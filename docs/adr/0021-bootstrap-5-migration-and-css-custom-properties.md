# Bootstrap 5 Migration and CSS Custom Properties

BasicLIVE previously vendored Bootstrap 4 SCSS source files and compiled application styles by importing them into `basiclive.scss`, using `crispy-bootstrap4` for form layouts, and relying on legacy Bootstrap 4 data attributes (`data-toggle`, `data-target`, `data-dismiss`) and utility classes.

We decided to migrate the framework frontend to Bootstrap 5 (v5.3.3):
1. **Unvendoring Framework Stylesheet**: Vendored Bootstrap SCSS files (`basiclive/core/lims/static/bootstrap/scss/`) were purged. Instead, standard minified Bootstrap 5.3.3 CSS and JS bundles are distributed via CDN definitions in `assets.json` and linked directly in `lims/base.html`.
2. **Theming via CSS Custom Properties**: `basiclive.scss` was decoupled from Bootstrap SCSS imports. Facility theming and palette overrides (such as `--bs-primary`, `--bs-border-color`, and typography) are now configured directly using Bootstrap 5 CSS variables on `:root` and component scopes.
3. **Form Rendering and Select2**: Upgraded form rendering from `crispy-bootstrap4` to `crispy-bootstrap5` (`CRISPY_TEMPLATE_PACK = 'bootstrap5'`). Third-party Select2 styling was migrated from `select2-bootstrap4` to `select2-bootstrap-5-theme` (v1.3.0) with `{theme: 'bootstrap-5'}` across frontend scripts.
4. **Template and Component Modernization**: All HTML templates, Python forms, and frontend helpers were refactored to modern Bootstrap 5 conventions:
   - Data attributes modernized to `data-bs-toggle`, `data-bs-target`, and `data-bs-dismiss`.
   - Modals modernized with `.btn-close` and `data-bs-dismiss="modal"`.
   - Directional utilities migrated to modern LTR/RTL names (`ms-*`, `me-*`, `ps-*`, `pe-*`, `text-start`, `text-end`, `float-start`, `float-end`).
   - Badges modernized to `badge text-bg-*` and `rounded-pill`.
   - Legacy form structures (`form-row`, `form-group`) replaced with standard grid rows (`row g-2`) and spacing utilities (`mb-3`).
   - Frontend JavaScript helpers (`basiclive-modals.js`, `basiclive-forms.js`, `basiclive-layouts.js`) updated to support native Bootstrap 5 component instances (`bootstrap.Modal`, `bootstrap.Popover`, `bootstrap.Tooltip`) alongside jQuery triggers.
