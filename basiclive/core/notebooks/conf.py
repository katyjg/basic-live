from typing import Any
from basiclive.utils.conf import AppSettings

DEFAULTS: dict[str, Any] = {
    "PAGE_SIZE": 10,
    "MAX_ENTRY_SIZE": 25 * 1024 * 1024,  # 25 MB
}

settings = AppSettings("NOTEBOOKS", DEFAULTS)
