import functools
import operator
import os
from datetime import timedelta

import httpx2
import msgpack
from django import http
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.http import JsonResponse
from django.urls import reverse_lazy
from django.utils import timezone, dateparse
from django.utils.decorators import method_decorator
from django.utils.encoding import force_str
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import View

from basiclive.core.lims.conf import settings as lims_settings
from basiclive.core.lims.models import ActivityLog, Beamline, Container, Automounter, Data, DataType, Sample
from basiclive.core.lims.models import AnalysisReport, Project, Session, SSHKey
from basiclive.core.lims.templatetags.bl_tags import humanize_duration
from basiclive.utils.data import parse_frames
from basiclive.utils.mixins import AuthenticationRequiredMixin
from basiclive.utils.signing import Signer, InvalidSignature


def get_hours_per_shift() -> int:
    try:
        from basiclive.core.schedule.conf import settings as schedule_settings
        return schedule_settings.HOURS_PER_SHIFT
    except (ImportError, AttributeError):
        return 8


if lims_settings.USE_SCHEDULE:
    HALF_SHIFT = int(get_hours_per_shift() / 2)

PROXY_URL = lims_settings.DOWNLOAD_PROXY_URL
MAX_CONTAINER_DEPTH = lims_settings.MAX_CONTAINER_DEPTH


def make_secure_path(path):
    # Download  key
    url = PROXY_URL + '/data/create/'
    try:
        r = httpx2.post(url, data={'path': path})
        if r.status_code == 200:
            return r.json()['key']
    except httpx2.HTTPError as e:
        raise ValueError('Unable to create SecurePath') from e
    raise ValueError('Unable to create SecurePath')


@method_decorator(csrf_exempt, name='dispatch')
class VerificationMixin(object):
    """
    Mixin to verify identity of user.
    Supports JWT authenticated users (request.user.is_authenticated) as well as
    legacy URL parameters `username` and `signature` where the signature is a string
    signed using a private key and verified using the public key stored on the
    User or Project object.
    """

    def dispatch(self, request, *args, **kwargs):
        if getattr(request, 'user', None) and request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)

        username = kwargs.get('username')
        signature = kwargs.get('signature')

        if not (username and signature):
            return http.HttpResponseForbidden("Authentication required.")

        User = get_user_model()
        user = User.objects.filter(username=username).first()
        project = Project.objects.filter(name__exact=username).first()

        if not user and not project:
            return http.HttpResponseNotFound("User or Project not found.")

        public_key = None
        if user:
            if getattr(user, 'key', None):
                public_key = user.key
            elif hasattr(user, 'sshkeys') and user.sshkeys.exists():
                public_key = user.sshkeys.first().key
        if not public_key and project:
            if getattr(project, 'key', None):
                public_key = project.key
            elif hasattr(project, 'sshkeys') and project.sshkeys.exists():
                public_key = project.sshkeys.first().key
            elif project.pi and hasattr(project.pi, 'sshkeys') and project.pi.sshkeys.exists():
                public_key = project.pi.sshkeys.first().key

        if not public_key:
            return http.HttpResponseBadRequest("Public key not configured.")

        try:
            signer = Signer(public=public_key)
            value = signer.unsign(signature)
        except InvalidSignature:
            return http.HttpResponseForbidden("Invalid signature.")

        if value != username:
            return http.HttpResponseForbidden("Signature mismatch.")

        if user:
            request.user = user
        elif project and project.pi:
            request.user = project.pi

        if project:
            request.project = project

        return super().dispatch(request, *args, **kwargs)


