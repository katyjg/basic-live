import re
from django.http import Http404
from django.utils.deprecation import MiddlewareMixin

from basiclive.core.acl.conf import settings
from basiclive.utils.network import IPAddressList, get_client_address


def get_trusted_urls():
    return settings.TRUSTED_URLS


def get_trusted_ips():
    return settings.TRUSTED_IPS


class TrustedAccessMiddleware(MiddlewareMixin):
    """
    Middleware to prevent access to the admin if the user IP
    isn't in the TRUSTED_IPS setting.
    """

    def process_request(self, request):
        client_address = get_client_address(request)
        trusted_urls = get_trusted_urls()
        if any(re.match(addr, request.path) for addr in trusted_urls):
            trusted_addresses = IPAddressList(*get_trusted_ips())
            if client_address not in trusted_addresses:
                raise Http404()

    def process_template_response(self, request, response):
        client_address = get_client_address(request)
        trusted_urls = get_trusted_urls()
        if any(re.match(addr, request.path) for addr in trusted_urls):
            trusted_addresses = IPAddressList(*get_trusted_ips())
            if response.context_data:
                response.context_data['internal_request'] = (client_address in trusted_addresses)
        return response
