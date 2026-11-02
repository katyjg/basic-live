from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Iterable

import httpx2
from django.db import transaction
from django.db.models import Q
from django.utils.dateparse import parse_date, parse_datetime
from django.utils.module_loading import import_string

from basiclive.core.lims.conf import settings as lims_settings
from basiclive.core.lims.models import (
    Country,
    Project,
    ProjectMembership,
    ProjectType,
    Region,
    User,
)

logger = logging.getLogger(__name__)


@dataclass
class ExternalMemberData:
    username: str = ""
    email: str = ""
    first_name: str = ""
    last_name: str = ""
    role: str = ProjectMembership.Role.MEMBER
    phone: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "username": self.username or "",
            "email": self.email or "",
            "first_name": self.first_name or "",
            "last_name": self.last_name or "",
            "role": _normalize_role(self.role),
            "phone": self.phone or "",
        }


@dataclass
class ExternalProjectData:
    source_id: str
    name: str
    start_date: date | None = None
    end_date: date | None = None
    kind: str | None = None
    alias: str | None = None
    contact_person: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    organisation: str | None = None
    department: str | None = None
    address: str | None = None
    city: str | None = None
    region_code: str | None = None
    country_code: str | None = None
    postal_code: str | None = None
    members: list[ExternalMemberData] = field(default_factory=list)


@dataclass
class ExternalUserData:
    username: str
    email: str = ""
    first_name: str = ""
    last_name: str = ""
    phone: str = ""
    projects: list[ExternalProjectData | tuple[str, str]] = field(default_factory=list)


def _resolve_country(country_code: str | None) -> Country | None:
    if not country_code:
        return None
    code = country_code.strip()
    if not code:
        return None
    return Country.objects.filter(
        Q(alpha2__iexact=code) | Q(alpha3__iexact=code) | Q(name__iexact=code)
    ).first()


def _resolve_region(region_code: str | None, country: Country | None = None) -> Region | None:
    if not region_code:
        return None
    code = region_code.strip()
    if not code:
        return None
    qs = Region.objects.all()
    if country:
        qs = qs.filter(country=country)
        prefixed = f"{country.alpha2}-{code}"
        query = Q(code__iexact=code) | Q(code__iexact=prefixed) | Q(name__iexact=code)
    else:
        query = Q(code__iexact=code) | Q(name__iexact=code)
    return qs.filter(query).first()


def _find_existing_user(username: str = "", email: str = "") -> User | None:
    uname = (username or "").strip()
    if uname:
        user = User.objects.filter(username__iexact=uname).first()
        if user:
            return user
    mail = (email or "").strip()
    if mail:
        user = User.objects.filter(email__iexact=mail).first()
        if user:
            return user
    return None


_ROLE_RANK = {
    ProjectMembership.Role.MEMBER: 1,
    ProjectMembership.Role.CO_INVESTIGATOR: 2,
    ProjectMembership.Role.PI: 3,
}


def _normalize_role(role: str | None) -> str:
    if not role:
        return ProjectMembership.Role.MEMBER
    valid_roles = {choice for choice, _ in ProjectMembership.Role.choices}
    role_upper = role.strip().upper()
    if role_upper in valid_roles:
        return role_upper
    if role_upper in ("CO_I", "CO-I", "COINVESTIGATOR"):
        return ProjectMembership.Role.CO_INVESTIGATOR
    return ProjectMembership.Role.MEMBER


