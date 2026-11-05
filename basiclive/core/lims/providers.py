from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Iterable

import httpx2
from django.core.cache import cache
from django.db import transaction
from django.db.models import Q
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
from basiclive.utils.misc import parse_date_value

logger = logging.getLogger(__name__)

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
    code: str = ""
    name: str = ""
    title: str = ""
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

    def __post_init__(self):
        if not self.code and self.name:
            self.code = self.name
        elif not self.name and self.code:
            self.name = self.code


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


class BaseProjectProvider:
    def __init__(self, cache_ttl: int | None = 900, **options: Any):
        self.cache_ttl = cache_ttl
        self.options = options

    def fetch_projects(self) -> Iterable[ExternalProjectData]:
        raise NotImplementedError("Subclasses must implement fetch_projects()")

    def fetch_user(self, user: User) -> ExternalUserData | None:
        return None

    def _prepare_project_metadata(self, item: ExternalProjectData) -> tuple[Project, bool]:
        source_id = str(item.source_id).strip()
        slug_code = str(item.code or item.name).strip()

        project = Project.objects.filter(source_id=source_id).first()
        created = False
        if not project:
            project = Project.objects.filter(
                Q(code__iexact=slug_code) | Q(code__iexact=slug_code),
                source_id__isnull=True,
            ).first()
            if project:
                project.source_id = source_id
            else:
                project = Project(source_id=source_id, code=slug_code)
                created = True

        project.code = slug_code
        if item.title:
            project.title = item.title.strip()
        if item.start_date is not None or created:
            project.start_date = item.start_date
        if item.end_date is not None or created:
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
        elif item.region_code is None and item.country_code is not None or (
            project.region and project.country and project.region.country_id != project.country_id
        ):
            project.region = None

        return project, created

    def _upsert_project_data(self, item: ExternalProjectData) -> tuple[Project, bool, int, int]:
        """
        Upserts a full ExternalProjectData record and reconciles its complete team roster
        against existing local Users.
        """
        with transaction.atomic():
            project, created = self._prepare_project_metadata(item)
            project.start_date = item.start_date
            project.end_date = item.end_date
            project.external_roster = [m.to_dict() for m in item.members]

            matched_members: dict[int, tuple[User, str]] = {}
            resolved_pi: User | None = None

            for member in item.members:
                role = _normalize_role(member.role)
                existing_user = _find_existing_user(member.username, member.email)
                if not existing_user:
                    continue
                if role == ProjectMembership.Role.PI and resolved_pi is None:
                    resolved_pi = existing_user
                prev = matched_members.get(existing_user.pk)
                if prev is None or _ROLE_RANK.get(role, 0) > _ROLE_RANK.get(prev[1], 0):
                    matched_members[existing_user.pk] = (existing_user, role)

            project.pi = resolved_pi
            project.save()

            memberships_synced = 0
            for existing_user, role in matched_members.values():
                self._apply_user_membership(existing_user, project, role)
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

    @staticmethod
    def _entry_matches_user(entry: dict[str, Any], user: User) -> bool:
        uname = (user.username or "").strip().lower()
        uemail = (user.email or "").strip().lower()
        entry_uname = str(entry.get("username") or "").strip().lower()
        entry_email = str(entry.get("email") or "").strip().lower()
        if uname and entry_uname and uname == entry_uname:
            return True
        if uemail and entry_email and uemail == entry_email:
            return True
        return False

    @staticmethod
    def _update_user_profile(
        user: User,
        source: dict[str, Any] | ExternalUserData,
        *,
        overwrite: bool = False,
    ) -> bool:
        updated = False
        for attr in ("first_name", "last_name", "email", "phone"):
            raw = source.get(attr) if isinstance(source, dict) else getattr(source, attr, "")
            val = str(raw or "").strip()
            if not val:
                continue
            current = getattr(user, attr, "")
            if (overwrite and current != val) or (not overwrite and not current):
                setattr(user, attr, val)
                updated = True
        if updated:
            full_name = f"{user.first_name} {user.last_name}".strip()
            if full_name and (not user.name or user.name == user.username):
                user.name = full_name
            user.save()
        return updated

    @staticmethod
    def _apply_user_membership(user: User, project: Project, role: str) -> None:
        normalized_role = _normalize_role(role)
        membership, created = ProjectMembership.objects.get_or_create(
            user=user,
            project=project,
            defaults={"role": normalized_role},
        )
        if not created and membership.role != normalized_role:
            membership.role = normalized_role
            membership.save(update_fields=["role", "modified"])
        if normalized_role == ProjectMembership.Role.PI and project.pi_id != user.pk:
            project.pi = user
            project.save(update_fields=["pi", "modified"])

    def _match_staged_rosters(self, user: User) -> None:
        for project in Project.objects.exclude(external_roster=[]):
            roster = project.external_roster or []
            if not isinstance(roster, list):
                continue
            best_role: str | None = None
            for entry in roster:
                if not isinstance(entry, dict):
                    continue
                if not self._entry_matches_user(entry, user):
                    continue
                self._update_user_profile(user, entry, overwrite=False)
                role = _normalize_role(entry.get("role"))
                if best_role is None or _ROLE_RANK.get(role, 0) > _ROLE_RANK.get(best_role, 0):
                    best_role = role
            if best_role is not None:
                self._apply_user_membership(user, project, best_role)

    def _reconcile_external_user(self, user: User, ext_user: ExternalUserData) -> None:
        self._update_user_profile(user, ext_user, overwrite=True)

        for item in ext_user.projects:
            explicit_role: str | None = None
            proj_target: ExternalProjectData | str | None = None
            if isinstance(item, tuple) and len(item) == 2:
                proj_target, explicit_role = item[0], _normalize_role(item[1])
            elif isinstance(item, ExternalProjectData):
                proj_target = item

            if isinstance(proj_target, ExternalProjectData):
                with transaction.atomic():
                    project, _ = self._prepare_project_metadata(proj_target)
                    if not project.external_roster and proj_target.members:
                        project.external_roster = [m.to_dict() for m in proj_target.members]
                    project.save()

                    user_role = explicit_role
                    if user_role is None:
                        for m in proj_target.members:
                            if self._entry_matches_user(m.to_dict(), user):
                                candidate = _normalize_role(m.role)
                                if user_role is None or _ROLE_RANK.get(candidate, 0) > _ROLE_RANK.get(user_role, 0):
                                    user_role = candidate
                    self._apply_user_membership(
                        user, project, user_role or ProjectMembership.Role.MEMBER
                    )
            elif isinstance(proj_target, str) and proj_target.strip():
                ident = proj_target.strip()
                project = Project.objects.filter(
                    Q(source_id=ident) | Q(code__iexact=ident)
                ).first()
                if project:
                    self._apply_user_membership(
                        user, project, explicit_role or ProjectMembership.Role.MEMBER
                    )

    def sync_user(self, user: User, force: bool = False) -> bool:
        if not user or not user.username:
            return False

        cache_key = f"lims:sync:user:{user.username.lower()}"
        if not force:
            if self.cache_ttl is None or self.cache_ttl <= 0:
                return False
            if cache.get(cache_key):
                return False

        # Stage 1: Match against staged external_roster entries on local Projects
        self._match_staged_rosters(user)

        # Stage 2: Query external user endpoint if implemented
        fetch_succeeded = True
        try:
            ext_user = self.fetch_user(user)
            if ext_user is not None:
                self._reconcile_external_user(user, ext_user)
        except Exception as exc:
            fetch_succeeded = False
            logger.warning("ProjectProvider.fetch_user(%s) failed: %s", user.username, exc)

        if fetch_succeeded and self.cache_ttl and self.cache_ttl > 0:
            cache.set(cache_key, True, timeout=int(self.cache_ttl))
        return True


