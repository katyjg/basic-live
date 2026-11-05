"""
Compatibility shim for relocated middleware and network utilities.
Canonical locations:
- basiclive.utils.network (IPAddressList, get_client_address)
- basiclive.core.acl.middleware (TrustedAccessMiddleware)
- basiclive.core.api.middleware (APIAuthenticationMiddleware, get_v2_user, get_v3_user)
"""

from basiclive.utils.network import IPAddressList, get_client_address
from basiclive.core.acl.middleware import TrustedAccessMiddleware
from basiclive.core.api.middleware import APIAuthenticationMiddleware, get_v2_user, get_v3_user

__all__ = [
    'IPAddressList',
    'get_client_address',
    'TrustedAccessMiddleware',
    'APIAuthenticationMiddleware',
    'get_v2_user',
    'get_v3_user',
]
