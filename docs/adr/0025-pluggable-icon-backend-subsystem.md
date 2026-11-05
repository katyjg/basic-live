# Pluggable Icon Backend Subsystem and Semantic Icon Migration

BasicLIVE previously coupled its UI iconography directly to Themify Icons. Template tags (`{% show_icon %}`), Python form button layouts, and view column formatters embedded font-vendor-specific CSS classes (`ti ti-...`) and font-specific sizing classes (`ti-sm`, `ti-md`). This tight coupling prevented facility deployments and downstream installations from adopting alternative icon libraries (such as Bootstrap Icons, FontAwesome, Lucide, or custom SVG sprite packages) without altering hundreds of templates and Python files.

We decided to introduce a pluggable icon backend architecture and migrate all icon usages across BasicLIVE to canonical icon names and standardized framework sizing tokens:

1. **Pluggable Backend Architecture**:
   - Implemented `BaseIconBackend` in `basiclive.core.lims.icons` defining an abstract interface for icon providers:
     - `resolve_icon_name(icon: str) -> str`: Resolves canonical semantic names into provider-specific icon classes.
     - `format_size_class(size: Optional[str]) -> str`: Validates standardized size literals against allowed sizes and formats framework utility classes.
     - `get_css_classes(icon: str, size: Optional[str] = None, extra_class: str = "") -> str`: Assembles the full CSS class string.
     - `get_stylesheet_urls() -> List[str]`: Returns required asset stylesheet URLs or static file paths.
   - Implemented `ThemifyBackend` as the default provider, configured via Django settings (`BASICLIVE_ICON_BACKEND = 'basiclive.core.lims.icons.ThemifyBackend'`). It supports dotted import paths or backend instances resolved via `get_icon_backend()`.
   - Utilizes a hybrid resolution strategy combining a canonical alias dictionary for semantic verbs and domain concepts (e.g. `edit -> ti-pencil`, `delete -> ti-trash`, `support -> ti-headphone-alt`, `areas -> ti-target`) with an automated `{prefix}-{name}` fallback and support for dynamic prefixes (such as `entry-selector-` for Notebooks).

2. **Framework Icon Sizing Tokens**:
   - Standardized on 5 framework sizing tokens: `xs`, `sm`, `md`, `lg`, `xl`.
   - Updated `basiclive.scss` (and compiled `basiclive.min.css`) to define standard utility classes `.bl-icon-{size}` with consistent rem-based font sizes (`0.8rem`, `1.1rem`, `1.5rem`, `2.0rem`, `3.0rem`), reset font-style, and baseline alignment.
   - Retained `.icon-{size}` and legacy `.ti-{size}` as SCSS aliases for backwards compatibility with downstream styles.

3. **Modernized Template Tags and Python Helpers**:
   - Modernized `{% show_icon %}` in `bl_icons.py` to accept plain canonical names (`icon="home"`), standard size tokens (`size="md"`), and modifier classes (`extra_class="text-danger"`), delegating all class rendering to the active backend.
   - Introduced `{% show_icon_css %}` in `bl_icons.py` and embedded it into `<head>` in `lims/base.html` so icon fonts and stylesheets are injected dynamically based on the active backend without hardcoded static links.
   - Implemented `render_icon(icon=None, size=None, extra_class=None, name=None) -> SafeString` in `basiclive.core.lims.icons` for programmatic icon generation in Python forms, help texts, and view formatters.

4. **Complete Codebase Migration**:
   - Audited and cataloged 165+ icon call sites across the framework in `docs/research/icon-call-sites-catalog.md`.
   - Migrated all `{% show_icon %}` calls across all core applications (`lims`, `acl`, `crm`, `schedule`, `notebooks`, `publications`) to canonical names and standard size tokens.
   - Modernized all Python form definitions in `basiclive/core/lims/forms.py` and table transforms in `basiclive/core/lims/views.py` (`movable`) to use `render_icon`.
   - Replaced all raw `<i>` icon tags across templates (`feedback.html`, `container-spreadsheet.html`, `403.html`, `404.html`, `500.html`, `entry.html`).
   - Automated regression tests in `tests/test_icon_backends.py` enforce 0 raw `ti` / `ti-` icon elements remaining in Python modules and Django templates.
