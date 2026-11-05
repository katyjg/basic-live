"""
Pluggable icon subsystem for BasicLIVE.

Provides backend-agnostic icon resolution, sizing classes, and stylesheet injection.
"""
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

from django.conf import settings
from django.utils.module_loading import import_string
from django.utils.safestring import mark_safe


class BaseIconBackend:
    """
    Abstract base class for BasicLIVE icon backends.
    """
    name = "base"
    base_class = ""
    icon_prefix = "icon-"
    allowed_sizes = ("xs", "sm", "md", "lg", "xl")
    size_class_prefix = "bl-icon-"
    aliases: Dict[str, str] = {}

    def format_size_class(self, size: Optional[str] = None) -> str:
        """
        Validates and returns the CSS class corresponding to a standardized size literal.
        """
        if not size:
            return ""
        size_str = str(size).strip().lower()
        if size_str not in self.allowed_sizes:
            raise ValueError(
                f"Invalid icon size '{size}'. Allowed sizes: {', '.join(self.allowed_sizes)}"
            )
        return f"{self.size_class_prefix}{size_str}"

    @lru_cache(maxsize=100)
    def resolve_icon_name(self, icon: str) -> str:
        clean = icon.strip()
        if not clean:
            return ""

        canonical = clean.split()[-1]
        candidates = [clean, canonical, clean.split("-")[0]]
        for candidate in candidates:
            target = self.aliases.get(candidate)
            if target:
                break
        else:
            target = canonical
        return f"{self.icon_prefix}{target}"

    def get_css_classes(
        self,
        icon: str,
        size: Optional[str] = None,
        extra_class: str = ""
    ) -> str:
        if not icon or not icon.strip():
            return ""
        parts = [self.base_class, self.resolve_icon_name(icon)]
        size_cls = self.format_size_class(size)
        if size_cls:
            parts.append(size_cls)
        if extra_class and extra_class.strip():
            parts.append(extra_class.strip())
        return " ".join(parts)

    def get_stylesheet_urls(self) -> List[str]:
        """
        Returns a list of static asset relative paths or URLs required for this icon font.
        """
        raise NotImplementedError("Icon backends must implement get_stylesheet_urls()")

    def get_assets(self) -> Dict[str, Any]:
        """
        Returns an asset specification dictionary (matching the schema in assets.json)
        to be downloaded and verified by the `collectassets` management command.
        """
        return {}

    def cleanup_assets(self, assets_root: Path) -> None:
        """
        Optional cleanup hook for pruning stale or unneeded files in the backend's asset directory.
        """
        pass

    def post_collect(self, assets_root: Path) -> None:
        """
        Lifecycle hook invoked by `collectassets` after downloading assets.
        Calls `cleanup_assets()` by default.
        """
        self.cleanup_assets(assets_root)


class ThemifyBackend(BaseIconBackend):
    """
    Default icon backend using Themify Icons.
    """
    name = "themify"
    base_class = "ti"
    icon_prefix = "ti-"
    stylesheet_urls = ("themify-icons/css/themify-icons.css",)

    # Canonical aliases mapping semantic action/object names to Themify glyph names
    aliases = {
        "add": "plus",
        "add-shipment": "plus",
        "remove": "minus",
        "calendar": "calendar",
        "check": "check2-square",
        "edit": "pencil",
        "delete": "trash",
        "view": "eye",
        "list": "view-list-alt",
        "history": "timer",
        "stats": "pulse",
        "usage": "pie-chart",
        "connections": "rss-alt",
        "feedback": "star",
        "support": "headphone-alt",
        "areas": "target",
        "new-area": "target",
        "request": "ruler-pencil",
        "samples": "paint-bucket",
        "groups": "layout-accordion-list",
        "profile": "user",
        'journal': 'book',
        "notebook": "agenda",
        "projects": "briefcase",
        'help': 'help-alt',
        'text-entry': 'align-left',
        'file-entry': 'clip',
        'image-entry': 'image',
        'video-entry': 'youtube',
        'sketch-entry': 'brush',
        'data-entry': 'layout-grid3',
        "settings": "settings",
        "light-theme": "shine",
        "dark-theme": "drupal",
        "auto-theme": "widget",
        "data": "layout-grid3",
        "home": "home",
        "quote": "quote-left",
        "reports": "bar-chart",
        "send": "location-arrow",
        "receive": "shopping-cart-full",
        "shipment": "truck",
        "onsite": "location-pin",
        "recall": "control-backward",
        "error": "alert",
        "comments": "comment-alt",
        "arrow-left": "arrow-left",
        "arrow-right": "arrow-right",
        "arrow-up": "arrow-up",
        "arrow-down": "arrow-down",
        "requests": "ruler-pencil",
        "container": "package"
    }

    def get_stylesheet_urls(self) -> List[str]:
        return list(self.stylesheet_urls)

    def get_assets(self) -> Dict[str, Any]:
        return {
            "themify-icons": {
                "url": "https://cdn.jsdelivr.net/npm/@icon/themify-icons@1.0.1-alpha.3/",
                "css": [
                    {
                        "path": "themify-icons.css",
                        "sri": "sha256-qoOBcGvQQnLXRmjq/r5ajkQ88/GGiFhWN4RXOutpnAY=",
                    },
                    {
                        "path": "themify-icons.eot",
                        "sri": "sha256-3/QV2uyRG2Xcpb4CBxoYJbdVCP8VjeW42Fl2lX25Mcs=",
                    },
                    {
                        "path": "themify-icons.svg",
                        "sri": "sha256-968uCWyFwu1vaLsIb3ksZ/KmBBy7gU/CeWkSsu70/nY=",
                    },
                    {
                        "path": "themify-icons.ttf",
                        "sri": "sha256-NQZjpGZeAAcsaKh60/oL5HuKkUJBJ/Xz4J9mQZcpXwE=",
                    },
                    {
                        "path": "themify-icons.woff",
                        "sri": "sha256-DbXFoUdet6PlAomD6h5kLRssAPr/aiUKN1ArDzgypKc=",
                    },
                ],
            }
        }