class HttpProjectProvider(BaseProjectProvider):
    DEFAULT_FIELD_MAP = {
        "source_id": "source_id",
        "code": "code",
        "name": "name",
        "title": "title",
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

    def _fetch_json(self, endpoint: str) -> Any:
        url = self._build_url(endpoint)
        response = httpx2.get(
            url,
            headers=self.headers,
            timeout=self.timeout,
            follow_redirects=True,
        )
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _extract_list(payload: Any) -> list[Any]:
        if isinstance(payload, dict):
            return list(
                payload.get("projects")
                or payload.get("results")
                or payload.get("data")
                or []
            )
        if isinstance(payload, list):
            return payload
        return []

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
        code_val = raw.get(fm.get("code", "code"))
        name_val = raw.get(fm.get("name", "name"))
        resolved_code = code_val or name_val
        if source_id_val is None or not resolved_code:
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
            code=str(resolved_code).strip(),
            name=str(resolved_code).strip(),
            title=_opt_str("title") or "",
            start_date=parse_date_value(raw.get(fm["start_date"])),
            end_date=parse_date_value(raw.get(fm["end_date"])),
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
        payload = self._fetch_json(self.projects_endpoint)
        records = self._extract_list(payload)
        results: list[ExternalProjectData] = []
        for item in records:
            if isinstance(item, dict):
                parsed = self._parse_project(item)
                if parsed:
                    results.append(parsed)
        return results

    def fetch_user(self, user: User) -> ExternalUserData | None:
        if not self.user_projects_endpoint:
            return None
        endpoint = self.user_projects_endpoint.format(
            username=user.username,
            email=user.email,
            id=user.pk,
        )
        payload = self._fetch_json(endpoint)

        ext_user = ExternalUserData(
            username=user.username,
            email=user.email or "",
            first_name=user.first_name or "",
            last_name=user.last_name or "",
            phone=user.phone or "",
        )
        if isinstance(payload, dict):
            for attr in ("email", "first_name", "last_name", "phone"):
                if payload.get(attr):
                    setattr(ext_user, attr, str(payload[attr]).strip())
        records = self._extract_list(payload)

        fm = self.field_map
        for item in records:
            if not isinstance(item, dict):
                continue
            raw_role = item.get("role") or item.get("user_role") or item.get("membership_role")
            mapped_role = self._map_role(raw_role) if raw_role else ProjectMembership.Role.MEMBER
            parsed_proj = self._parse_project(item)
            if parsed_proj:
                if raw_role and not any(
                    self._entry_matches_user(m.to_dict(), user) for m in parsed_proj.members
                ):
                    parsed_proj.members.append(
                        ExternalMemberData(
                            username=user.username,
                            email=ext_user.email or user.email,
                            first_name=ext_user.first_name or user.first_name,
                            last_name=ext_user.last_name or user.last_name,
                            role=mapped_role,
                            phone=ext_user.phone or user.phone,
                        )
                    )
                ext_user.projects.append(parsed_proj)
            else:
                ident = (
                    item.get(fm["source_id"])
                    or item.get("source_id")
                    or item.get("project")
                    or item.get(fm["name"])
                    or item.get("name")
                )
                if ident is not None:
                    ext_user.projects.append((str(ident).strip(), mapped_role))

        return ext_user


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
