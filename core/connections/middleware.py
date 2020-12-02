from django.conf import settings

from ipaddress import ip_address
from ipaddress import ip_network

TRUSTED_URLS = getattr(settings, 'TRUSTED_URLS', [])
TRUSTED_IPS = getattr(settings, 'TRUSTED_IPS', ['127.0.0.1/32'])


def get_client_address(request):
    depth = getattr(settings, 'TRUSTED_PROXIES', 2)
    if 'HTTP_X_FORWARDED_FOR' in request.META:
        header = request.META['HTTP_X_FORWARDED_FOR']
        levels = [x.strip() for x in header.split(',')]

        if len(levels) >= depth:
            address = ip_address(levels[-depth])
        else:
            address = None
    else:
        address = ip_address(request.META['REMOTE_ADDR'])
    return address and address.exploded or address

