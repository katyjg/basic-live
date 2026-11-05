from importlib.metadata import version, PackageNotFoundError

import truststore
truststore.inject_into_ssl()

try:
    __version__ = version('basic-live')
except PackageNotFoundError:
    __version__ = '0.0.0-dev'

