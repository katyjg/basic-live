from ipaddress import ip_address, ip_network
from basiclive.utils.conf import settings


class IPAddressList(list):
    def __init__(self, *ips):
        super().__init__()
        self.extend([ip_network(ip, False) for ip in ips])

    def __contains__(self, address):
        ip = ip_address(address)
        return any(ip in net for net in self)


def get_trusted_proxies() -> int:
    try:
        from basiclive.core.acl.conf import settings as acl_settings
        return acl_settings.TRUSTED_PROXIES
    except (ImportError, AttributeError):
        return settings.TRUSTED_PROXIES


def get_client_address(request):
    depth = get_trusted_proxies()
    if 'HTTP_X_FORWARDED_FOR' in request.META:
        header = request.META['HTTP_X_FORWARDED_FOR']
        levels = [x.strip() for x in header.split(',')]

        if len(levels) >= depth:
            address = ip_address(levels[-depth])
        else:
            address = None
    elif 'REMOTE_ADDR' in request.META:
        try:
            address = ip_address(request.META['REMOTE_ADDR'])
        except ValueError:
            address = None
    else:
        address = None
    return address and address.exploded or address
