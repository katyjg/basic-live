# Simplified Django Instance Configuration via basiclive.utils.configure

BasicLIVE is distributed as a pluggable, reusable framework across light-source facility deployments (ADR-0001). Downstream instance applications (with `vanilla/settings.py` serving as the canonical reference implementation) previously maintained extensive framework boilerplate within their `settings.py`.

We decided to introduce a centralized framework configuration entrypoint, `basiclive.utils.configure(settings: dict)`, invoked at the bottom of instance `settings.py` files via `configure(globals())`.

## Context and Problem

Previously, each deployment had to manually configure and synchronize:
- Required third-party and internal applications (`crispy_forms`, `crispy_bootstrap5`, `crisp_modals`, `itemlist`, `reportcraft`, `basiclive.core.lims`, `basiclive.core.api`, `basiclive.core.acl`).
- Brittle optional application inclusion and exclusion lists (`schedule`, `crm`, `notebooks`, `publications`) via manual list operations (`INSTALLED_APPS.remove(...)`).
- Extensive ReportCraft functions (`REPORTCRAFT_FUNCTIONS`), apps (`REPORTCRAFT_APPS`), and access mixins (`REPORTCRAFT_MIXINS`).
- Framework presentation standards: Crispy template packs (`CRISPY_ALLOWED_TEMPLATE_PACKS`, `CRISPY_TEMPLATE_PACK`), Content Security Policy (`SECURE_CSP`), auth user model (`AUTH_USER_MODEL = 'lims.User'`), and icon backend (`BASICLIVE_ICON_BACKEND`).
- API and JWT token authentication policies (`REST_FRAMEWORK`, `SIMPLE_JWT`).
- Standard static asset paths (`STATIC_ROOT`, `STATICFILES_DIRS` with framework assets) and media storage directories (`MEDIA_ROOT`).
- Middleware pipeline ordering requirements (e.g. `TrustedAccessMiddleware` prepended before security middleware; `APIAuthenticationMiddleware` and `ProjectContextMiddleware` appended).
- Deployment-specific configuration loading via `local/settings.py`.

This redundancy caused configuration drift across facility installations, elevated upgrade friction when framework dependencies or middleware requirements changed, and created risks of runtime misconfiguration.

## Decision

Downstream instance `settings.py` files now define only site-specific metadata, database credentials, and optional feature flags, delegating framework wiring to `basiclive.utils.configure(globals())`.

1. **Framework Defaults (`EXTRA_SETTINGS`)**:
   - Injects standard settings for Crispy Forms (Bootstrap 5), ReportCraft functions and mixins, CSP directives, custom user model (`lims.User`), default icon backend (`ThemifyBackend`), and REST Framework / SimpleJWT authentication.

2. **Static and Media Directory Derivation**:
   - Automatically derives `STATIC_ROOT`, `STATICFILES_DIRS` (including project static and 3rd-party asset directories), and `MEDIA_ROOT` from `BASE_DIR` and `PROJECT_DIR`.

3. **Local Overrides**:
   - Dynamically imports `local.settings` if present, overriding baseline settings with environment-specific variables.

4. **Dynamic Application Resolution**:
   - Ensures mandatory framework applications (`BASICLIVE_APPS`) are present in `INSTALLED_APPS`.
   - Resolves optional core modules (`USE_CRM`, `USE_SCHEDULE`, `USE_NOTEBOOKS`, `USE_PUBLICATIONS`) enabled by default or toggled through `BASICLIVE_LIMS` dictionary flags.
   - Preserves application ordering and prevents duplicate registrations.

5. **Authentication Backend Assembly**:
   - Inspects `BASICLIVE_AUTH_PROVIDERS` and appends corresponding authentication backends (`django_python3_ldap.auth.LDAPBackend`, `django_cas_ng.backends.CASBackend`).

6. **Middleware Pipeline Injection**:
   - Prepends `basiclive.core.acl.middleware.TrustedAccessMiddleware` at position 0 to enforce network boundary security.
   - Appends `basiclive.core.api.middleware.APIAuthenticationMiddleware` and `basiclive.core.lims.middleware.ProjectContextMiddleware` to ensure consistent request authentication and active project context resolution.

## Consequences

- **Minimal Boilerplate**: Instance `settings.py` files are reduced to essentials (site name, database, local credentials, and feature switches).
- **Centralized Framework Upgrades**: New middleware, core apps, and default framework settings can be rolled out across deployments without requiring manual modifications to every instance repository.
- **Override Flexibility**: Deployments retain control through `local.settings` and pre-`configure` overrides while framework invariants remain guaranteed.
