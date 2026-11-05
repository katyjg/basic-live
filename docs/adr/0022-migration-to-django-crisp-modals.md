# Migration of Modal Form Framework to django-crisp-modals

BasicLIVE previously implemented custom modal handling using an in-house jQuery plugin (`basiclive-modals.js` / `basiclive-modals.min.js`), custom modal templates (`lims/modal/content.html`, `lims/modal/form.html`, `lims/modal/delete.html`), and a custom backend mixin (`AsyncFormMixin` in `basiclive/utils/mixins.py`) paired with Django generic views (`CreateView`, `UpdateView`, `DeleteView`).

Following the migration to Bootstrap 5, we decided to adopt the modal form framework provided by `django-crisp-modals` (`crisp_modals`).

## Context and Decision

1. **Dependency and Configuration**:
   - Added `django-crisp-modals >= 2026.1.0` to `pyproject.toml`.
   - Added `"crisp_modals"` to `INSTALLED_APPS` and wired frontend assets via CDN (`jquery.form.min.js`, `crisp_modals/modals.min.js`).

2. **Template Modernization and Inheritance**:
   - Switched `lims/modal/content.html` to `crisp_modals/modal.html`.
   - Switched `lims/modal/delete.html` to `crisp_modals/delete.html`.
   - Re-based `lims/modal/form.html` on `crisp_modals/form.html`.
   - Configured `$('#modal-target').initModal(...)` in `lims/base.html`.

3. **Frontend Helper Consolidation**:
   - Retired and purged `basiclive-modals.js` and `basiclive-modals.min.js`.
   - Moved string utility functions (`slugify`, `strip`) into `basiclive-spreadsheet.js` and recompiled `basiclive-spreadsheet.min.js`.
   - Ensured modal templates depending on `slugify` (such as `lims/forms/group-edit.html`) explicitly load `basiclive-spreadsheet.min.js` via `modal_assets`.

4. **View Migration across Apps**:
   - Systematically migrated modal views across `lims`, `crm`, `acl`, and `schedule` to inherit from `crisp_modals.views` (`ModalCreateView`, `ModalUpdateView`, `ModalDeleteView`, `ModalFormView`).
   - Standardized modal delete views to override `confirmed(*args, **kwargs)` for post-deletion actions and activity logging, returning clean JSON responses.
   - Replaced custom `AsyncFormMixin` with an alias inheriting from `crisp_modals.views.AjaxFormMixin` that emits a `DeprecationWarning`.

5. **Modal Form Inheritance and Semantic Layout Classes**:
   - Refactored all modal forms across `lims`, `crm`, `acl`, and `schedule` to inherit from `crisp_modals.forms.ModalModelForm` (or `ModalForm`).
   - Eliminated boilerplate manual instantiations of `self.body = BodyHelper(self)` and `self.footer = FooterHelper(self)`, allowing `ModalModelForm.__init__` to initialize body and footer helpers automatically with sensible defaults.
   - Replaced custom grid wrappers (`Div(..., css_class="col-*")` and `Div(..., css_class="row")`) with semantic layout components provided by `crisp_modals.forms`:
     - `Row`: semantic form row wrapper.
     - `FullWidth` (`col-12`), `HalfWidth` (`col-6`), `ThirdWidth` (`col-4`), `QuarterWidth` (`col-3`), `SixthWidth` (`col-2`), `TwoThirdWidth` (`col-8`), `ThreeQuarterWidth` (`col-9`), `FiveSixthWidth` (`col-10`).
     - `Button`: styled button wrapper extending Crispy's `StrictButton`.
     - Standardized modal action buttons via `self.footer.set_buttons(...)`.
   - Aliased `BodyHelper` and `FooterHelper` in `basiclive.core.lims.forms` to their `crisp_modals.forms` counterparts to maintain backwards compatibility for host applications and custom extensions.