class BootstrapIconBackend(BaseIconBackend):
    """
    Icon backend for Bootstrap Icons.
    """
    name = "bootstrap-icons"
    base_class = "bi"
    icon_prefix = "bi-"
    stylesheet_urls = ("bootstrap-icons/css/bootstrap-icons.min.css",)
    aliases = {
        "add": "plus-lg",
        "remove": "dash-lg",
        "calendar": "calendar",
        "check": "check-box",
        "edit": "pencil",
        "delete": "trash",
        "move": "arrows-move",
        "view": "eye",
        "list": "list-ul",
        "history": "stopwatch",
        "stats": "activity",
        "usage": "pie-chart",
        "connections": "rss",
        "feedback": "star",
        "support": "headset",
        "areas": "bookmarks",
        "new-area": "bookmark-plus",
        "request": "clipboard-heart",
        "samples": "flask",
        "groups": "collection",
        "profile": "person",
        'journal': 'journals',
        "notebook": "journal-bookmark",
        "projects": "briefcase",
        'help': 'question-circle',
        'text-entry': 'body-text',
        'file-entry': 'paperclip',
        'image-entry': 'image',
        'video-entry': 'play-btn',
        'sketch-entry': 'brush',
        'data-entry': 'table',
        "settings": "gear",
        "light-theme": "sun",
        "dark-theme": "moon",
        "auto-theme": "circle-half",
        "home": "house",
        "data": "table",
        "reports": "journal-richtext",
        "send": "send-check",
        "receive": "cart3",
        "shipment": "truck",
        "onsite": "geo-alt",
        "recall": "send-x",
        "error": "exclamation-diamond",
        "comments": "chat-left-text",
        "arrow-left": "arrow-left",
        "arrow-right": "arrow-right",
        "arrow-up": "arrow-up",
        "arrow-down": "arrow-down",
        "requests": "card-checklist",
        "container": "box-seam",
    }

    def get_stylesheet_urls(self) -> List[str]:
        return list(self.stylesheet_urls)

    def get_assets(self):
        return {
            "bootstrap-icons": {
                "css": [
                    {
                        "path": "https://cdn.jsdelivr.net/npm/bootstrap-icons@1.13.1/font/bootstrap-icons.min.css",
                        "sri": "sha256-pdY4ejLKO67E0CM2tbPtq1DJ3VGDVVdqAR6j3ZwdiE4=",
                    },
                    {
                        "path": "https://cdn.jsdelivr.net/npm/bootstrap-icons@1.13.1/font/fonts/bootstrap-icons.woff",
                        "file": "fonts/bootstrap-icons.woff",
                        "sri": "sha256-9VUTt7WRy4SjuH/w406iTUgx1v7cIuVLkRymS1tUShU=",
                    },
                    {
                        "path": "https://cdn.jsdelivr.net/npm/bootstrap-icons@1.13.1/font/fonts/bootstrap-icons.woff2",
                        "file": "fonts/bootstrap-icons.woff2",
                        "sri": "sha256-bHVxA2ShylYEJncW9tKJl7JjGf2weM8R4LQqtm/y6mE=",

                    },
                ],
            }
        }


