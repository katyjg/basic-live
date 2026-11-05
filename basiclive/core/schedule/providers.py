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

from basiclive.core.lims.models import Beamline, Project
from basiclive.core.lims.providers import _find_existing_user
from basiclive.utils.misc import parse_date_value
from basiclive.core.schedule.conf import settings as schedule_settings
from basiclive.core.schedule.models import (
    AccessType,
    BeamlineSupport,
    Beamtime,
    Downtime,
    EmailNotification,
    FacilityMode,
    FacilityModeType,
)

logger = logging.getLogger(__name__)


@dataclass
class ExternalModeData:
    mode_code: str
    start: datetime
    end: datetime
    source_id: str | None = None
    comments: str = ""


@dataclass
class ExternalBeamtimeData:
    beamline_acronym: str
    start: datetime
    end: datetime
    project_name: str | None = None
    project_source_id: str | None = None
    access_type: str | None = None
    cancelled: bool | None = None
    comments: str = ""
    source_id: str | None = None


@dataclass
class ExternalDowntimeData:
    start: datetime
    end: datetime
    scope: int = Downtime.SCOPE_CHOICES.FACILITY
    beamline_acronym: str | None = None
    comments: str = ""
    source_id: str | None = None


@dataclass
class ExternalSupportData:
    date: date
    staff_username: str = ""
    staff_email: str = ""
    source_id: str | None = None


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
    _SYNC_PRIORITY = {"modes": 0, "downtime": 1, "beamtime": 2, "support": 3}
    _explicit_cancelled: dict[str, bool] = {}
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

    def _reconcile_beamtime(
        self,
        start: date,
        end: date,
        items: Iterable[ExternalBeamtimeData],
        explicit_cancelled_source_ids: set[str] | None = None,
    ) -> int:
        start_dt = timezone.make_aware(datetime.combine(start, time.min))
        end_dt = timezone.make_aware(datetime.combine(end, time.min))
        now = timezone.now()

        beamlines_by_acronym = {
            bl.acronym.lower(): bl for bl in Beamline.objects.all()
        }
        access_by_name = {
            at.name.lower(): at for at in AccessType.objects.all() if at.name
        }
        default_access = AccessType.objects.first()

        seen_source_ids: set[str] = set()
        synced_count = 0

        with transaction.atomic():
            for item in items:
                bl_key = str(item.beamline_acronym or "").strip().lower()
                beamline = beamlines_by_acronym.get(bl_key)
                if not beamline:
                    continue

                st = _ensure_aware(item.start)
                en = _ensure_aware(item.end)

                project: Project | None = None
                if item.project_source_id:
                    project = Project.objects.filter(
                        source_id=str(item.project_source_id).strip()
                    ).first()
                if not project and item.project_name:
                    project = Project.objects.filter(
                        code__iexact=str(item.project_name).strip()
                    ).first()

                access = default_access
                if item.access_type:
                    matched_access = access_by_name.get(
                        str(item.access_type).strip().lower()
                    )
                    if matched_access:
                        access = matched_access

                source_id = (
                    str(item.source_id).strip()
                    if item.source_id
                    else f"beamtime:{beamline.acronym}:{st.isoformat()}:{en.isoformat()}"
                )
                seen_source_ids.add(source_id)

                if item.cancelled is not None:
                    cancelled = bool(item.cancelled)
                    self._explicit_cancelled[source_id] = cancelled
                    if explicit_cancelled_source_ids is not None:
                        explicit_cancelled_source_ids.add(source_id)
                else:
                    self._explicit_cancelled.pop(source_id, None)
                    cancelled = Downtime.objects.filter(
                        beamline=beamline,
                        end__gt=st,
                        start__lt=en,
                    ).exists()

                bt, created = Beamtime.objects.update_or_create(
                    source_id=source_id,
                    defaults={
                        "project": project,
                        "beamline": beamline,
                        "access": access,
                        "start": st,
                        "end": en,
                        "cancelled": cancelled,
                        "comments": item.comments or "",
                    },
                )
                if created and st > now:
                    EmailNotification.objects.create(beamtime=bt)

                synced_count += 1

            stale_qs = Beamtime.objects.filter(
                source_id__isnull=False,
                end__gt=start_dt,
                start__lt=end_dt,
            ).exclude(source_id__in=seen_source_ids)
            for sid in stale_qs.values_list("source_id", flat=True):
                if sid:
                    self._explicit_cancelled.pop(sid, None)
            stale_qs.delete()

        return synced_count

    def _reconcile_downtime(
        self,
        start: date,
        end: date,
        items: Iterable[ExternalDowntimeData],
        explicit_cancelled_source_ids: set[str] | None = None,
    ) -> int:
        start_dt = timezone.make_aware(datetime.combine(start, time.min))
        end_dt = timezone.make_aware(datetime.combine(end, time.min))

        beamlines_by_acronym = {
            bl.acronym.lower(): bl for bl in Beamline.objects.all()
        }
        active_production_beamlines = list(
            Beamline.objects.filter(active=True, simulated=False)
        )

        seen_source_ids: set[str] = set()
        synced_count = 0

        explicit_false_ids = {
            sid for sid, val in self._explicit_cancelled.items() if val is False
        }
        if explicit_cancelled_source_ids:
            explicit_false_ids |= explicit_cancelled_source_ids

        with transaction.atomic():
            for item in items:
                st = _ensure_aware(item.start)
                en = _ensure_aware(item.end)

                bl_key = str(item.beamline_acronym or "").strip().lower()
                if bl_key:
                    target_bl = beamlines_by_acronym.get(bl_key)
                    if not target_bl:
                        continue
                    target_beamlines = [target_bl]
                    is_expanded = False
                else:
                    target_beamlines = active_production_beamlines
                    is_expanded = True

                for beamline in target_beamlines:
                    if item.source_id:
                        base_sid = str(item.source_id).strip()
                        source_id = (
                            f"{base_sid}:{beamline.acronym}"
                            if is_expanded
                            else base_sid
                        )
                    else:
                        source_id = (
                            f"downtime:{beamline.acronym}:{st.isoformat()}:{en.isoformat()}"
                        )
                    seen_source_ids.add(source_id)

                    Downtime.objects.update_or_create(
                        source_id=source_id,
                        defaults={
                            "beamline": beamline,
                            "scope": item.scope,
                            "start": st,
                            "end": en,
                            "comments": item.comments or "",
                        },
                    )

                    overlap_bt = Beamtime.objects.filter(
                        beamline=beamline,
                        end__gt=st,
                        start__lt=en,
                    )
                    if explicit_false_ids:
                        overlap_bt = overlap_bt.exclude(
                            source_id__in=explicit_false_ids
                        )
                    overlap_bt.update(cancelled=True)

                    synced_count += 1

            stale_qs = Downtime.objects.filter(
                source_id__isnull=False,
                end__gt=start_dt,
                start__lt=end_dt,
            ).exclude(source_id__in=seen_source_ids)
            stale_deleted, _ = stale_qs.delete()

            if stale_deleted:
                explicit_true_ids = {
                    sid for sid, val in self._explicit_cancelled.items() if val is True
                }
                candidates = Beamtime.objects.filter(
                    source_id__isnull=False,
                    cancelled=True,
                    end__gt=start_dt,
                    start__lt=end_dt,
                ).exclude(source_id__in=explicit_true_ids)
                for bt in candidates:
                    has_downtime = Downtime.objects.filter(
                        beamline=bt.beamline,
                        end__gt=bt.start,
                        start__lt=bt.end,
                    ).exists()
                    if not has_downtime:
                        bt.cancelled = False
                        bt.save(update_fields=["cancelled"])

        return synced_count

    def _reconcile_support(
        self,
        start: date,
        end: date,
        items: Iterable[ExternalSupportData],
    ) -> int:
        seen_source_ids: set[str] = set()
        synced_count = 0

        with transaction.atomic():
            for item in items:
                uname = str(item.staff_username or "").strip()
                email = str(item.staff_email or "").strip()
                staff_user = _find_existing_user(username=uname, email=email)

                if not staff_user:
                    ident = uname or email or "unknown"
                    msg = f"BeamlineSupport sync skipped unknown staff user '{ident}' on {item.date.isoformat()}."
                    logger.warning(msg)
                    warnings.warn(msg)
                    continue

                source_id = (
                    str(item.source_id).strip()
                    if item.source_id
                    else f"support:{item.date.isoformat()}:{staff_user.username}"
                )
                seen_source_ids.add(source_id)

                BeamlineSupport.objects.update_or_create(
                    source_id=source_id,
                    defaults={
                        "staff": staff_user,
                        "date": item.date,
                    },
                )
                synced_count += 1

            stale_qs = BeamlineSupport.objects.filter(
                source_id__isnull=False,
                date__gte=start,
                date__lt=end,
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

        explicit_cancelled_source_ids: set[str] = set()
        ordered_types = sorted(
            requested, key=lambda t: self._SYNC_PRIORITY.get(t, 99)
        )

        for entity_type in ordered_types:
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
                elif entity_type == "beamtime":
                    bt_items = list(self.fetch_beamtime(start, end))
                    results["beamtime"] = self._reconcile_beamtime(
                        start,
                        end,
                        bt_items,
                        explicit_cancelled_source_ids=explicit_cancelled_source_ids,
                    )
                    handled = True
                elif entity_type == "downtime":
                    dt_items = list(self.fetch_downtime(start, end))
                    results["downtime"] = self._reconcile_downtime(
                        start,
                        end,
                        dt_items,
                        explicit_cancelled_source_ids=explicit_cancelled_source_ids,
                    )
                    handled = True
                elif entity_type == "support":
                    sup_items = list(self.fetch_support(start, end))
                    results["support"] = self._reconcile_support(start, end, sup_items)
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

    def fetch_beamtime(self, start: date, end: date) -> list[ExternalBeamtimeData]:
        endpoint_template = self.endpoints.get("beamtime")
        if not endpoint_template:
            return []
        payload = self._fetch_json(endpoint_template, start, end)
        records = self._extract_list(payload, key="beamtime")

        results: list[ExternalBeamtimeData] = []
        for raw in records:
            if not isinstance(raw, dict):
                continue
            beamline_acronym = (
                raw.get("beamline")
                or raw.get("beamline_acronym")
                or raw.get("acronym")
            )
            if not beamline_acronym:
                continue
            st = _parse_datetime_value(raw.get("start"))
            en = _parse_datetime_value(raw.get("end"))
            if not st or not en:
                continue
            project_name = (
                raw.get("project")
                or raw.get("project_name")
                or raw.get("proposal")
            )
            project_source_id = (
                raw.get("project_source_id") or raw.get("project_id")
            )
            access_type = (
                raw.get("access_type") or raw.get("access") or raw.get("kind")
            )
            cancelled = (
                bool(raw["cancelled"])
                if "cancelled" in raw and raw["cancelled"] is not None
                else None
            )
            source_id_val = raw.get("id") or raw.get("source_id")
            comments = str(raw.get("comments") or raw.get("description") or "").strip()
            results.append(
                ExternalBeamtimeData(
                    beamline_acronym=str(beamline_acronym).strip(),
                    start=st,
                    end=en,
                    project_name=str(project_name).strip() if project_name else None,
                    project_source_id=(
                        str(project_source_id).strip() if project_source_id else None
                    ),
                    access_type=str(access_type).strip() if access_type else None,
                    cancelled=cancelled,
                    comments=comments,
                    source_id=(
                        str(source_id_val).strip() if source_id_val is not None else None
                    ),
                )
            )
        return results

    def fetch_downtime(self, start: date, end: date) -> list[ExternalDowntimeData]:
        endpoint_template = self.endpoints.get("downtime")
        if not endpoint_template:
            return []
        payload = self._fetch_json(endpoint_template, start, end)
        records = self._extract_list(payload, key="downtime")

        results: list[ExternalDowntimeData] = []
        for raw in records:
            if not isinstance(raw, dict):
                continue
            st = _parse_datetime_value(raw.get("start"))
            en = _parse_datetime_value(raw.get("end"))
            if not st or not en:
                continue
            beamline_acronym = (
                raw.get("beamline")
                or raw.get("beamline_acronym")
                or raw.get("acronym")
            )
            bl_clean = str(beamline_acronym).strip() if beamline_acronym else None

            raw_scope = raw.get("scope")
            if isinstance(raw_scope, int) and raw_scope in (
                Downtime.SCOPE_CHOICES.FACILITY,
                Downtime.SCOPE_CHOICES.BEAMLINE,
            ):
                scope = raw_scope
            elif isinstance(raw_scope, str):
                scope_upper = raw_scope.strip().upper()
                if "BEAMLINE" in scope_upper:
                    scope = Downtime.SCOPE_CHOICES.BEAMLINE
                else:
                    scope = Downtime.SCOPE_CHOICES.FACILITY
            else:
                scope = (
                    Downtime.SCOPE_CHOICES.BEAMLINE
                    if bl_clean
                    else Downtime.SCOPE_CHOICES.FACILITY
                )

            source_id_val = raw.get("id") or raw.get("source_id")
            comments = str(raw.get("comments") or raw.get("description") or "").strip()
            results.append(
                ExternalDowntimeData(
                    start=st,
                    end=en,
                    scope=scope,
                    beamline_acronym=bl_clean,
                    comments=comments,
                    source_id=(
                        str(source_id_val).strip() if source_id_val is not None else None
                    ),
                )
            )
        return results

    def fetch_support(self, start: date, end: date) -> list[ExternalSupportData]:
        endpoint_template = self.endpoints.get("support")
        if not endpoint_template:
            return []
        payload = self._fetch_json(endpoint_template, start, end)
        records = self._extract_list(payload, key="support")

        results: list[ExternalSupportData] = []
        for raw in records:
            if not isinstance(raw, dict):
                continue
            dt_val = parse_date_value(raw.get("date") or raw.get("start"))
            if not dt_val:
                continue
            staff_username = str(
                raw.get("staff_username")
                or raw.get("username")
                or raw.get("staff")
                or ""
            ).strip()
            staff_email = str(
                raw.get("staff_email") or raw.get("email") or ""
            ).strip()
            if not staff_username and not staff_email:
                continue
            source_id_val = raw.get("id") or raw.get("source_id")
            results.append(
                ExternalSupportData(
                    date=dt_val,
                    staff_username=staff_username,
                    staff_email=staff_email,
                    source_id=(
                        str(source_id_val).strip() if source_id_val is not None else None
                    ),
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