@method_decorator(csrf_exempt, name='dispatch')
class UpdateUserKey(View):
    """
    API for adding a public key to a BasicLIVE Project. This method will only be allowed if the signature can be verified,
    or the request is authenticated by a User with access to the Project, and the Project does not already have a public key registered.

    :key: r'^(?P<signature>(?P<username>):.+)/project/$' or POST /project/ with project/public.
    """

    def post(self, request, *args, **kwargs):
        public = request.POST.get('public')
        if not public:
            return http.HttpResponseBadRequest("Public key required.")

        username = (
            kwargs.get('username')
            or request.POST.get('project')
            or request.POST.get('username')
            or (request.headers.get('X-Project') if hasattr(request, 'headers') else request.META.get('HTTP_X_PROJECT'))
        )
        signature = kwargs.get('signature')

        target_project = None
        if username:
            target_project = Project.objects.filter(name__exact=username).first()
        elif getattr(request, 'project', None):
            target_project = request.project

        if not target_project:
            return http.HttpResponseNotFound("Project does not exist.")

        if getattr(request, 'user', None) and request.user.is_authenticated:
            if not request.user.can_access_project(target_project):
                return http.HttpResponseForbidden("Permission denied.")
        elif signature:
            signer = Signer(public=public)
            try:
                value = signer.unsign(signature)
            except InvalidSignature:
                return http.HttpResponseForbidden("Invalid signature.")
            if value != kwargs.get('username'):
                return http.HttpResponseForbidden("Signature mismatch.")
        else:
            return http.HttpResponseForbidden("Authentication required.")

        has_key = (
            getattr(target_project, 'key', None)
            or (hasattr(target_project, 'sshkeys') and target_project.sshkeys.exists())
        )
        if has_key:
            return http.HttpResponseNotModified()

        SSHKey.objects.create(
            name='API Key',
            key=public,
            user=target_project.pi,
            project=target_project
        )
        if hasattr(target_project, 'key'):
            target_project.key = public
            target_project.save(update_fields=['key'])

        ActivityLog.objects.log_activity(
            request, request.user, ActivityLog.TYPE.MODIFY,
            f'Key Initialized for user {request.user}'
        )

        return JsonResponse({})


class LaunchSession(AuthenticationRequiredMixin, View):
    """
    Method to start a BasicLIVE Session from the beamline. If a Session with the same name already exists, a new Stretch
    will be added to the Session.

    """

    def post(self, request, *args, **kwargs):
        project_name = (
            kwargs.get('username')
            or kwargs.get('project')
            or request.POST.get('project')
            or request.GET.get('project')
            or (request.headers.get('X-Project') if hasattr(request, 'headers') else request.META.get('HTTP_X_PROJECT'))
        )
        beamline_name = kwargs.get('beamline')
        session_name = kwargs.get('session')

        try:
            beamline = Beamline.objects.get(acronym__exact=beamline_name)
        except Beamline.DoesNotExist:
            raise http.Http404("Beamline does not exist.")

        if not beamline.active:
            return http.HttpResponseForbidden("Beamline is inactive or decommissioned.")

        project = None
        if project_name:
            project = Project.objects.filter(name__exact=project_name).first()
            if not project and str(project_name).isdigit():
                project = Project.objects.filter(id=int(project_name)).first()
            if not project:
                raise http.Http404("Project does not exist.")
        elif getattr(request, 'project', None):
            project = request.project

        if not project and lims_settings.USE_SCHEDULE:
            try:
                from basiclive.core.schedule.models import Beamtime
                now = timezone.now()
                bts = Beamtime.objects.filter(
                    beamline=beamline,
                    start__lte=now + timedelta(hours=HALF_SHIFT),
                    end__gte=now - timedelta(hours=HALF_SHIFT),
                    cancelled=False
                )
                accessible = [bt.project for bt in bts if request.user.can_access_project(bt.project)]
                if len(accessible) == 1:
                    project = accessible[0]
            except Exception:
                pass

        if not project:
            raise http.Http404("Project does not exist or not specified.")

        if not request.user.can_access_project(project):
            return http.HttpResponseForbidden("Permission denied.")

        end_time = None
        if lims_settings.USE_SCHEDULE:
            now = timezone.now()
            beamtime = project.beamtime.filter(beamline=beamline, start__lte=now + timedelta(hours=HALF_SHIFT),
                                               end__gte=now - timedelta(hours=HALF_SHIFT))
            if beamtime.exists():
                end_time = max(beamtime.values_list('end', flat=True)).isoformat()
            elif beamline.simulated:
                end_time = (timezone.now() + timedelta(hours=2)).isoformat()

        session, created = Session.objects.get_or_create(project=project, beamline=beamline, name=session_name)
        if created:
            # Download  key
            try:
                key = make_secure_path(os.path.join(project.name, session.name))
                session.url = key
                session.save()
            except ValueError:
                return http.HttpResponseServerError("Unable to create SecurePath")
        session.launch()
        if created:
            ActivityLog.objects.log_activity(
                request, session, ActivityLog.TYPE.CREATE, f'Session {session} launched'
            )

        try:
            feedback_url = force_str(reverse_lazy('session-feedback', kwargs={'key': session.feedback_key()}))
            survey_url = request.build_absolute_uri(feedback_url)
        except Exception:
            survey_url = None

        session_info = {'session': session.name,
                        'duration': humanize_duration(session.total_time()),
                        'survey': survey_url,
                        'end_time': end_time}
        return JsonResponse(session_info)