class TablerIconBackend(BootstrapIconBackend):
    """
    Icon backend for Tabler Icons.
    """
    name = "tabler-icons"
    base_class = "ti"
    icon_prefix = "ti-"
    stylesheet_urls = ("tabler-icons/css/tabler-icons-200.min.css",)
    aliases = {
        "add": "plus",
        "add-shipment": "cube-plus",
        "remove": "minus",
        "calendar": "calendar-week",
        "check": "checkbox",
        "edit": "pencil",
        "delete": "trash",
        "move": "arrows-move",
        "view": "eye",
        "list": "list",
        "history": "stopwatch",
        "stats": "activity",
        "usage": "chart-pie",
        "connections": "rss",
        "feedback": "star",
        "support": "headset",
        "areas": "bookmarks",
        "new-area": "bookmark-plus",
        "request": "clipboard-heart",
        "samples": "test-pipe",
        "groups": "category",
        "profile": "user-circle",
        'journal': 'books',
        "projects": "briefcase",
        'text-entry': 'text-plus',
        'file-entry': 'paperclip',
        'image-entry': 'photo-plus',
        'video-entry': 'brand-youtube',
        'sketch-entry': 'sketching',
        'data-entry': 'table-plus',
        "light-theme": "brightness-up",
        "dark-theme": "moon-stars",
        "auto-theme": "brightness",
        "data": "table-alias",
        "reports": "report",
        "receive": "shopping-cart-check",
        "shipment": "truck-delivery",
        "onsite": "map-pin",
        "recall": "send-off",
        "error": "exclamation-circle",
        "comments": "message",
        "requests": "list-details",
        "container": "package",
    }

    def get_assets(self):
        return {
            "tabler-icons": {
                "css": [
                    {
                        "path": "https://cdn.jsdelivr.net/npm/@tabler/icons-webfont@3.48.0/dist/tabler-icons-200.min.css",
                        "sri": "sha256-KQbWBRFkUcTpt4+cKPVJoGM73BCOsof9+CbTl2eZFi4=",
                    },
                    {
                        "path": "https://cdn.jsdelivr.net/npm/@tabler/icons-webfont@3.48.0/dist/fonts/tabler-icons-200.woff",
                        "file": "fonts/tabler-icons-200.woff",
                        "sri": "sha256-3SY4XdJPpmzy36j+2h97VGzQwSF2LArv0WsaKjAETko=",
                    },
                    {
                        "path": "https://cdn.jsdelivr.net/npm/@tabler/icons-webfont@3.48.0/dist/fonts/tabler-icons-200.woff2",
                        "file": "fonts/tabler-icons-200.woff2",
                        "sri": "sha256-XW/0uxZQIMHi4uNfV15brom0vX3qpLc92R3UMGtUHF0=",
                    },
                    {
                        "path": "https://cdn.jsdelivr.net/npm/@tabler/icons-webfont@3.48.0/dist/fonts/tabler-icons-200.ttf",
                        "file": "fonts/tabler-icons-200.ttf",
                        "sri": "sha256-Z8xmF4oPnEJyHen+Prl8jGuqVrEHiG7YxJe/zJY1zCc=",
                    },
                    {
                        "path": "https://cdn.jsdelivr.net/npm/@tabler/icons-webfont@3.48.0/dist/fonts/tabler-icons-200.svg",
                        "file": "fonts/tabler-icons-200.svg",
                        "sri": "sha256-lUKqdWdV9vZOJ1PhIqqannZJynRmputZHn1YTUyJYIY=",
                    },
                ],
            }
        }

def get_icon_backend() -> BaseIconBackend:
    """
    Retrieves the configured icon backend instance.
    Defaults to ThemifyBackend.
    """
    backend_config = getattr(
        settings,
        "BASICLIVE_ICON_BACKEND",
        "basiclive.core.lims.icons.ThemifyBackend"
    )

    if isinstance(backend_config, BaseIconBackend):
        return backend_config
    if isinstance(backend_config, type) and issubclass(backend_config, BaseIconBackend):
        return backend_config()
    if isinstance(backend_config, str):
        backend_cls = import_string(backend_config)
        return backend_cls()

    raise ValueError(
        f"Invalid BASICLIVE_ICON_BACKEND: {backend_config!r}. Expected a subclass or dotted path to BaseIconBackend."
    )


def render_icon(
    icon: Optional[str] = None,
    size: Optional[str] = None,
    extra_class: Optional[str] = None,
    name: Optional[str] = None,
) -> str:
    """
    Convenience helper to render a standalone HTML icon element for use in Python code (forms, admin).
    Accepts either 'icon' or 'name' as positional or keyword argument.
    """
    icon_name = name or icon
    if not icon_name or not str(icon_name).strip():
        return mark_safe("")
    classes = get_icon_backend().get_css_classes(str(icon_name), size=size, extra_class=extra_class or "")
    if not classes:
        return mark_safe("")
    return mark_safe(f'<i class="{classes}"></i>')
