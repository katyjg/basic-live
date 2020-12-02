from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from django.utils.timezone import make_aware

from basiclive.core.lims.models import Project, Beamline
from basiclive.core.schedule.models import Beamtime, BeamlineSupport, AccessType, Downtime

import json
from datetime import datetime, timedelta


SHIFT_MAP = ["08", "16", "00"]

def get_project_by_name(name):
    return Project.objects.filter((Q(last_name=name['last_name']) & Q(first_name=name['first_name'])) | (
                Q(username__iexact=name['last_name']) | Q(username__iexact=name['first_name']))).first()

def get_project_by_account(account):
    try:
        return Project.objects.filter(username__iexact=account.split(',')[0].strip()).first()
    except:
        return None

def get_date(dt, shift, end=False):
    dt = datetime.strptime("{}T{}".format(dt, SHIFT_MAP[shift]), "%Y-%m-%dT%H")
    if end: dt += timedelta(hours=8)
    if shift == 2: dt += timedelta(days=1)
    return make_aware(dt)


class Command(BaseCommand):
    help = 'Imports beamtime from the Django 2 website.'

    def add_arguments(self, parser):
        parser.add_argument('--file', type=str)

    def handle(self, *args, **options):
        bt_file = options['file']
        access_map = { a.name.lower().replace('-', '_'): a for a in AccessType.objects.all() }
        with open(bt_file) as json_bt:
            data = json.load(json_bt)
            projects = [p for p in data if p['model'] == 'scheduler.proposal']
            beamtime = [p for p in data if p['model'] == 'scheduler.visit']
            downtime = [p for p in data if p['model'] == 'scheduler.stat' and p['fields']['mode'] == 'FacilityRepair']
            support = [p for p in data if p['model'] == 'scheduler.oncall']
            contact_map = { p['pk']: get_project_by_name(p['fields'])
                         for p in data if p['model'] == 'scheduler.supportperson' }
            beamline_map = {1: 2, 2: 1}
            project_map = {}

            for p in projects:
                mxproject = get_project_by_account(p['fields']['account']) or get_project_by_name(p['fields'])
                project_map[p['pk']] = {
                    'account': mxproject,
                    'email': p['fields']['email'],
                }
                try:
                    if not mxproject.email and p['fields']['email']:
                        mxproject.email = p['fields']['email']
                        mxproject.save()
                        print("Updating email '{}' for '{}'".format(mxproject.email, mxproject.username))
                except:
                    pass
                try:
                    mxproject.alias = int(p['fields']['last_name'])
                    mxproject.save()
                    print('Updating alias "{}" for "{}"'.format(mxproject.alias, mxproject.username))
                except:
                    pass
            print({p: k for p, k in project_map.items() if k['account'] == None})

            for p in beamtime:
                kind = AccessType.objects.get(name="Local")
                for k, v in access_map.items():
                    if p['fields'].get(k):
                        if p['fields'][k]: kind = v
                info = {
                    'project': p['fields']['proposal'] and project_map[p['fields']['proposal']]['account'] or None,
                    'beamline': Beamline.objects.get(pk=beamline_map[p['fields']['beamline']]),
                    'comments': p['fields']['description'],
                    'access': kind,
                    'start': get_date(p['fields']['start_date'], p['fields']['first_shift']),
                    'end': get_date(p['fields']['end_date'], p['fields']['last_shift'], True),
                }
                bt = Beamtime.objects.create(**info)

            for p in downtime:
                for bl in Beamline.objects.exclude(simulated=True):
                    info = {
                        'start': get_date(p['fields']['start_date'], p['fields']['first_shift']),
                        'end': get_date(p['fields']['end_date'], p['fields']['last_shift'], True),
                        'scope': 0,
                        'beamline': bl
                    }
                    downtime = Downtime.objects.create(**info)

            for p in support:
                BeamlineSupport.objects.create(staff=contact_map[p['fields']['local_contact']],
                                               date=datetime.strptime(p['fields']['date'], "%Y-%m-%d"))