class CloseSession(VerificationMixin, View):
    """
    Method to close a BasicLIVE Session from the beamline.

    :key: r'^(?P<signature>(?P<username>):.+)/close/(?P<beamline>)/(?P<session>)/$'
    """

    def post(self, request, *args, **kwargs):
        project_name = (
            kwargs.get('username')
            or kwargs.get('project')
            or request.POST.get('project')
            or request.GET.get('project')
            or (request.headers.get('X-Project') if hasattr(request, 'headers') else request.META.get('HTTP_X_PROJECT'))
        )
        beamline_name = kwargs.get('beamline')
        session_name = kwargs.get('session')

        try:
            beamline = Beamline.objects.get(acronym__exact=beamline_name)
        except Beamline.DoesNotExist:
            raise http.Http404("Beamline does not exist.")

        session = None
        if project_name:
            project = Project.objects.filter(name__exact=project_name).first()
            if not project and str(project_name).isdigit():
                project = Project.objects.filter(id=int(project_name)).first()
            if not project:
                raise http.Http404("Project does not exist.")
            if not request.user.can_access_project(project):
                return http.HttpResponseForbidden("Permission denied.")
            session = project.sessions.filter(beamline=beamline, name=session_name).first()
        else:
            sessions = Session.objects.filter(beamline=beamline, name=session_name)
            if getattr(request, 'project', None):
                session = sessions.filter(project=request.project).first()
            if not session:
                accessible = [s for s in sessions if request.user.can_access_project(s.project)]
                if len(accessible) >= 1:
                    session = accessible[0]

        if not session:
            raise http.Http404("Session does not exist.")

        if not request.user.can_access_project(session.project):
            return http.HttpResponseForbidden("Permission denied.")

        session.close()
        try:
            last_stretch = session.stretches.with_duration().last()
            duration_val = last_stretch.duration if last_stretch else None
        except Exception:
            last_stretch = session.stretches.last()
            duration_val = ((last_stretch.end or timezone.now()) - last_stretch.start) if last_stretch else None

        duration_str = humanize_duration(duration_val) if duration_val else "0m"
        session_info = {'session': session.name,
                        'duration': duration_str}
        return JsonResponse(session_info)


KEYS = {
    'container__name': 'container',
    'container__kind__name': 'container_type',
    'group__name': 'group',
    'id': 'id',
    'name': 'name',
    'barcode': 'barcode',
    'comments': 'comments',
    'location__name': 'location',
    'port_name': 'port'
}


def prep_sample(info, **kwargs):
    sample = {
        KEYS.get(key): value
        for key, value in info.items()
    }
    sample.update(**kwargs)
    return sample


