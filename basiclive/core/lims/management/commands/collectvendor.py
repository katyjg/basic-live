# Modified from https://github.com/jochenklar/django-vendor-files/

import base64
import hashlib
import json
import os

import requests

from django.apps import apps as django_apps
from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Fetches static vendor files from CDNs defined in `vendor.json` files found in app/static/app directories'

    def handle(self, *args, **options):

        apps = django_apps.get_app_configs()
        for app in apps:
            vendor_path = os.path.join(app.path, 'static', app.label, 'vendor.json')
            if os.path.exists(vendor_path):
                vendors = json.loads(open(vendor_path).read())
                for key, vendor_conf in vendors.items():
                    for kind in [k for k in vendor_conf.keys() if k != 'url']:
                        for file in vendor_conf[kind]:
                            # get the directory and the file_name
                            filename = os.path.basename(file['path'])
                            if settings.DEBUG:
                                file_path = os.path.join(app.path, 'static', app.label, 'vendor', key, kind, filename)
                            else:
                                file_path = os.path.join(settings.STATIC_ROOT, app.label, 'vendor', key, kind, filename)
                            directory = os.path.dirname(file_path)

                            # create the needed directories
                            try:
                                os.makedirs(directory)
                            except OSError:
                                pass

                            # get the full url of the file
                            url = requests.compat.urljoin(vendor_conf['url'], file['path'])

                            print('%s -> %s' % (url, file_path))

                            # fetch the file from the cdn
                            response = requests.get(url)
                            response.raise_for_status()
                            with open(file_path, 'wb') as f:
                                f.write(response.content)

                            # check the intergrity of the file if a SRI was supplied
                            if 'sri' in file:
                                algorithm, file_hash = file['sri'].split('-')

                                h = hashlib.new(algorithm)
                                h.update(open(file_path, 'rb').read())
                                if base64.b64encode(h.digest()).decode() != file_hash:
                                    raise Exception('Subresource Integrity (SRI) failed for %s' % file_path)
