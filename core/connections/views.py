from datetime import datetime, timedelta
import msgpack

import requests

from django.conf import settings
from django.contrib.auth import get_user_model

from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import View


from .middleware import get_client_address
from ..lims.models import Session
from ..staff.models import UserList, RemoteConnection

if settings.LIMS_USE_SCHEDULE:
    HALF_SHIFT = int(getattr(settings, 'HOURS_PER_SHIFT', 8)/2)

PROXY_URL = getattr(settings, 'DOWNLOAD_PROXY_URL', '')
MAX_CONTAINER_DEPTH = getattr(settings, 'MAX_CONTAINER_DEPTH', 2)

User = get_user_model()


@method_decorator(csrf_exempt, name='dispatch')
class AccessList(View):
    """
    Returns list of usernames that should be able to access the remote server referenced by the IP number inferred from
    the request.

    :key: r'^accesslist/$'
    """

    def get(self, request, *args, **kwargs):

        from ..staff.models import UserList
        client_addr = get_client_address(request)

        userlist = UserList.objects.filter(address=client_addr, active=True).first()

        if userlist:
            return JsonResponse(userlist.access_users(), safe=False)
        else:
            return JsonResponse([], safe=False)

    def post(self, request, *args, **kwargs):

        client_addr = get_client_address(request)
        userlist = UserList.objects.filter(address=client_addr, active=True).first()

        tz = timezone.get_current_timezone()
        errors = []

        if userlist:
            data = msgpack.loads(request.body)
            for conn in data:
                try:
                    project = User.objects.get(username=conn['project'])
                except:
                    errors.append("User '{}' not found.".format(conn['project']))
                status = conn['status']
                try:
                    dt = tz.localize(datetime.strptime(conn['date'], "%Y-%m-%d %H:%M:%S"))
                    r, created = RemoteConnection.objects.get_or_create(name=conn['name'], userlist=userlist, user=project)
                    r.status = status
                    if created:
                        r.created = dt
                    else:
                        r.end = dt
                    r.save()
                except:
                    pass

            return JsonResponse(userlist.access_users(), safe=False)
        else:
            return JsonResponse([], safe=False)


@method_decorator(csrf_exempt, name='dispatch')
class SSHKeys(View):
    """
    Returns SSH keys for specified user  if the remote server referenced by the IP number inferred from
    the request exists.

    :key: r'^keys/<username>$'
    """

    def get(self, request, *args, **kwargs):
        user = User.objects.filter(username=self.kwargs.get('username')).first()
        msg = ''
        if user:
            msg = '\n'.join(user.sshkeys.values_list('key', flat=True)).encode()

        return HttpResponse(msg, content_type='text/plain')