class ProjectSamples(VerificationMixin, View):
    """
    :Return: Dictionary for each On-Site sample owned by the Project and NOT loaded on another beamline.

    :key: r'^(?P<signature>(?P<username>):.+)/samples/(?P<beamline>)/$'
    """

    def get(self, request, *args, **kwargs):
        project_name = (
            kwargs.get('username')
            or kwargs.get('project')
            or request.GET.get('project')
            or (request.headers.get('X-Project') if hasattr(request, 'headers') else request.META.get('HTTP_X_PROJECT'))
        )
        beamline_name = kwargs.get('beamline')

        try:
            beamline = Beamline.objects.get(acronym=beamline_name)
            automounter = Automounter.objects.select_related('container').get(beamline=beamline, active=True)
        except (Beamline.DoesNotExist, Automounter.DoesNotExist):
            raise http.Http404("Beamline or Automounter does not exist")

        project = None
        if project_name:
            project = Project.objects.filter(name__exact=project_name).first()
            if not project and str(project_name).isdigit():
                project = Project.objects.filter(id=int(project_name)).first()
            if not project:
                raise http.Http404("Project does not exist.")
        elif getattr(request, 'project', None):
            project = request.project
        else:
            active_sess = beamline.active_session()
            if active_sess:
                project = active_sess.project

        if not project:
            raise http.Http404("Project does not exist or not specified.")

        if not request.user.can_access_project(project):
            return http.HttpResponseForbidden("Permission denied.")

        lookups = ['container__{}'.format('__'.join(['parent']*(i+1))) for i in range(MAX_CONTAINER_DEPTH)]
        query = Q(container__status=Container.STATES.ON_SITE)
        query &= (
            functools.reduce(operator.or_, [Q(**{lookup:automounter.container}) for lookup in lookups]) |
            functools.reduce(operator.and_, [Q(**{"{}__isnull".format(lookup):True}) for lookup in lookups])
        )

        sample_list = project.samples.filter(query).order_by('group__priority', 'priority').values(
            'container__name', 'container__kind__name', 'group__name', 'id', 'name', 'barcode', 'comments',
            'location__name', 'container__location__name', 'port_name'
        )
        samples = [prep_sample(sample, priority=i) for i, sample in enumerate(sample_list)]
        return JsonResponse(samples, safe=False)


TRANSFORMS = {
    'file_name': 'filename',
    'exposure_time': 'exposure',
}


class AddReport(VerificationMixin, View):
    """
    Method to add meta-data and JSON details about an AnalysisReport.
    """

    def post(self, request, *args, **kwargs):
        info = msgpack.loads(request.body, raw=False)

        project_name = (
            kwargs.get('username')
            or kwargs.get('project')
            or (info.get('project') if isinstance(info, dict) else None)
            or request.GET.get('project')
            or (request.headers.get('X-Project') if hasattr(request, 'headers') else request.META.get('HTTP_X_PROJECT'))
        )
        beamline_name = kwargs.get('beamline')
        try:
            beamline = Beamline.objects.get(acronym=beamline_name) if beamline_name else None
        except Beamline.DoesNotExist:
            beamline = None

        project = None
        if project_name:
            project = Project.objects.filter(name__exact=project_name).first()
            if not project and str(project_name).isdigit():
                project = Project.objects.filter(id=int(project_name)).first()
            if not project:
                raise http.Http404("Project does not exist.")

        data = None
        if info.get('data_id'):
            data_ids = info.get('data_id')
            if not isinstance(data_ids, (list, tuple)):
                data_ids = [data_ids]
            data = Data.objects.filter(pk__in=data_ids)
            if not data.exists():
                raise http.Http404("Data does not exist")
            if not project:
                project = data.first().project

        if not project and getattr(request, 'project', None):
            project = request.project

        if not project and beamline:
            active_sess = beamline.active_session()
            if active_sess:
                project = active_sess.project

        if not project:
            raise http.Http404("Project does not exist or not specified.")

        if not request.user.can_access_project(project):
            return http.HttpResponseForbidden("Permission denied.")

        # Download  key
        try:
            key = make_secure_path(info.get('directory'))
        except ValueError:
            return http.HttpResponseServerError("Unable to create SecurePath")

        details = {
            'project': project,
            'score': info.get('score') if info.get('score') else 0,
            'kind': info.get('kind', 'Data Analysis'),
            'details': info.get('details'),
            'name': info.get('title'),
            'url': key
        }
        report = AnalysisReport.objects.filter(pk=info.get('id')).first()

        if report:
            project.reports.filter(pk=report.pk).update(**details)
        else:
            report, created = AnalysisReport.objects.get_or_create(**details)

        if data:
            for d in data:
                report.data.add(d)

        beamline_name = kwargs.get('beamline', 'beamline')
        ActivityLog.objects.log_activity(
            request, report, ActivityLog.TYPE.CREATE,
            f"Report {report.name} uploaded from {beamline_name}"
        )
        return JsonResponse({'id': report.pk})