class BaseProjectProvider:
    def __init__(self, cache_ttl: int | None = 900, **options: Any):
        self.cache_ttl = cache_ttl
        self.options = options

    def fetch_projects(self) -> Iterable[ExternalProjectData]:
        raise NotImplementedError("Subclasses must implement fetch_projects()")

    def fetch_user(self, user: User) -> ExternalUserData | None:
        return None

    def _upsert_project_data(self, item: ExternalProjectData) -> tuple[Project, bool, int, int]:
        """
        Upserts a single ExternalProjectData record and reconciles memberships for existing users.
        Returns (project, created, memberships_synced, memberships_removed).
        """
        source_id = str(item.source_id).strip()
        slug_name = str(item.name).strip()

        with transaction.atomic():
            project = Project.objects.filter(source_id=source_id).first()
            created = False
            if not project:
                # Fallback to matching an unlinked local project by name on initial link
                project = Project.objects.filter(
                    name__iexact=slug_name, source_id__isnull=True
                ).first()
                if project:
                    project.source_id = source_id
                else:
                    project = Project(source_id=source_id, name=slug_name)
                    created = True

            project.name = slug_name
            project.start_date = item.start_date
            project.end_date = item.end_date

            for attr in (
                "alias",
                "contact_person",
                "contact_email",
                "contact_phone",
                "organisation",
                "department",
                "address",
                "city",
                "postal_code",
            ):
                val = getattr(item, attr, None)
                if val is not None:
                    setattr(project, attr, val)

            if item.kind:
                kind_obj = ProjectType.objects.filter(name__iexact=item.kind.strip()).first()
                if kind_obj:
                    project.kind = kind_obj

            country = _resolve_country(item.country_code)
            if country:
                project.country = country
            region = _resolve_region(item.region_code, country=project.country)
            if region:
                project.region = region
                if not project.country:
                    project.country = region.country
            elif item.region_code is None or (
                project.region and project.country and project.region.country_id != project.country_id
            ):
                project.region = None

            project.external_roster = [m.to_dict() for m in item.members]

            # Match members against already existing Users without creating new Users
            matched_members: dict[int, tuple[User, str]] = {}
            resolved_pi: User | None = None

            for member in item.members:
                role = _normalize_role(member.role)
                existing_user = _find_existing_user(member.username, member.email)
                if not existing_user:
                    continue
                if role == ProjectMembership.Role.PI and resolved_pi is None:
                    resolved_pi = existing_user
                # Keep highest precedence role if a user appears multiple times
                prev = matched_members.get(existing_user.pk)
                if prev is None or _ROLE_RANK.get(role, 0) > _ROLE_RANK.get(prev[1], 0):
                    matched_members[existing_user.pk] = (existing_user, role)

            project.pi = resolved_pi
            project.save()

            memberships_synced = 0
            for existing_user, role in matched_members.values():
                membership, m_created = ProjectMembership.objects.get_or_create(
                    user=existing_user,
                    project=project,
                    defaults={"role": role},
                )
                if not m_created and membership.role != role:
                    membership.role = role
                    membership.save(update_fields=["role", "modified"])
                memberships_synced += 1

            stale_qs = ProjectMembership.objects.filter(project=project).exclude(
                user_id__in=list(matched_members.keys())
            )
            memberships_removed, _ = stale_qs.delete()

        return project, created, memberships_synced, memberships_removed

    def sync_projects(self) -> dict[str, int]:
        stats = {
            "created": 0,
            "updated": 0,
            "memberships_synced": 0,
            "memberships_removed": 0,
        }
        try:
            items = list(self.fetch_projects())
        except Exception as exc:
            logger.warning("ProjectProvider.fetch_projects() failed: %s", exc)
            return stats

        for item in items:
            _, created, m_synced, m_removed = self._upsert_project_data(item)
            if created:
                stats["created"] += 1
            else:
                stats["updated"] += 1
            stats["memberships_synced"] += m_synced
            stats["memberships_removed"] += m_removed

        return stats


def _parse_date_value(val: Any) -> date | None:
    if not val:
        return None
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    s = str(val).strip()
    if not s:
        return None
    parsed_d = parse_date(s[:10])
    if parsed_d:
        return parsed_d
    parsed_dt = parse_datetime(s)
    if parsed_dt:
        return parsed_dt.date()
    return None


