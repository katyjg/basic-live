import json
from pathlib import Path
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import include, path, reverse

from django.core.files.uploadedfile import SimpleUploadedFile

from basiclive.core.notebooks.forms import (
    ENTRY_FORMS,
    DataEntryForm,
    EntryForm,
    FileEntryForm,
    ImageEntryForm,
    NotebookForm,
    SketchEntryForm,
    TextEntryForm,
    VideoEntryForm,
    get_entry_form_class,
)
from basiclive.core.notebooks.models import Entry, EntryType, Notebook
import basiclive.core.notebooks as notebooks_pkg

User = get_user_model()


class NotebookFormsTestCase(TestCase):
    @classmethod
    def setUpClass(cls):
        call_command('migrate', verbosity=0)
        super().setUpClass()

    def setUp(self):
        self.user = User.objects.create_superuser(username="user", password="password123", name="User")
        self.other = User.objects.create_user(username="other", password="password123", name="Other")
        self.admin = User.objects.create_superuser(username="admin", password="password123", name="Admin")

        self.notebook = Notebook.objects.create(
            name="existing-notebook",
            title="Existing Notebook",
            description="Existing description",
        )

    def test_notebook_form_create_init(self):
        """Test NotebookForm initialization for a new notebook."""
        form = NotebookForm(user=self.user)
        self.assertEqual(form.body.title, "Create Notebook")
        self.assertIn("title", form.fields)
        self.assertIn("description", form.fields)

        # Check footer buttons
        buttons = form.footer.layout.fields
        button_labels = [b.content for b in buttons]
        self.assertIn("Save", button_labels)

    def test_notebook_form_edit_init(self):
        """Test NotebookForm initialization for an existing notebook."""
        form = NotebookForm(instance=self.notebook, user=self.user)
        self.assertEqual(form.body.title, "Edit Notebook")
        self.assertEqual(form.initial['title'], "Existing Notebook")

    def test_notebook_form_valid_save(self):
        """Test submitting valid data to NotebookForm saves a new notebook."""
        data = {
            'title': "Brand New Notebook",
            'description': "Details about experiment",
        }
        form = NotebookForm(data=data, user=self.user)
        self.assertTrue(form.is_valid(), form.errors)
        instance = form.save()
        self.assertEqual(instance.title, "Brand New Notebook")

    def test_create_notebook_view_get(self):
        """Test GET request to CreateNotebook renders modal form."""
        self.client.force_login(self.user)
        response = self.client.get(reverse('notebooks:create-notebook'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Create Notebook")

    def test_create_notebook_view_post(self):
        """Test POST request to CreateNotebook creates a notebook and returns json response."""
        self.client.force_login(self.user)
        data = {
            'title': "Modal Created Notebook",
            'description': "Created via crisp-modals view",
        }
        response = self.client.post(reverse('notebooks:create-notebook'), data=data)
        self.assertEqual(response.status_code, 200)
        json_data = response.json()
        self.assertIn('url', json_data)
        self.assertTrue(Notebook.objects.filter(title="Modal Created Notebook").exists())

    def test_update_notebook_view_get_by_owner(self):
        """Test GET request to UpdateNotebook by owner succeeds."""
        self.client.force_login(self.user)
        response = self.client.get(
            reverse('notebooks:notebook-edit', kwargs={'pk': self.notebook.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Edit Notebook")

    def test_update_notebook_view_by_owner(self):
        """Test POST request to UpdateNotebook by owner succeeds."""
        self.client.force_login(self.user)
        data = {
            'title': "Updated Title by Owner",
            'description': "Updated description",
        }
        response = self.client.post(
            reverse('notebooks:notebook-edit', kwargs={'pk': self.notebook.pk}),
            data=data
        )
        self.assertEqual(response.status_code, 200)
        self.notebook.refresh_from_db()
        self.assertEqual(self.notebook.title, "Updated Title by Owner")

    def test_update_notebook_view_permission_denied_for_non_owner(self):
        """Non-owners (who are not superusers) should be denied editing access."""
        self.client.force_login(self.other)
        response = self.client.get(
            reverse('notebooks:notebook-edit', kwargs={'pk': self.notebook.pk})
        )
        self.assertEqual(response.status_code, 403)

    def test_no_is_ajax_references(self):
        """Verify that deprecated request.is_ajax() is completely purged."""
        pkg_dir = Path(notebooks_pkg.__file__).parent
        for py_file in pkg_dir.glob("*.py"):
            with open(py_file, "r") as f:
                content = f.read()
            self.assertNotIn("is_ajax", content, f"Found deprecated is_ajax in {py_file.name}")


class EntryFormsTestCase(TestCase):
    @classmethod
    def setUpClass(cls):
        call_command('migrate', verbosity=0)
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree('notebooks', ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.owner = User.objects.create_user(username="author1", password="password123", name="Author One")
        self.notebook = Notebook.objects.create(
            name="lab-notebook",
            title="Lab Notebook",
        )
        self.text_type, _ = EntryType.objects.get_or_create(name="Text")
        self.image_type, _ = EntryType.objects.get_or_create(name="Image")
        self.video_type, _ = EntryType.objects.get_or_create(name="Video")
        self.sketch_type, _ = EntryType.objects.get_or_create(name="Sketch")
        self.data_type, _ = EntryType.objects.get_or_create(name="Data")
        self.file_type, _ = EntryType.objects.get_or_create(name="File")

    def test_get_entry_form_class(self):
        """Verify get_entry_form_class resolves correctly for strings and EntryType objects."""
        self.assertEqual(get_entry_form_class("text"), TextEntryForm)
        self.assertEqual(get_entry_form_class("TEXT"), TextEntryForm)
        self.assertEqual(get_entry_form_class(self.text_type), TextEntryForm)
        self.assertEqual(get_entry_form_class("image"), ImageEntryForm)
        self.assertEqual(get_entry_form_class("video"), VideoEntryForm)
        self.assertEqual(get_entry_form_class("sketch"), SketchEntryForm)
        self.assertEqual(get_entry_form_class("data"), DataEntryForm)
        self.assertEqual(get_entry_form_class("file"), FileEntryForm)
        self.assertIsNone(get_entry_form_class("unknown"))
        self.assertIsNone(get_entry_form_class(123))

    def test_text_entry_form_create_and_save(self):
        """Test creating and saving a TextEntryForm."""
        form = TextEntryForm(
            data={"text": "### Experimental Log\nSample mounted successfully.", "tags": "beamline, run-1; calibration"},
            user=self.owner,
            notebook=self.notebook,
            kind=self.text_type,
        )
        self.assertEqual(form.body.title, "Create Text Entry")
        self.assertTrue(form.is_valid(), form.errors)
        entry = form.save()
        self.assertEqual(entry.notebook, self.notebook)
        self.assertEqual(entry.author, self.owner)
        self.assertEqual(entry.kind, self.text_type)
        self.assertIn("Experimental Log", entry.text)
        self.assertEqual(entry.tags, ["beamline", "run-1", "calibration"])

    def test_text_entry_form_edit_init(self):
        """Test initializing TextEntryForm on existing instance populates tags and sets edit title."""
        existing = Entry.objects.create(
            notebook=self.notebook,
            author=self.owner,
            kind=self.text_type,
            text="Initial text",
            tags=["sample-A", "shift-1"],
        )
        form = TextEntryForm(instance=existing, user=self.owner)
        self.assertEqual(form.body.title, "Edit Text Entry")
        self.assertEqual(form.initial["tags"], "sample-A, shift-1")

    def test_image_entry_form_requires_file_on_create(self):
        """ImageEntryForm requires a file upload when creating a new entry."""
        form = ImageEntryForm(data={"text": "Caption without image", "tags": ""})
        self.assertFalse(form.is_valid())
        self.assertIn("file", form.errors)

        # Providing a file validates successfully
        from io import BytesIO
        from PIL import Image
        buf = BytesIO()
        Image.new("RGB", (10, 10), color="blue").save(buf, format="PNG")
        uploaded_img = SimpleUploadedFile("crystal.png", buf.getvalue(), content_type="image/png")
        form = ImageEntryForm(
            data={"text": "Sample crystal under microscope", "tags": "microscope"},
            files={"file": uploaded_img},
            user=self.owner,
            notebook=self.notebook,
            kind=self.image_type,
        )
        self.assertTrue(form.is_valid(), form.errors)
        entry = form.save()
        self.assertEqual(entry.kind, self.image_type)
        self.assertEqual(entry.tags, ["microscope"])
        self.assertTrue(bool(entry.file))

    def test_video_entry_form_requires_file_on_create(self):
        """VideoEntryForm requires a file upload on create."""
        form = VideoEntryForm(data={"text": "Video caption", "tags": ""})
        self.assertFalse(form.is_valid())
        self.assertIn("file", form.errors)

        uploaded_vid = SimpleUploadedFile("rotation.mp4", b"fake video bytes", content_type="video/mp4")
        form = VideoEntryForm(
            data={"text": "Automounter rotation", "tags": "video, robot"},
            files={"file": uploaded_vid},
            user=self.owner,
            notebook=self.notebook,
            kind=self.video_type,
        )
        self.assertTrue(form.is_valid(), form.errors)
        entry = form.save()
        self.assertEqual(entry.kind, self.video_type)

    def test_file_entry_form_requires_file_on_create(self):
        """FileEntryForm requires a file upload on create."""
        form = FileEntryForm(data={"text": "File description", "tags": ""})
        self.assertFalse(form.is_valid())
        self.assertIn("file", form.errors)

        uploaded_file = SimpleUploadedFile("results.csv", b"col1,col2\n1,2\n", content_type="text/csv")
        form = FileEntryForm(
            data={"text": "Raw integration results", "tags": "data, raw"},
            files={"file": uploaded_file},
            user=self.owner,
            notebook=self.notebook,
            kind=self.file_type,
        )
        self.assertTrue(form.is_valid(), form.errors)
        entry = form.save()
        self.assertEqual(entry.kind, self.file_type)

    def test_sketch_entry_form_with_base64_data(self):
        """SketchEntryForm converts base64 canvas data to a file."""
        # 1x1 transparent PNG as base64
        base64_png = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        form = SketchEntryForm(
            data={"sketch_data": base64_png, "text": "Hand-drawn crystal mount", "tags": "sketch"},
            user=self.owner,
            notebook=self.notebook,
            kind=self.sketch_type,
        )
        self.assertTrue(form.is_valid(), form.errors)
        entry = form.save()
        self.assertEqual(entry.kind, self.sketch_type)
        self.assertTrue(bool(entry.file))

    def test_sketch_entry_form_missing_input_on_create(self):
        """SketchEntryForm requires either sketch_data or file when creating."""
        form = SketchEntryForm(data={"text": "Empty sketch", "tags": ""})
        self.assertFalse(form.is_valid())
        self.assertIn("file", form.errors)

    def test_data_entry_form_json_cleaning_and_validation(self):
        """DataEntryForm validates and cleans JSON input."""
        valid_json = json.dumps({"data": {"x": [1.0, 2.0, 3.0], "y": [10.55, 20.33, 30.12]}})
        form = DataEntryForm(
            data={"text": valid_json, "tags": "table, json"},
            user=self.owner,
            notebook=self.notebook,
            kind=self.data_type,
        )
        self.assertTrue(form.is_valid(), form.errors)
        entry = form.save()
        self.assertEqual(entry.kind, self.data_type)
        # Should be compact valid JSON
        parsed = json.loads(entry.text)
        self.assertIn("data", parsed)

        # Invalid JSON should fail validation
        invalid_form = DataEntryForm(data={"text": "{invalid json: true", "tags": ""})
        self.assertFalse(invalid_form.is_valid())
        self.assertIn("text", invalid_form.errors)

    def test_tag_cleaning_and_normalization(self):
        """EntryForm clean_tags handles empty strings, duplicates, and mixed delimiters."""
        form = TextEntryForm(data={"text": "Tag test", "tags": "  alpha , beta ; gamma ; ; delta  "})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["tags"], ["alpha", "beta", "gamma", "delta"])

        empty_form = TextEntryForm(data={"text": "No tags", "tags": "   "})
        self.assertTrue(empty_form.is_valid(), empty_form.errors)
        self.assertEqual(empty_form.cleaned_data["tags"], [])