class AddData(VerificationMixin, View):
    """
    Method to add meta-data about Data collected on the Beamline.
    """

    def post(self, request, *args, **kwargs):
        info = msgpack.loads(request.body, raw=False)

        project_name = (
            kwargs.get('username')
            or kwargs.get('project')
            or (info.get('project') if isinstance(info, dict) else None)
            or request.GET.get('project')
            or (request.headers.get('X-Project') if hasattr(request, 'headers') else request.META.get('HTTP_X_PROJECT'))
        )
        beamline_name = kwargs.get('beamline')

        try:
            beamline = Beamline.objects.get(acronym=beamline_name)
        except Beamline.DoesNotExist:
            raise http.Http404("Beamline does not exist")

        session = beamline.active_session()

        project = None
        if project_name:
            project = Project.objects.filter(name__exact=project_name).first()
            if not project and str(project_name).isdigit():
                project = Project.objects.filter(id=int(project_name)).first()
            if not project:
                raise http.Http404("Project does not exist.")

        sample = None
        if info.get('sample_id'):
            sample = Sample.objects.filter(pk=info.get('sample_id')).first()
            if sample and not project:
                project = sample.project

        if not project and session:
            project = session.project

        if not project and getattr(request, 'project', None):
            project = request.project

        if not project:
            raise http.Http404("Project does not exist or not specified.")

        if not request.user.can_access_project(project):
            return http.HttpResponseForbidden("Permission denied.")

        # Download  key
        try:
            key = make_secure_path(info.get('directory'))
        except ValueError:
            return http.HttpResponseServerError("Unable to create SecurePath")

        if sample and sample.project != project:
            sample = None
        elif not sample:
            sample = project.samples.filter(pk=info.get('sample_id')).first()

        data = Data.objects.filter(pk=info.get('id')).first()

        details = {
            'session': (session and session.project == project) and session or None,
            'project': project,
            'beamline': beamline,
            'url': key,
            'sample': sample,
            'group': sample and sample.group or None,
        }

        base_fields = ['energy', 'frames', 'file_name', 'exposure_time', 'attenuation', 'name', 'beam_size']
        details.update({f: info.get(f in TRANSFORMS and TRANSFORMS[f] or f) for f in base_fields})
        details.update(kind=DataType.objects.get_by_natural_key(info['type']))
        num_frames = 1
        if info.get('frames'):
            num_frames = len(parse_frames(info['frames']))
            details.update(num_frames=num_frames)

        # Set start and end time for dataset
        end_time = timezone.now() if 'end_time' not in info else dateparse.parse_datetime(info['end_time'])
        start_time = (
            end_time - timedelta(seconds=(num_frames*info['exposure_time']))
        ) if 'start_time' not in info else dateparse.parse_datetime(info['start_time'])
        details.update(start_time=start_time, end_time=end_time)

        for k in ['sample_id', 'group', 'port', 'frames', 'energy', 'filename', 'exposure', 'attenuation',
                  'container', 'name', 'directory', 'type', 'id']:
            if k in info:
                info.pop(k)

        details['meta_data'] = info

        if data:
            Data.objects.filter(pk=data.pk).update(**details)
        else:
            data, created = Data.objects.get_or_create(**details)

        ActivityLog.objects.log_activity(
            request, data, ActivityLog.TYPE.CREATE, f"{data.kind.name} metadata uploaded from {beamline.acronym}"
        )
        return JsonResponse({'id': data.pk})


class FetchProjects(AuthenticationRequiredMixin, View):

    def get(self, request, *args, **kwargs):
        user = self.request.user

        projects = user.get_projects()
        return JsonResponse(projects, safe=False)

