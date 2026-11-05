from typing import Any
from django.conf import settings as django_settings


class AppSettings:
    """
    Dynamic configuration proxy for BasicLIVE applications.

    Resolves settings from a dictionary namespace in django.conf.settings
    (e.g., BASICLIVE_LIMS) with fallback to application defaults.
    Evaluates dynamically on each attribute access to ensure compatibility
    with Django's @override_settings in tests.
    """

    def __init__(self, prefix: str, defaults: dict[str, Any]):
        """
        :param prefix: The application prefix for the settings dictionary,
                       e.g. 'LIMS' for settings.BASICLIVE_LIMS.
                       Can also be passed as a full name like 'BASICLIVE_LIMS'.
        :param defaults: Dictionary of default setting names and values.
        """
        if not prefix.startswith("BASICLIVE_"):
            raw_prefix = prefix.upper()
            namespace = f"BASICLIVE_{raw_prefix}"
        else:
            raw_prefix = prefix.upper().removeprefix("BASICLIVE_")
            namespace = prefix.upper()

        object.__setattr__(self, "_prefix", raw_prefix)
        object.__setattr__(self, "_namespace", namespace)
        object.__setattr__(self, "_defaults", dict(defaults))

    @property
    def namespace(self) -> str:
        return self._namespace

    @property
    def defaults(self) -> dict[str, Any]:
        return self._defaults

    def _resolve_name(self, name: str) -> str | None:
        if not isinstance(name, str):
            return None
        if name in self._defaults:
            return name
        prefix_tag = f"{self._prefix}_"
        if name.startswith(prefix_tag):
            unprefixed = name[len(prefix_tag):]
            if unprefixed in self._defaults:
                return unprefixed
        else:
            prefixed = f"{prefix_tag}{name}"
            if prefixed in self._defaults:
                return prefixed
        return None

    def __getattr__(self, name: str) -> Any:
        resolved_name = self._resolve_name(name)
        if resolved_name is None:
            raise AttributeError(f"Invalid setting '{name}' for '{self._namespace}'")

        user_settings = getattr(django_settings, self._namespace, None)
        if not isinstance(user_settings, dict):
            # Fallback namespace for auth apps e.g. BASICLIVE_AUTH_LDAP <-> BASICLIVE_LDAP
            if self._prefix == "LDAP":
                user_settings = getattr(django_settings, "BASICLIVE_AUTH_LDAP", None)
            elif self._prefix == "CAS":
                user_settings = getattr(django_settings, "BASICLIVE_AUTH_CAS", None)

        if isinstance(user_settings, dict):
            if name in user_settings:
                return user_settings[name]
            if resolved_name in user_settings:
                return user_settings[resolved_name]
            prefix_tag = f"{self._prefix}_"
            prefixed = f"{prefix_tag}{resolved_name}"
            if prefixed in user_settings:
                return user_settings[prefixed]

        return self._defaults[resolved_name]

    def __getitem__(self, name: str) -> Any:
        try:
            return getattr(self, name)
        except AttributeError as e:
            raise KeyError(str(e)) from e

    def get(self, name: str, default: Any = None) -> Any:
        try:
            return getattr(self, name)
        except AttributeError:
            return default

    def __iter__(self):
        return iter(self._defaults)

    def keys(self):
        return self._defaults.keys()

    def __contains__(self, name: str) -> bool:
        return self._resolve_name(name) is not None

    def __dir__(self):
        return sorted(set(super().__dir__()) | set(self._defaults.keys()))

    def __setattr__(self, name: str, value: Any):
        raise AttributeError(
            f"'{self.__class__.__name__}' object attributes are read-only. "
            f"Configure settings via django.conf.settings.{self._namespace} "
            f"or @override_settings."
        )

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} namespace={self._namespace!r}>"


DEFAULTS: dict[str, Any] = {
    "TRUSTED_PROXIES": 2,
    "PDF_TEMP_PREFIX": "render_pdf-",
    "PDF_CACHE_PREFIX": "render-pdf",
    "PDF_CACHE_TIMEOUT": 30,
}

settings = AppSettings("UTILS", DEFAULTS)