class HttpProjectProvider(BaseProjectProvider):
    DEFAULT_FIELD_MAP = {
        "source_id": "source_id",
        "name": "name",
        "start_date": "start_date",
        "end_date": "end_date",
        "kind": "kind",
        "alias": "alias",
        "contact_person": "contact_person",
        "contact_email": "contact_email",
        "contact_phone": "contact_phone",
        "organisation": "organisation",
        "department": "department",
        "address": "address",
        "city": "city",
        "region_code": "region_code",
        "country_code": "country_code",
        "postal_code": "postal_code",
        "members": "members",
    }
    DEFAULT_ROLE_MAP = {
        "PI": ProjectMembership.Role.PI,
        "CO_INVESTIGATOR": ProjectMembership.Role.CO_INVESTIGATOR,
        "CO_I": ProjectMembership.Role.CO_INVESTIGATOR,
        "MEMBER": ProjectMembership.Role.MEMBER,
        "USER": ProjectMembership.Role.MEMBER,
    }

    def __init__(self, cache_ttl: int | None = 900, **options: Any):
        super().__init__(cache_ttl=cache_ttl, **options)
        self.base_url: str = str(options.get("base_url", "")).rstrip("/")
        self.headers: dict[str, str] = dict(options.get("headers") or {})
        self.timeout: float = float(options.get("timeout", 10.0))
        self.projects_endpoint: str = str(options.get("projects_endpoint", "/projects/active/"))
        self.user_projects_endpoint: str | None = options.get("user_projects_endpoint")
        self.field_map: dict[str, str] = {
            **self.DEFAULT_FIELD_MAP,
            **(options.get("field_map") or {}),
        }
        self.role_map: dict[str, str] = {
            **self.DEFAULT_ROLE_MAP,
            **(options.get("role_map") or {}),
        }

    def _build_url(self, endpoint: str) -> str:
        if endpoint.startswith(("http://", "https://")):
            return endpoint
        return f"{self.base_url}/{endpoint.lstrip('/')}"

    def _map_role(self, raw_role: Any) -> str:
        if not raw_role:
            return ProjectMembership.Role.MEMBER
        key = str(raw_role).strip()
        mapped = self.role_map.get(key) or self.role_map.get(key.upper())
        return _normalize_role(mapped or key)

    def _parse_member(self, raw: dict[str, Any]) -> ExternalMemberData:
        return ExternalMemberData(
            username=str(raw.get("username") or "").strip(),
            email=str(raw.get("email") or "").strip(),
            first_name=str(raw.get("first_name") or "").strip(),
            last_name=str(raw.get("last_name") or "").strip(),
            role=self._map_role(raw.get("role")),
            phone=str(raw.get("phone") or "").strip(),
        )

    def _parse_project(self, raw: dict[str, Any]) -> ExternalProjectData | None:
        fm = self.field_map
        source_id_val = raw.get(fm["source_id"])
        name_val = raw.get(fm["name"])
        if source_id_val is None or not name_val:
            return None

        raw_members = raw.get(fm["members"]) or []
        members = [
            self._parse_member(m)
            for m in raw_members
            if isinstance(m, dict)
        ]

        def _opt_str(field_key: str) -> str | None:
            mapped_key = fm.get(field_key)
            if not mapped_key:
                return None
            val = raw.get(mapped_key)
            return str(val).strip() if val is not None else None

        return ExternalProjectData(
            source_id=str(source_id_val).strip(),
            name=str(name_val).strip(),
            start_date=_parse_date_value(raw.get(fm["start_date"])),
            end_date=_parse_date_value(raw.get(fm["end_date"])),
            kind=_opt_str("kind"),
            alias=_opt_str("alias"),
            contact_person=_opt_str("contact_person"),
            contact_email=_opt_str("contact_email"),
            contact_phone=_opt_str("contact_phone"),
            organisation=_opt_str("organisation"),
            department=_opt_str("department"),
            address=_opt_str("address"),
            city=_opt_str("city"),
            region_code=_opt_str("region_code"),
            country_code=_opt_str("country_code"),
            postal_code=_opt_str("postal_code"),
            members=members,
        )

    def fetch_projects(self) -> list[ExternalProjectData]:
        url = self._build_url(self.projects_endpoint)
        response = httpx2.get(
            url,
            headers=self.headers,
            timeout=self.timeout,
            follow_redirects=True,
        )
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict):
            records = (
                payload.get("results")
                or payload.get("projects")
                or payload.get("data")
                or []
            )
        elif isinstance(payload, list):
            records = payload
        else:
            records = []

        results: list[ExternalProjectData] = []
        for item in records:
            if isinstance(item, dict):
                parsed = self._parse_project(item)
                if parsed:
                    results.append(parsed)
        return results


def _resolve_provider_class(backend: Any) -> type[BaseProjectProvider]:
    backend_cls = backend if isinstance(backend, type) else import_string(str(backend))
    if not (isinstance(backend_cls, type) and issubclass(backend_cls, BaseProjectProvider)):
        raise ValueError(
            f"Invalid PROJECT_PROVIDER backend {backend!r}: must subclass BaseProjectProvider."
        )
    return backend_cls


def get_project_provider() -> BaseProjectProvider | None:
    config = lims_settings.PROJECT_PROVIDER
    if not config:
        return None

    if isinstance(config, BaseProjectProvider):
        return config
    if isinstance(config, (type, str)):
        backend_cls = _resolve_provider_class(config)
        return backend_cls()
    if isinstance(config, dict):
        backend_path = config.get("BACKEND")
        if not backend_path:
            raise ValueError("PROJECT_PROVIDER dictionary must specify 'BACKEND'.")
        backend_cls = _resolve_provider_class(backend_path)
        cache_ttl = config.get("CACHE_TTL", 900)
        options = dict(config.get("OPTIONS") or {})
        return backend_cls(cache_ttl=cache_ttl, **options)

    raise ValueError(
        f"Invalid PROJECT_PROVIDER: {config!r}. Expected None, dotted path, or dict with BACKEND."
    )
