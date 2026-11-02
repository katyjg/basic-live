from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any, Iterable

import httpx2
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.module_loading import import_string

from basiclive.core.schedule.conf import settings as schedule_settings
from basiclive.core.schedule.models import FacilityMode, FacilityModeType

logger = logging.getLogger(__name__)


@dataclass
class ExternalModeData:
    mode_code: str
    start: datetime
    end: datetime
    source_id: str | None = None
    comments: str = ""


def _ensure_aware(dt: datetime) -> datetime:
    if timezone.is_naive(dt):
        return timezone.make_aware(dt)
    return dt


def _parse_datetime_value(val: Any) -> datetime | None:
    if not val:
        return None
    if isinstance(val, datetime):
        return _ensure_aware(val)
    s = str(val).strip()
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s)
        return _ensure_aware(dt)
    except ValueError:
        parsed = parse_datetime(s)
        if parsed:
            return _ensure_aware(parsed)
    return None


class BaseScheduleProvider:
    ENTITY_TYPES = ("modes", "beamtime", "downtime", "support")
    CANONICAL_MODES = ("normal", "development", "maintenance", "shutdown", "special")
    DEFAULT_MODE_MAP = {
        "N": "normal",
        "NORMAL": "normal",
        "D": "development",
        "DEVELOPMENT": "development",
        "M": "maintenance",
        "MV": "maintenance",
        "M0": "maintenance",
        "MT": "maintenance",
        "MAINTENANCE": "maintenance",
        "X": "shutdown",
        "SHUTDOWN": "shutdown",
        "NS": "special",
        "DS": "special",
        "DST": "special",
        "DS-CSR": "special",
        "SPECIAL": "special",
    }

    def __init__(self, cache_ttl: int | None = 900, **options: Any):
        self.cache_ttl = cache_ttl
        self.options = options
        custom_map = options.get("mode_map") or {}
        self.mode_map: dict[str, str] = {
            **self.DEFAULT_MODE_MAP,
            **{str(k).strip().upper(): str(v).strip().lower() for k, v in custom_map.items()},
        }

    def supports(self, entity_type: str) -> bool:
        if entity_type not in self.ENTITY_TYPES:
            return False
        hook_name = f"fetch_{entity_type}"
        return getattr(type(self), hook_name, None) is not getattr(
            BaseScheduleProvider, hook_name, None
        )

    def translate_mode(self, raw_kind: str | None) -> str | None:
        if not raw_kind:
            return None
        cleaned = str(raw_kind).strip()
        if not cleaned:
            return None
        mapped = self.mode_map.get(cleaned) or self.mode_map.get(cleaned.upper())
        if mapped:
            return mapped.lower()
        lower = cleaned.lower()
        if lower in self.CANONICAL_MODES or FacilityModeType.objects.filter(code=lower).exists():
            return lower
        return None

    def fetch_modes(self, start: date, end: date) -> Iterable[ExternalModeData]:
        raise NotImplementedError("Subclasses must implement fetch_modes()")

    def fetch_beamtime(self, start: date, end: date) -> Iterable[Any]:
        raise NotImplementedError("Subclasses must implement fetch_beamtime()")

    def fetch_downtime(self, start: date, end: date) -> Iterable[Any]:
        raise NotImplementedError("Subclasses must implement fetch_downtime()")

    def fetch_support(self, start: date, end: date) -> Iterable[Any]:
        raise NotImplementedError("Subclasses must implement fetch_support()")

    def _reconcile_modes(self, start: date, end: date, items: Iterable[ExternalModeData]) -> int:
        start_dt = timezone.make_aware(datetime.combine(start, time.min))
        end_dt = timezone.make_aware(datetime.combine(end, time.min))

        mode_types = {m.code: m for m in FacilityModeType.objects.all()}
        seen_source_ids: set[str] = set()
        synced_count = 0

        with transaction.atomic():
            for item in items:
                canonical_code = self.translate_mode(item.mode_code)
                if not canonical_code:
                    continue
                mode_type = mode_types.get(canonical_code)
                if not mode_type:
                    mode_type, _ = FacilityModeType.objects.get_or_create(
                        code=canonical_code,
                        defaults={"description": canonical_code.title()},
                    )
                    mode_types[canonical_code] = mode_type

                st = _ensure_aware(item.start)
                en = _ensure_aware(item.end)
                source_id = (
                    str(item.source_id).strip()
                    if item.source_id
                    else f"mode:{canonical_code}:{st.isoformat()}:{en.isoformat()}"
                )
                seen_source_ids.add(source_id)

                FacilityMode.objects.update_or_create(
                    source_id=source_id,
                    defaults={
                        "mode": mode_type,
                        "start": st,
                        "end": en,
                        "comments": item.comments or "",
                    },
                )
                synced_count += 1

            # Prune stale externally sourced intervals within [start_dt, end_dt]
            stale_qs = FacilityMode.objects.filter(
                source_id__isnull=False,
                end__gt=start_dt,
                start__lt=end_dt,
            ).exclude(source_id__in=seen_source_ids)
            stale_qs.delete()

        return synced_count

    def sync(
        self,
        start: date,
        end: date,
        types: Iterable[str] | None = None,
        force: bool = False,
    ) -> dict[str, int]:
        requested = list(types) if types is not None else [t for t in self.ENTITY_TYPES if self.supports(t)]
        results: dict[str, int] = {t: 0 for t in requested}

        if not force and (self.cache_ttl is None or self.cache_ttl <= 0):
            return results

        def _warn(msg: str) -> None:
            logger.warning(msg)
            warnings.warn(msg)

        for entity_type in requested:
            if not self.supports(entity_type):
                continue
            cache_key = f"schedule:sync:{entity_type}:{start.isoformat()}:{end.isoformat()}"
            if not force and self.cache_ttl and self.cache_ttl > 0 and cache.get(cache_key):
                continue

            try:
                handled = False
                if entity_type == "modes":
                    items = list(self.fetch_modes(start, end))
                    results["modes"] = self._reconcile_modes(start, end, items)
                    handled = True
                if handled and self.cache_ttl and self.cache_ttl > 0:
                    cache.set(cache_key, True, timeout=int(self.cache_ttl))
            except (httpx2.ConnectError, httpx2.NetworkError) as exc:
                _warn(f"Couldn't fetch schedule {entity_type} from upstream provider: {exc}")
            except (httpx2.UnsupportedProtocol, httpx2.InvalidURL) as exc:
                _warn(f"Schedule provider URL must start with 'http://' or 'https://': {exc}")
            except Exception as exc:
                _warn(f"ScheduleProvider sync({entity_type}) failed: {exc}")

        return results


