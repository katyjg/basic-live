import json
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.template import Context, Template, loader
from django.test import RequestFactory, TestCase, override_settings
from django.urls import include, path
from django.utils import timezone


import basiclive.core.notebooks as notebooks_pkg
from basiclive.core.notebooks.models import (
    Annotation,
    Entry,
    EntryType,
    Notebook,
)

User = get_user_model()

from django.contrib.auth import views as auth_views

urlpatterns = [
    path("", include("basiclive.core.lims.urls")),
    path("login/", auth_views.LoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("notebooks/", include("basiclive.core.notebooks.urls")),
    path("reports/", include("reportcraft.urls")),
]


@override_settings(ROOT_URLCONF="basiclive.core.notebooks.tests.test_templates")
class NotebookTemplatesTestCase(TestCase):
    @classmethod
    def setUpClass(cls):
        call_command('migrate', verbosity=0)
        super().setUpClass()

    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(username="testuser", password="password123", name="Test User", is_staff=True)
        self.text_type, _ = EntryType.objects.get_or_create(name="Text")
        self.data_type, _ = EntryType.objects.get_or_create(name="Data")
        self.file_type, _ = EntryType.objects.get_or_create(name="File")
        self.sketch_type, _ = EntryType.objects.get_or_create(name="Sketch")
        self.image_type, _ = EntryType.objects.get_or_create(name="Image")
        self.video_type, _ = EntryType.objects.get_or_create(name="Video")

        self.notebook = Notebook.objects.create(
            name="test-nb",
            title="Test Notebook",
            description="Test notebook description",
        )

        self.today = timezone.localdate(timezone.now())
        self.entry = Entry.objects.create(
            notebook=self.notebook,
            created=timezone.now(),
            author=self.user,
            text="Hello **Markdown** world!",
            kind=self.text_type,
            tags=["sample", "test"],
        )

    def test_notebooks_templatetags_direct(self):
        """Test notebooks template tags and filters directly."""
        template = Template(
            "{% load bl_notebooks %}"
            "{{ text|clean_json }}"
            "{{ dt|simpletime }}"
            "{{ dt|timeish }}"
            "{{ data|json }}"
        )
        ctx = Context({
            "text": '{"a": 1}',
            "dt": timezone.now(),
            "data": {"key": "value"},
        })
        rendered = template.render(ctx)
        self.assertIn('"a":1', rendered)
        self.assertIn('"key": "value"', rendered)

    def test_load_data_and_plot_axes_tags(self):
        """Test load_data and plot_axes templatetags on tabular data entry."""
        table_json = json.dumps({
            "headers": ["Time", "Intensity", "Label"],
            "data": {
                "0": [0.0, 1.0, 2.0],
                "1": [10.5, 20.3, 30.1],
                "2": ["A", "B", "C"],
            }
        })
        data_entry = Entry.objects.create(
            notebook=self.notebook,
            created=timezone.now(),
            author=self.user,
            text=table_json,
            kind=self.data_type,
        )
        template = Template(
            "{% load bl_notebooks %}"
            "{% load_data entry as d %}"
            "{% plot_axes entry as axes %}"
            "Headers: {{ d.headers|join:',' }}; Axes: {{ axes|join:',' }}"
        )
        rendered = template.render(Context({"entry": data_entry}))
        self.assertIn("Headers: Time,Intensity,Label", rendered)
        self.assertIn("Axes: Time,Intensity", rendered)

    def test_render_entries_templates(self):
        """Verify all entry kind templates render without syntax errors."""
        request = self.factory.get("/")
        request.user = self.user

        for kind in ["Text", "Data", "File", "Sketch", "Image", "Video"]:
            t = loader.get_template(f"notebooks/entries/{kind.lower()}.html")
            data_text = '{"headers": ["X", "Y"], "data": {"0": [1, 2], "1": [3, 4]}}' if kind == "Data" else "Content"
            entry_obj = Entry.objects.create(
                notebook=self.notebook,
                created=timezone.now(),
                author=self.user,
                text=data_text,
                kind=EntryType.objects.get(name=kind),
            )
            rendered = t.render({"entry": entry_obj, "notebook": self.notebook, "user": self.user}, request)
            self.assertIn(f"entry-{kind}", rendered)
            self.assertIn(f"/notebooks/{self.notebook.pk}/entry/{entry_obj.pk}/edit/", rendered)
            self.assertNotIn("onclick=\"edit_", rendered)

    def test_render_notebook_list_template(self):
        """Verify notebook_list.html renders cleanly."""
        request = self.factory.get("/notebooks/")
        request.user = self.user

        t_list = loader.get_template("notebooks/notebook_list.html")
        rendered = t_list.render({
            "notebooks": Notebook.objects.all(),
        }, request)
        self.assertIn("Notebooks", rendered)
        self.assertIn(self.notebook.title, rendered)

    def test_render_notebook_detail_template(self):
        """Verify notebook.html renders cleanly extending lims/base.html."""
        request = self.factory.get(f"/notebooks/{self.notebook.pk}/")
        request.user = self.user

        t_detail = loader.get_template("notebooks/notebook.html")
        rendered = t_detail.render({
            "notebook": self.notebook,
            "object": self.notebook,
            "entries": [self.entry],
            "user": self.user,
        }, request)
        self.assertIn(self.notebook.title, rendered)
        self.assertIn("notebook-content", rendered)
        self.assertIn(f"/notebooks/{self.notebook.pk}/entry/new/text/", rendered)
        self.assertNotIn('id="entry-editor"', rendered)
        self.assertNotIn('id="editor-body"', rendered)
        self.assertNotIn("submitEntry", rendered)
        self.assertIn("col-lg-9", rendered)
        self.assertIn("col-lg-3", rendered)
        self.assertIn("notebook-sidebar", rendered)
        self.assertIn("notebook-sidebar-calendar", rendered)
        self.assertIn("calendar-offcanvas", rendered)
        self.assertIn("notebook-offcanvas-calendar", rendered)
        self.assertIn('data-bs-toggle="offcanvas"', rendered)
        self.assertIn("$('.calendar-container').myelnCalendar", rendered)

    def test_notebook_detail_template_calendar_context(self):
        """Verify calendar initialization parameters and responsive offcanvas elements."""
        request = self.factory.get(f"/notebooks/{self.notebook.pk}/")
        request.user = self.user
        t_detail = loader.get_template("notebooks/notebook.html")

        # 1. With selected_date and latest_date
        rendered_selected = t_detail.render({
            "notebook": self.notebook,
            "object": self.notebook,
            "entries": [self.entry],
            "user": self.user,
            "selected_date": "2026-09-15",
            "latest_date": "2026-09-19",
        }, request)
        self.assertIn("'currentMonth': \"2026-09-15\"", rendered_selected)
        self.assertIn("'selectedDate': \"2026-09-15\"", rendered_selected)
        self.assertIn('data-bs-target="#calendar-offcanvas"', rendered_selected)
        self.assertIn('aria-controls="calendar-offcanvas"', rendered_selected)
        self.assertIn('class="offcanvas offcanvas-end d-lg-none"', rendered_selected)
        self.assertIn('id="calendar-offcanvas"', rendered_selected)
        self.assertIn('id="notebook-sidebar-calendar"', rendered_selected)
        self.assertIn('id="notebook-offcanvas-calendar"', rendered_selected)

        # 2. With only latest_date (no selected_date)
        rendered_latest = t_detail.render({
            "notebook": self.notebook,
            "object": self.notebook,
            "entries": [self.entry],
            "user": self.user,
            "selected_date": "",
            "latest_date": "2026-09-19",
        }, request)
        self.assertIn("'currentMonth': \"2026-09-19\"", rendered_latest)
        self.assertIn("'selectedDate': \"\"", rendered_latest)

        # 3. Without selected_date or latest_date (empty context fallback)
        rendered_empty = t_detail.render({
            "notebook": self.notebook,
            "object": self.notebook,
            "entries": [self.entry],
            "user": self.user,
        }, request)
        self.assertIn("'currentMonth': \"\"", rendered_empty)
        self.assertIn("'selectedDate': \"\"", rendered_empty)

    def test_bootstrap_5_compliance_in_templates(self):
        """Ensure no legacy Bootstrap 4 classes or obsolete tags exist in templates."""
        templates_dir = Path(notebooks_pkg.__file__).parent / "templates" / "notebooks"
        html_files = list(templates_dir.rglob("*.html"))
        self.assertTrue(len(html_files) > 0, "Template files must exist")

        legacy_patterns = [
            'data-toggle="',
            'text-right',
            'float-right',
            'custom-select',
            '{% load md2 %}',
        ]

        for path in html_files:
            content = path.read_text(encoding="utf-8")
            for pattern in legacy_patterns:
                self.assertNotIn(
                    pattern,
                    content,
                    f"Found legacy pattern '{pattern}' in {path.relative_to(templates_dir)}"
                )

    def test_notebooks_js_modal_lifecycle_and_legacy_cleanup(self):
        """Verify notebooks.js and notebooks.min.js implement modal lifecycle and purge legacy functions."""
        static_dir = Path(notebooks_pkg.__file__).parent / "static" / "notebooks"
        js_path = static_dir / "notebooks.js"
        min_js_path = static_dir / "notebooks.min.js"

        self.assertTrue(js_path.exists(), "notebooks.js must exist")
        self.assertTrue(min_js_path.exists(), "notebooks.min.js must exist")

        js_content = js_path.read_text(encoding="utf-8")
        min_js_content = min_js_path.read_text(encoding="utf-8")

        # Required modal lifecycle elements
        required_patterns = [
            "initModalEntryEditors",
            "shown.bs.modal",
            "hidden.bs.modal",
            "initTextModal",
            "initSketchModal",
            "initDataModal",
            "initFileDropzoneModal",
            "NotebookAnnotations",
        ]
        for pat in required_patterns:
            self.assertIn(pat, js_content, f"Expected {pat} in notebooks.js")

        self.assertIn("initModalEntryEditors", min_js_content)
        self.assertIn("shown.bs.modal", min_js_content)
        self.assertIn("NotebookAnnotations", min_js_content)

        # Legacy functions that MUST be purged
        purged_patterns = [
            "function showEditor(",
            "function closeEditor(",
            "function submitEntry(",
            "function prepare_editor(",
            "function createEntry(",
            "entryCreators",
            "entryEditors",
            "window.showEditor",
            "window.closeEditor",
            "window.submitEntry",
            "window.createEntry",
            "function addComment(",
            "function addHighlight(",
            "function delHighlight(",
            "function delComment(",
            "function cancelComment(",
            "function submitComment(",
            "function submitAnnotation(",
            "function markAnnotations(",
            "function markComment(",
            "function unmarkComment(",
            "window.addComment",
            "window.addHighlight",
            "window.delHighlight",
            "window.delComment",
            "window.cancelComment",
            "window.submitComment",
            "window.markComment",
            "window.unmarkComment",
        ]
        for pat in purged_patterns:
            self.assertNotIn(pat, js_content, f"Obsolete pattern '{pat}' found in notebooks.js")
            self.assertNotIn(pat, min_js_content, f"Obsolete pattern '{pat}' found in notebooks.min.js")

    def test_entry_template_annotation_rendering(self):
        """Verify modern entry template renders annotations-data and comment badges."""
        Annotation.objects.create(
            entry=self.entry,
            author=self.user,
            text="Test observation",
            quote="Hello",
        )
        request = self.factory.get(f"/notebooks/{self.notebook.pk}/")
        request.user = self.user

        t_entry = loader.get_template("notebooks/entries/entry.html")
        rendered = t_entry.render({
            "entry": self.entry,
            "notebook": self.notebook,
            "user": self.user,
        }, request)

        # Comment badge with count
        self.assertIn("entry-comment-badge", rendered)
        self.assertIn("comment-count", rendered)
        self.assertIn("1", rendered)

        # Modern annotations-data script tag
        self.assertIn('class="annotations-data"', rendered)
        self.assertIn('type="application/json"', rendered)
        self.assertIn("Test observation", rendered)
        self.assertIn("Hello", rendered)

        # Ensure legacy patterns are absent
        self.assertNotIn("highlight-annotation", rendered)
        self.assertNotIn("comment-annotation", rendered)
        self.assertNotIn('type="text/json"', rendered)

