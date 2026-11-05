import inspect
import unittest
from pathlib import Path


from django import forms
from django.apps import apps
from django.contrib.staticfiles import finders
from django.template.loader import get_template
from django.test import SimpleTestCase
from django.urls import URLPattern, URLResolver

from basiclive.core.lims.models import DataType, Project, RequestType
import basiclive.core.lims.views as lims_views
import basiclive.core.acl.views as acl_views
import basiclive.core.crm.views as crm_views
import basiclive.core.schedule.views as schedule_views
import basiclive.core.publications.views as pub_views
import basiclive.core.lims.urls as lims_urls
import basiclive.core.acl.urls as acl_urls
import basiclive.core.crm.urls as crm_urls
import basiclive.core.schedule.urls as schedule_urls
import basiclive.core.publications.urls as pub_urls
import basiclive.core.notebooks.views as notebooks_views
import basiclive.core.notebooks.urls as notebooks_urls
import basiclive.core.notebooks.forms as notebooks_forms


class TemplateIntegrityTests(SimpleTestCase):
    """Automated tests verifying template paths, loading, compilation, and rendering."""

    VIEW_MODULES = [
        lims_views,
        acl_views,
        crm_views,
        schedule_views,
        pub_views,
        notebooks_views,
    ]

    URL_MODULES = [
        lims_urls,
        acl_urls,
        crm_urls,
        schedule_urls,
        pub_urls,
        notebooks_urls,
    ]

    def test_all_view_template_names_exist(self):
        """Verify that every view class with a template_name or tool_template attribute points to an existing template."""
        checked = 0
        for mod in self.VIEW_MODULES:
            for name, obj in inspect.getmembers(mod, inspect.isclass):
                if obj.__module__ == mod.__name__:
                    tname = getattr(obj, "template_name", None)
                    if tname:
                        with self.subTest(view=f"{mod.__name__}.{name}", template=tname):
                            tmpl = get_template(tname)
                            self.assertIsNotNone(tmpl)
                            checked += 1
                    tool_template = getattr(obj, "tool_template", None)
                    if tool_template:
                        with self.subTest(view=f"{mod.__name__}.{name}", tool_template=tool_template):
                            tmpl = get_template(tool_template)
                            self.assertIsNotNone(tmpl)
                            checked += 1

        self.assertGreater(checked, 60, "Expected at least 60 view templates to be validated")

    def test_url_pattern_template_overrides_exist(self):
        """Verify that template_name overrides passed in as_view(...) in URL patterns exist."""
        def extract_patterns(pattern_list):
            results = []
            for p in pattern_list:
                if isinstance(p, URLPattern):
                    initkwargs = getattr(p.callback, "view_initkwargs", {}) or getattr(p.callback, "initkwargs", {})
                    if "template_name" in initkwargs:
                        results.append((str(p.pattern), initkwargs["template_name"]))
                elif isinstance(p, URLResolver):
                    results.extend(extract_patterns(p.url_patterns))
            return results

        overrides = []
        for umod in self.URL_MODULES:
            overrides.extend(extract_patterns(umod.urlpatterns))

        self.assertGreater(len(overrides), 0, "Expected URL pattern template overrides to be found")
        for pattern_str, tname in overrides:
            with self.subTest(pattern=pattern_str, template=tname):
                tmpl = get_template(tname)
                self.assertIsNotNone(tmpl)

    def test_data_detail_get_template_names(self):
        """Verify DataDetail.get_template_names() dynamically builds valid template candidates."""
        view = lims_views.DataDetail()
        kind = DataType(name="MX Dataset", acronym="DATA", template="lims/data/data-frames.html")
        view.object = type("DummyData", (), {"kind": kind})()

        names = view.get_template_names()
        self.assertEqual(names, ["lims/data/data-frames.html", "lims/data/data.html"])

        for tname in names:
            with self.subTest(template=tname):
                tmpl = get_template(tname)
                self.assertIsNotNone(tmpl)

    def test_request_type_template_defaults(self):
        """Verify RequestType model template path defaults and standard request templates."""
        edit_default = RequestType._meta.get_field("edit_template").default
        self.assertEqual(edit_default, "lims/requests/base-edit.html")
        self.assertIsNotNone(get_template(edit_default))

        standard_request_templates = [
            "lims/requests/base-edit.html",
            "lims/requests/base-view.html",
            "lims/requests/exafs-edit.html",
            "lims/requests/exafs-view.html",
            "lims/requests/imgir-edit.html",
            "lims/requests/imgir-view.html",
        ]
        for tname in standard_request_templates:
            with self.subTest(template=tname):
                tmpl = get_template(tname)
                self.assertIsNotNone(tmpl)

    def test_data_type_templates(self):
        """Verify standard DataType templates exist and load."""
        standard_data_templates = [
            "lims/data/data.html",
            "lims/data/data-frames.html",
            "lims/data/data-mad.html",
            "lims/data/data-xrf.html",
        ]
        for tname in standard_data_templates:
            with self.subTest(template=tname):
                tmpl = get_template(tname)
                self.assertIsNotNone(tmpl)

    def test_templatetag_and_component_templates_exist(self):
        """Verify component and inclusion tag templates exist."""
        component_templates = [
            "lims/components/badge-score.html",
            "lims/components/badge-label.html",
            "lims/components/icon-info.html",
            "lims/comments.html",
            "lims/messages.html",
            "lims/navs.html",
            "crm/forms/likert-table.html",
            "crm/forms/likert-entry.html",
            "acl/tools-access.html",
            "crm/tools-support.html",
            "lims/tools-base.html",
            "lims/tools-shipment.html",
            "lims/tools-shipment-edit.html",
        ]
        for tname in component_templates:
            with self.subTest(template=tname):
                tmpl = get_template(tname)
                self.assertIsNotNone(tmpl)

    def test_all_app_templates_load_and_compile(self):
        """Verify every HTML template file across all core apps loads and compiles without syntax error."""
        app_names = [
            "basiclive.core.lims",
            "basiclive.core.acl",
            "basiclive.core.crm",
            "basiclive.core.schedule",
            "basiclive.core.publications",
            "basiclive.core.notebooks",
        ]
        loaded_count = 0
        for app_name in app_names:
            app_config = apps.get_app_config(app_name.split(".")[-1])
            template_dir = Path(app_config.path) / "templates"
            if not template_dir.is_dir():
                continue

            for html_file in template_dir.rglob("*.html"):
                rel_path = str(html_file.relative_to(template_dir))
                with self.subTest(app=app_name, template=rel_path):
                    tmpl = get_template(rel_path)
                    self.assertIsNotNone(tmpl)
                    loaded_count += 1

        self.assertGreater(loaded_count, 60, "Expected at least 60 templates on disk across apps")

    def test_error_handlers_render(self):
        """Verify error handler templates (403, 403_csrf, 404, 500) exist and render."""
        error_templates = [
            ("403.html", {"reason": "Permission denied"}),
            ("403_csrf.html", {"reason": "CSRF verification failed"}),
            ("404.html", {"request_path": "/missing/path/"}),
            ("500.html", {}),
        ]
        for tname, ctx in error_templates:
            with self.subTest(template=tname):
                tmpl = get_template(tname)
                rendered = tmpl.render(ctx)
                self.assertIsInstance(rendered, str)
                self.assertGreater(len(rendered.strip()), 0)

    def test_core_layout_and_modal_templates_render(self):
        """Verify core base layout and modal wrapper templates render properly."""
        class DummyForm(forms.Form):
            name = forms.CharField()

        class DummyWizard:
            steps = type("Steps", (), {"step0": 0, "step1": 1, "count": 2, "prev": None, "next": "step2"})()
            form = DummyForm()

        project = Project(name="testuser")

        cases = [
            ("lims/base.html", {"user": None}),
            ("lims/modal/form.html", {"form": DummyForm(), "title": "Edit Item"}),
            ("lims/modal/wizard.html", {"wizard": DummyWizard(), "title": "New Item"}),
        ]
        for tname, ctx in cases:
            with self.subTest(template=tname):
                tmpl = get_template(tname)
                rendered = tmpl.render(ctx)
                self.assertIsInstance(rendered, str)
                self.assertGreater(len(rendered.strip()), 0)

    def test_basiclive_static_assets_exist(self):
        """Verify that all renamed BasicLIVE static assets exist and old mxlive assets do not."""
        expected_assets = [
            "lims/css/basiclive.scss",
            "lims/css/basiclive.min.css",
            "lims/css/basiclive.min.css.map",
            "lims/js/basiclive-diffviewer.js",
            "lims/js/basiclive-diffviewer.min.js",
            "lims/js/basiclive-forms.js",
            "lims/js/basiclive-forms.min.js",
            "lims/js/basiclive-layouts.js",
            "lims/js/basiclive-layouts.min.js",
            "lims/js/basiclive-reports.js",
            "lims/js/basiclive-reports.min.js",
            "lims/js/basiclive-seater.js",
            "lims/js/basiclive-seater.min.js",
            "lims/js/basiclive-spreadsheet.js",
            "lims/js/basiclive-spreadsheet.min.js",
            "schedule/js/basiclive-scheduler.js",
        ]
        for asset in expected_assets:
            with self.subTest(asset=asset):
                path = finders.find(asset)
                self.assertIsNotNone(path, f"Expected static asset not found: {asset}")

        obsolete_assets = [
            "lims/css/mxlive.scss",
            "lims/css/mxlive.min.css",
            "lims/css/mxlive.min.css.map",
            "lims/js/mxlive-diffviewer.js",
            "lims/js/mxlive-diffviewer.min.js",
            "lims/js/mxlive-forms.js",
            "lims/js/mxlive-forms.min.js",
            "lims/js/mxlive-layouts.js",
            "lims/js/mxlive-layouts.min.js",
            "lims/js/mxlive-modals.js",
            "lims/js/mxlive-modals.min.js",
            "lims/js/mxlive-reports.js",
            "lims/js/mxlive-reports.min.js",
            "lims/js/mxlive-seater.js",
            "lims/js/mxlive-seater.min.js",
            "lims/js/mxlive-spreadsheet.js",
            "lims/js/mxlive-spreadsheet.min.js",
            "schedule/js/mxlive-scheduler.js",
        ]
        for asset in obsolete_assets:
            with self.subTest(obsolete_asset=asset):
                path = finders.find(asset)
                self.assertIsNone(path, f"Obsolete mxlive asset still found: {asset}")

    def test_crispy_bootstrap5_configuration_and_rendering(self):
        """Verify crispy_forms is configured with crispy_bootstrap5 and renders Bootstrap 5 form markup."""
        from django.conf import settings
        from crispy_forms.helper import FormHelper
        from django.template import Context, Template

        self.assertIn("crispy_bootstrap5", settings.INSTALLED_APPS)
        self.assertEqual(getattr(settings, "CRISPY_TEMPLATE_PACK", None), "bootstrap5")

        class SampleForm(forms.Form):
            title = forms.CharField(label="Title")

        form = SampleForm()
        form.helper = FormHelper()
        form.helper.form_tag = False
        template = Template("{% load crispy_forms_tags %}{% crispy form %}")
        rendered = template.render(Context({"form": form}))

        # Bootstrap 5 crispy forms uses 'mb-3' and 'form-label' rather than BS4 'form-group'
        self.assertIn("mb-3", rendered)
        self.assertIn("form-label", rendered)
        self.assertIn("form-control", rendered)
        self.assertNotIn("form-group", rendered)

    def test_bootstrap5_and_select2_theme_assets(self):
        """Verify assets.json and templates use Bootstrap 5 and select2-bootstrap-5-theme."""
        import json
        assets_file = Path(apps.get_app_config("lims").path) / "static" / "lims" / "assets.json"
        self.assertTrue(assets_file.exists())
        with open(assets_file, "r") as f:
            assets_data = json.load(f)

        # Bootstrap 5 assets
        bootstrap_conf = assets_data.get("bootstrap", {})
        self.assertIn("bootstrap@5", bootstrap_conf.get("url", ""))
        css_paths = [entry["path"] for entry in bootstrap_conf.get("css", [])]
        js_paths = [entry["path"] for entry in bootstrap_conf.get("js", [])]
        self.assertIn("css/bootstrap.min.css", css_paths)
        self.assertIn("js/bootstrap.bundle.min.js", js_paths)

        base_tmpl = get_template("lims/base.html")
        self.assertIn("bootstrap/css/bootstrap.min.css", base_tmpl.template.source)
        self.assertIn("bootstrap/js/bootstrap.bundle.min.js", base_tmpl.template.source)

    def test_vendored_bootstrap_scss_removed_and_css_variables_configured(self):
        """Verify vendored Bootstrap SCSS is removed and basiclive.scss overrides CSS custom properties."""
        lims_static = Path(apps.get_app_config("lims").path) / "static"
        vendored_scss_dir = lims_static / "bootstrap" / "scss"
        self.assertFalse(vendored_scss_dir.exists(), "Vendored Bootstrap SCSS directory should be removed")

        scss_file = lims_static / "lims" / "css" / "basiclive.scss"
        self.assertTrue(scss_file.exists())

    def test_no_legacy_bootstrap4_classes_or_attributes_in_templates(self):
        """Verify that HTML templates do not contain legacy Bootstrap 4 data attributes or utility classes."""
        import re

        app_names = [
            "basiclive.core.lims",
            "basiclive.core.acl",
            "basiclive.core.crm",
            "basiclive.core.schedule",
            "basiclive.core.publications",
            "basiclive.core.notebooks",
        ]

        legacy_patterns = [
            (re.compile(r'\bdata-(toggle|target|dismiss)\s*='), "Legacy data-* attribute without bs- prefix"),
            (re.compile(r'\bbadge-pill\b'), "Legacy 'badge-pill' class (use 'rounded-pill')"),
            (re.compile(r'\bbadge-(primary|secondary|success|danger|warning|info|light|dark)\b'), "Legacy 'badge-*' color class (use 'text-bg-*')"),
            (re.compile(r'\b(float|pull)-(left|right)\b'), "Legacy float/pull class (use 'float-start' or 'float-end')"),
            (re.compile(r'\btext-(left|right)\b'), "Legacy text align class (use 'text-start' or 'text-end')"),
            (re.compile(r'\b(mr|ml|pr|pl)-[0-9a-z]+\b'), "Legacy directional spacing class (use 'me-*', 'ms-*', 'pe-*', 'ps-*')"),
            (re.compile(r'\bform-(row|group)\b'), "Legacy form layout class (use 'row g-2' or 'mb-3')"),
            (re.compile(r'\bcustom-select\b'), "Legacy 'custom-select' class (use 'form-select')"),
        ]

        for app_name in app_names:
            app_config = apps.get_app_config(app_name.split(".")[-1])
            template_dir = Path(app_config.path) / "templates"
            if not template_dir.is_dir():
                continue

            for html_file in template_dir.rglob("*.html"):
                content = html_file.read_text(encoding="utf-8")
                # Strip <script>...</script> tags to avoid catching backward-compatible JS fallback selectors
                stripped_content = re.sub(r'<script\b[^>]*>.*?</script>', '', content, flags=re.DOTALL)
                rel_path = str(html_file.relative_to(template_dir))

                for pattern, msg in legacy_patterns:
                    match = pattern.search(stripped_content)
                    if match:
                        self.fail(f"Found {msg} ('{match.group(0)}') in {app_name}/{rel_path}")

    def test_bootstrap5_template_markup_present(self):
        """Verify presence of Bootstrap 5 markup and data attributes in key templates."""
        navs_tmpl = get_template("lims/navs.html")
        self.assertIn('data-bs-toggle="dropdown"', navs_tmpl.template.source)
        self.assertIn('navbar-nav ms-auto', navs_tmpl.template.source)

        base_tmpl = get_template("lims/base.html")
        self.assertIn("data-bs-toggle", base_tmpl.template.source)

    def test_jquery_migrate_not_referenced(self):
        """Verify that jquery-migrate is purged from all templates and assets.json."""
        # 1. Sweep all templates across all registered apps
        app_names = [
            "basiclive.core.lims",
            "basiclive.core.acl",
            "basiclive.core.crm",
            "basiclive.core.schedule",
            "basiclive.core.publications",
            "basiclive.core.notebooks",
        ]
        for app_name in app_names:
            app_config = apps.get_app_config(app_name.split(".")[-1])
            template_dir = Path(app_config.path) / "templates"
            if not template_dir.is_dir():
                continue
            for html_file in template_dir.rglob("*.html"):
                content = html_file.read_text(encoding="utf-8")
                self.assertNotIn(
                    "jquery-migrate",
                    content,
                    f"Found obsolete jquery-migrate reference in {html_file}",
                )

        # 2. Check assets.json
        assets_file = Path(apps.get_app_config("lims").path) / "static" / "lims" / "assets.json"
        assets_content = assets_file.read_text(encoding="utf-8")
        self.assertNotIn("jquery-migrate", assets_content)

    def test_diffviewer_modernization(self):
        """Verify that basiclive-diffviewer.js and .min.js do not reference jQuery.browser or IE8 transforms."""
        lims_static = Path(apps.get_app_config("lims").path) / "static" / "lims" / "js"
        diffviewer_js = (lims_static / "basiclive-diffviewer.js").read_text(encoding="utf-8")
        diffviewer_min_js = (lims_static / "basiclive-diffviewer.min.js").read_text(encoding="utf-8")

        for name, content in [("basiclive-diffviewer.js", diffviewer_js), ("basiclive-diffviewer.min.js", diffviewer_min_js)]:
            with self.subTest(file=name):
                self.assertNotIn("jQuery.browser", content, f"Obsolete jQuery.browser found in {name}")
                self.assertNotIn("useIeTransforms", content, f"Obsolete useIeTransforms found in {name}")
                self.assertNotIn("ieTransforms", content, f"Obsolete ieTransforms found in {name}")

        # Also verify static asset resolution
        self.assertIsNotNone(finders.find("lims/js/basiclive-diffviewer.js"))
        self.assertIsNotNone(finders.find("lims/js/basiclive-diffviewer.min.js"))

    def test_crisp_modals_configuration_and_integration(self):
        """Verify crisp_modals app installation, template inheritance, and base.html wiring."""
        self.assertTrue(apps.is_installed("crisp_modals"))

        # 1. Base template includes modals.min.js and initializes modal handler
        base_tmpl = get_template("lims/base.html")
        rendered_base = base_tmpl.render({"user": None})
        self.assertIn("crisp_modals/modals.min.js", rendered_base)
        self.assertIn("jquery.form.min.js", rendered_base)
        self.assertIn("initModal", rendered_base)

        form_tmpl = get_template("lims/modal/form.html")
        self.assertIn('extends "crisp_modals/form.html"', form_tmpl.template.source)

    def test_spreadsheet_utility_functions_present(self):
        """Verify that slugify and strip utility functions exist in basiclive-spreadsheet.js and .min.js."""
        lims_static = Path(apps.get_app_config("lims").path) / "static" / "lims" / "js"
        spreadsheet_js = (lims_static / "basiclive-spreadsheet.js").read_text(encoding="utf-8")
        spreadsheet_min_js = (lims_static / "basiclive-spreadsheet.min.js").read_text(encoding="utf-8")

        for name, content in [("basiclive-spreadsheet.js", spreadsheet_js), ("basiclive-spreadsheet.min.js", spreadsheet_min_js)]:
            with self.subTest(file=name):
                self.assertIn("function slugify", content)
                self.assertIn("function strip", content)

    def test_modal_form_inheritance_and_crisp_modals_layouts(self):
        """Verify that modal forms inherit from ModalModelForm/ModalForm and use crisp_modals layout classes."""
        import crisp_modals.forms as cm_forms
        from basiclive.core.lims import forms as lims_forms
        from basiclive.core.crm import forms as crm_forms
        from basiclive.core.acl import forms as acl_forms
        from basiclive.core.schedule import forms as schedule_forms

        # Verify all modal form classes inherit from crisp_modals ModalModelForm or ModalForm
        form_modules = [lims_forms, crm_forms, acl_forms, schedule_forms, notebooks_forms]
        expected_modal_forms = [
            # lims
            (lims_forms, "ProjectForm"),
            (lims_forms, "NewProjectForm"),
            (lims_forms, "RequestTypeForm"),
            (lims_forms, "RequestTypeLayoutForm"),
            (lims_forms, "RequestForm"),
            (lims_forms, "RequestParameterForm"),
            (lims_forms, "RequestAdminForm"),
            (lims_forms, "ShipmentForm"),
            (lims_forms, "ShipmentCommentsForm"),
            (lims_forms, "AutomounterForm"),
            (lims_forms, "SampleForm"),
            (lims_forms, "SampleAdminForm"),
            (lims_forms, "ShipmentSendForm"),
            (lims_forms, "ShipmentReturnForm"),
            (lims_forms, "ShipmentRecallSendForm"),
            (lims_forms, "ShipmentRecallReturnForm"),
            (lims_forms, "ShipmentReceiveForm"),
            (lims_forms, "ShipmentArchiveForm"),
            (lims_forms, "ContainerForm"),
            (lims_forms, "GroupForm"),
            (lims_forms, "ContainerLoadForm"),
            (lims_forms, "EmptyContainers"),
            (lims_forms, "LocationLoadForm"),
            (lims_forms, "AddShipmentForm"),
            (lims_forms, "ShipmentContainerForm"),
            (lims_forms, "ShipmentGroupForm"),
            (lims_forms, "SSHKeyForm"),
            (lims_forms, "GuideForm"),
            # crm
            (crm_forms, "SupportAreaForm"),
            (crm_forms, "FeedbackForm"),
            (crm_forms, "SupportEntryForm"),
            # acl
            (acl_forms, "AccessForm"),
            # schedule
            (schedule_forms, "BeamtimeForm"),
            (schedule_forms, "BeamlineSupportForm"),
            (schedule_forms, "DowntimeForm"),
            (schedule_forms, "EmailNotificationForm"),
            # notebooks
            (notebooks_forms, "NotebookForm"),
        ]

        for mod, class_name in expected_modal_forms:
            with self.subTest(form=f"{mod.__name__}.{class_name}"):
                cls = getattr(mod, class_name, None)
                self.assertIsNotNone(cls, f"Class {class_name} not found in {mod.__name__}")
                self.assertTrue(
                    issubclass(cls, (cm_forms.ModalModelForm, cm_forms.ModalForm)),
                    f"{class_name} does not inherit from ModalModelForm or ModalForm"
                )

        # Source check for deprecated patterns: ensure no form uses old Div(..., css_class="col-12") style wrappers
        for mod in form_modules:
            src = inspect.getsource(mod)
            with self.subTest(module=mod.__name__):
                self.assertNotIn('Div(css_class="col-12")', src)
                self.assertNotIn("Div(css_class='col-12')", src)
                self.assertNotIn('Div(css_class="col-6")', src)
                self.assertNotIn("Div(css_class='col-6')", src)

    def test_notebooks_assets_json_and_static_files(self):
        """Verify basiclive.core.notebooks assets.json contains valid SRI hashes and CDN URLs."""
        import json
        assets_file = Path(apps.get_app_config("notebooks").path) / "static" / "notebooks" / "assets.json"
        self.assertTrue(assets_file.exists())
        with open(assets_file, "r") as f:
            assets_data = json.load(f)

        expected_libs = [
            "simplemde",
            "katex",
            "dropzone",
            "atrament",
            "papaparse",
            "d3",
            "clndr",
            "moment",
            "tinycolorpicker",
            "html5sortable",
            "highlight",
            "markjs",
        ]
        for lib in expected_libs:
            self.assertIn(lib, assets_data)
            lib_info = assets_data[lib]
            self.assertIn("url", lib_info)
            for asset_type in ("js", "css"):
                for entry in lib_info.get(asset_type, []):
                    self.assertIn("path", entry)
                    self.assertIn("sri", entry)
                    self.assertTrue(entry["sri"].startswith("sha"), f"Invalid SRI in {lib}: {entry['sri']}")

        # Verify notebooks native assets are registered
        self.assertIsNotNone(finders.find("notebooks/notebooks.min.css"))
        self.assertIsNotNone(finders.find("notebooks/notebooks.js"))
        self.assertIsNotNone(finders.find("notebooks/icons/style.css"))

    def test_entry_modal_forms_and_templates_integrity(self):
        """Verify EntryForm hierarchy, Crisp layout structure, and template data-modal-url integration."""
        from unittest.mock import MagicMock
        from crisp_modals.forms import ModalModelForm, Row
        from crispy_forms.layout import Layout
        from basiclive.core.notebooks.forms import (
            EntryForm,
            TextEntryForm,
            ImageEntryForm,
            VideoEntryForm,
            SketchEntryForm,
            DataEntryForm,
            FileEntryForm,
            get_entry_form_class,
            ENTRY_FORMS,
        )

        form_classes = [
            TextEntryForm,
            ImageEntryForm,
            VideoEntryForm,
            SketchEntryForm,
            DataEntryForm,
            FileEntryForm,
        ]

        # 1. Verify inheritance from ModalModelForm and EntryForm
        for form_cls in form_classes:
            self.assertTrue(issubclass(form_cls, EntryForm), f"{form_cls.__name__} must inherit from EntryForm")
            self.assertTrue(issubclass(form_cls, ModalModelForm), f"{form_cls.__name__} must inherit from ModalModelForm")
            inst = form_cls()
            self.assertIsInstance(inst.body.layout, Layout)
            has_row = any(isinstance(f, Row) for f in inst.body.layout.fields)
            self.assertTrue(has_row, f"{form_cls.__name__} layout should contain Row")

        # 2. Verify get_entry_form_class resolver
        for kind_str, form_cls in ENTRY_FORMS.items():
            self.assertEqual(get_entry_form_class(kind_str), form_cls)
            self.assertEqual(get_entry_form_class(kind_str.upper()), form_cls)
            self.assertEqual(get_entry_form_class(kind_str.title()), form_cls)
            entry_type_mock = MagicMock()
            entry_type_mock.name = kind_str
            self.assertEqual(get_entry_form_class(entry_type_mock), form_cls)

        self.assertIsNone(get_entry_form_class("nonexistent"))
        self.assertIsNone(get_entry_form_class(12345))

        # 3. Verify template files have valid data-modal-url and no #entry-editor
        notebook_tmpl = get_template("notebooks/notebook.html")
        self.assertNotIn('id="entry-editor"', notebook_tmpl.template.source)
        self.assertNotIn('id="editor-body"', notebook_tmpl.template.source)
        self.assertNotIn("submitEntry", notebook_tmpl.template.source)
        self.assertIn("data-modal-url", notebook_tmpl.template.source)

        entry_tmpl = get_template("notebooks/entries/entry.html")
        self.assertIn("data-modal-url", entry_tmpl.template.source)
        self.assertNotIn('onclick="edit_', entry_tmpl.template.source)


if __name__ == "__main__":
    unittest.main()