class HttpScheduleProvider(BaseScheduleProvider):
    def __init__(self, cache_ttl: int | None = 900, **options: Any):
        super().__init__(cache_ttl=cache_ttl, **options)
        self.base_url: str = str(options.get("base_url", "")).rstrip("/")
        self.headers: dict[str, str] = dict(options.get("headers") or {})
        self.timeout: float = float(options.get("timeout", 10.0))
        endpoints = dict(options.get("endpoints") or {})
        if not endpoints and options.get("modes_endpoint"):
            endpoints["modes"] = str(options["modes_endpoint"])
        self.endpoints: dict[str, str] = endpoints

    def supports(self, entity_type: str) -> bool:
        return bool(self.endpoints.get(entity_type))

    def _build_url(self, endpoint: str) -> str:
        if endpoint.startswith(("http://", "https://")) or "://" in endpoint:
            return endpoint
        if not self.base_url:
            return endpoint
        return f"{self.base_url}/{endpoint.lstrip('/')}"

    def _fetch_json(self, endpoint_template: str, start: date, end: date) -> Any:
        formatted = endpoint_template.format(start=start.isoformat(), end=end.isoformat())
        url = self._build_url(formatted)
        response = httpx2.get(
            url,
            headers=self.headers,
            timeout=self.timeout,
            follow_redirects=True,
        )
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _extract_list(payload: Any, key: str = "modes") -> list[Any]:
        if isinstance(payload, dict):
            return list(
                payload.get(key)
                or payload.get("results")
                or payload.get("data")
                or []
            )
        if isinstance(payload, list):
            return payload
        return []

    def fetch_modes(self, start: date, end: date) -> list[ExternalModeData]:
        endpoint_template = self.endpoints.get("modes")
        if not endpoint_template:
            return []
        payload = self._fetch_json(endpoint_template, start, end)
        records = self._extract_list(payload, key="modes")

        results: list[ExternalModeData] = []
        for raw in records:
            if not isinstance(raw, dict):
                continue
            raw_kind = raw.get("kind") or raw.get("mode") or raw.get("code")
            canonical = self.translate_mode(raw_kind)
            if not canonical:
                continue
            st = _parse_datetime_value(raw.get("start"))
            en = _parse_datetime_value(raw.get("end"))
            if not st or not en:
                continue
            source_id_val = raw.get("id") or raw.get("source_id")
            comments = str(raw.get("comments") or raw.get("description") or "").strip()
            results.append(
                ExternalModeData(
                    mode_code=canonical,
                    start=st,
                    end=en,
                    source_id=str(source_id_val).strip() if source_id_val is not None else None,
                    comments=comments,
                )
            )
        return results


def _resolve_schedule_provider_class(backend: Any) -> type[BaseScheduleProvider]:
    backend_cls = backend if isinstance(backend, type) else import_string(str(backend))
    if not (isinstance(backend_cls, type) and issubclass(backend_cls, BaseScheduleProvider)):
        raise ValueError(
            f"Invalid SCHEDULE_PROVIDER backend {backend!r}: must subclass BaseScheduleProvider."
        )
    return backend_cls


def get_schedule_provider() -> BaseScheduleProvider | None:
    config = schedule_settings.SCHEDULE_PROVIDER
    if not config:
        return None

    if isinstance(config, BaseScheduleProvider):
        return config
    if isinstance(config, (type, str)):
        backend_cls = _resolve_schedule_provider_class(config)
        return backend_cls()
    if isinstance(config, dict):
        backend_path = config.get("BACKEND")
        if not backend_path:
            raise ValueError("SCHEDULE_PROVIDER dictionary must specify 'BACKEND'.")
        backend_cls = _resolve_schedule_provider_class(backend_path)
        cache_ttl = config.get("CACHE_TTL", 900)
        options = dict(config.get("OPTIONS") or {})
        return backend_cls(cache_ttl=cache_ttl, **options)

    raise ValueError(
        f"Invalid SCHEDULE_PROVIDER: {config!r}. Expected None, dotted path, or dict with BACKEND."
    )
