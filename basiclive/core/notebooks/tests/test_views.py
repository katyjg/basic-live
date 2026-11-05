import json
import shutil
from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import RequestFactory, TestCase, override_settings
from django.urls import include, path, reverse
from django.utils import timezone


from basiclive.core.notebooks.models import (
    Entry,
    EntryType,
    Notebook,
)
from basiclive.core.notebooks import views

User = get_user_model()


class NotebookViewsTestCase(TestCase):
    @classmethod
    def setUpClass(cls):
        call_command('migrate', verbosity=0)
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree('notebooks', ignore_errors=True)

    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_superuser(username="user", password="password123", name="User")
        self.other = User.objects.create_user(username="other", password="password123", name="Other")
        self.admin = User.objects.create_superuser(username="admin", password="password123", name="Admin")

        for k in ["text", "image", "video", "sketch", "data", "file"]:
            if not EntryType.objects.filter(name__iexact=k).exists():
                EntryType.objects.create(name=k)

        self.text_type = EntryType.objects.filter(name__iexact="text").first()
        self.data_type = EntryType.objects.filter(name__iexact="data").first()
        self.image_type = EntryType.objects.filter(name__iexact="image").first()
        self.video_type = EntryType.objects.filter(name__iexact="video").first()
        self.sketch_type = EntryType.objects.filter(name__iexact="sketch").first()
        self.file_type = EntryType.objects.filter(name__iexact="file").first()

        # Notebooks with various access levels
        self.public_nb = Notebook.objects.create(
            name="public-nb",
            title="Public Notebook",
            description="Public Description",
        )

        self.internal_nb = Notebook.objects.create(
            name="internal-nb",
            title="Internal Notebook",
            description="Internal Description",
        )

        self.private_nb = Notebook.objects.create(
            name="private-nb",
            title="Private Notebook",
            description="Private Description",
        )

        self.other_private_nb = Notebook.objects.create(
            name="other-private-nb",
            title="Other Private Notebook",
            description="Other Private Description",
        )

        # Create entries for testing
        self.now = timezone.now()
        self.today = timezone.localdate(self.now)
        self.yesterday = self.today - timedelta(days=1)
        self.yesterday_dt = self.now - timedelta(days=1)

        self.entry_yesterday = Entry.objects.create(
            notebook=self.private_nb,
            created=self.yesterday_dt,
            author=self.user,
            text="Yesterday entry text",
            kind=self.text_type,
            tags=["sample", "protein"],
        )

        self.entry_today = Entry.objects.create(
            notebook=self.private_nb,
            created=self.now,
            author=self.user,
            text="Today entry text",
            kind=self.text_type,
            tags=["buffer"],
        )

    def test_all_urls_reverse(self):
        """Verify all URL endpoints reverse correctly."""
        self.assertEqual(reverse("notebooks:notebook-list"), "/notebooks/")
        self.assertEqual(reverse("notebooks:create-notebook"), "/notebooks/new/")
        self.assertEqual(reverse("notebooks:notebook-detail", kwargs={"pk": self.public_nb.pk}), f"/notebooks/{self.public_nb.pk}/")
        self.assertEqual(reverse("notebooks:notebook-edit", kwargs={"pk": self.public_nb.pk}), f"/notebooks/{self.public_nb.pk}/edit/")
        self.assertEqual(reverse("notebooks:create-entry", kwargs={"book": self.public_nb.pk, "kind": "text"}), f"/notebooks/{self.public_nb.pk}/entry/new/text/")
        self.assertEqual(reverse("notebooks:edit-entry", kwargs={"book": self.public_nb.pk, "pk": self.entry_today.pk}), f"/notebooks/{self.public_nb.pk}/entry/{self.entry_today.pk}/edit/")
        self.assertEqual(reverse("notebooks:delete-entry", kwargs={"book": self.public_nb.pk, "pk": self.entry_today.pk}), f"/notebooks/{self.public_nb.pk}/entry/{self.entry_today.pk}/delete/")
        self.assertEqual(reverse("notebooks:notebook-dates", kwargs={"pk": self.public_nb.pk}), f"/notebooks/{self.public_nb.pk}/dates/")
        self.assertEqual(
            reverse("notebooks:entry-annotations", kwargs={"book": self.public_nb.pk, "pk": self.entry_today.pk}),
            f"/notebooks/{self.public_nb.pk}/entry/{self.entry_today.pk}/annotations/"
        )
        self.assertEqual(
            reverse("notebooks:entry-annotation-detail", kwargs={"book": self.public_nb.pk, "pk": self.entry_today.pk, "ann_pk": 1}),
            f"/notebooks/{self.public_nb.pk}/entry/{self.entry_today.pk}/annotations/1/"
        )
        self.assertEqual(
            reverse("notebooks:annotate-notebook", kwargs={"book": self.public_nb.pk, "pk": self.entry_today.pk}),
            f"/notebooks/{self.public_nb.pk}/annotate/{self.entry_today.pk}/"
        )
        self.assertEqual(reverse("notebooks:tag-notebook", kwargs={"pk": self.public_nb.pk}), f"/notebooks/{self.public_nb.pk}/tag/")
        self.assertEqual(reverse("notebooks:entry-data", kwargs={"pk": self.entry_today.pk}), f"/notebooks/entry/{self.entry_today.pk}/")

    def test_notebook_access_mixin_anonymous(self):
        """Anonymous user can't see  any notebooks."""
        view = views.NotebookList()
        request = self.factory.get("/notebooks/")
        request.user = MagicMock(is_authenticated=False)
        view.request = request
        qs = view.get_queryset()
        self.assertNotIn(self.public_nb, qs)
        self.assertNotIn(self.internal_nb, qs)
        self.assertNotIn(self.private_nb, qs)
        self.assertNotIn(self.other_private_nb, qs)

    def test_notebook_access_mixin_authenticated_user(self):
        """Authenticated can't see notebooks."""
        view = views.NotebookList()
        request = self.factory.get("/notebooks/")
        request.user = self.other
        view.request = request
        qs = view.get_queryset()
        self.assertNotIn(self.public_nb, qs)
        self.assertNotIn(self.internal_nb, qs)
        self.assertNotIn(self.private_nb, qs)  # member of private_nb
        self.assertNotIn(self.other_private_nb, qs)  # not member, not owner

    def test_notebook_access_mixin_superuser(self):
        """Superuser sees all notebooks."""
        view = views.NotebookList()
        request = self.factory.get("/notebooks/")
        request.user = self.admin
        view.request = request
        qs = view.get_queryset()
        self.assertEqual(set(qs), set(Notebook.objects.all()))

    def test_notebook_edit_mixin(self):
        """Test edit permissions on NotebookEditMixin."""
        view = views.UpdateNotebook()
        view.kwargs = {'pk': self.private_nb.pk}

        # User allowed
        request = self.factory.get(f"/notebooks/{self.private_nb.pk}/edit/")
        request.user = self.user
        view.request = request
        self.assertTrue(view.test_func())

        # Superuser allowed
        request.user = self.admin
        view.request = request
        self.assertTrue(view.test_func())

        # Non-owner denied
        request.user = self.other
        view.request = request
        self.assertFalse(view.test_func())

    def test_notebook_dates_endpoint(self):
        """Test NotebookDates returns JSON list of page dates in given month."""
        self.client.force_login(self.user)
        month_str = f"{self.yesterday.strftime('%Y%m')},{self.today.strftime('%Y%m')}"
        response = self.client.get(
            reverse("notebooks:notebook-dates", kwargs={"pk": self.private_nb.pk}),
            {"months": month_str},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(isinstance(data, list))
        dates = [d["date"] for d in data]
        self.assertIn(self.today.isoformat(), dates)

    def test_notebook_dates_with_active_filters(self):
        """Test NotebookDates applies active list filters (tags, search, kind)."""
        self.client.force_login(self.user)
        month_str = f"{self.yesterday.strftime('%Y%m')},{self.today.strftime('%Y%m')}"

        # Filter by tag 'protein' (only yesterday's entry has it)
        response = self.client.get(
            reverse("notebooks:notebook-dates", kwargs={"pk": self.private_nb.pk}),
            {"months": month_str, "tags": "protein"},
        )
        self.assertEqual(response.status_code, 200)
        dates = [d["date"] for d in response.json()]
        self.assertIn(self.yesterday.isoformat(), dates)
        self.assertNotIn(self.today.isoformat(), dates)

        # Filter by tag 'buffer' (only today's entry has it)
        response = self.client.get(
            reverse("notebooks:notebook-dates", kwargs={"pk": self.private_nb.pk}),
            {"months": month_str, "tags": "buffer"},
        )
        self.assertEqual(response.status_code, 200)
        dates = [d["date"] for d in response.json()]
        self.assertIn(self.today.isoformat(), dates)
        self.assertNotIn(self.yesterday.isoformat(), dates)

        # Search for text in today's entry using SEARCH_VAR ("search")
        response = self.client.get(
            reverse("notebooks:notebook-dates", kwargs={"pk": self.private_nb.pk}),
            {"months": month_str, "search": "Today"},
        )
        self.assertEqual(response.status_code, 200)
        dates = [d["date"] for d in response.json()]
        self.assertIn(self.today.isoformat(), dates)
        self.assertNotIn(self.yesterday.isoformat(), dates)

        # Search for text using 'q' query parameter
        response = self.client.get(
            reverse("notebooks:notebook-dates", kwargs={"pk": self.private_nb.pk}),
            {"months": month_str, "q": "Yesterday"},
        )
        self.assertEqual(response.status_code, 200)
        dates = [d["date"] for d in response.json()]
        self.assertIn(self.yesterday.isoformat(), dates)
        self.assertNotIn(self.today.isoformat(), dates)

        # Filter by kind (text)
        response = self.client.get(
            reverse("notebooks:notebook-dates", kwargs={"pk": self.private_nb.pk}),
            {"months": month_str, "kind__id__exact": self.text_type.pk},
        )
        self.assertEqual(response.status_code, 200)
        dates = [d["date"] for d in response.json()]
        self.assertIn(self.today.isoformat(), dates)
        self.assertIn(self.yesterday.isoformat(), dates)

        # Filter by kind with no entries (data)
        response = self.client.get(
            reverse("notebooks:notebook-dates", kwargs={"pk": self.private_nb.pk}),
            {"months": month_str, "kind__id__exact": self.data_type.pk},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

        # Filter by author
        response = self.client.get(
            reverse("notebooks:notebook-dates", kwargs={"pk": self.private_nb.pk}),
            {"months": month_str, "author__id__exact": self.user.pk},
        )
        self.assertEqual(response.status_code, 200)
        dates = [d["date"] for d in response.json()]
        self.assertIn(self.today.isoformat(), dates)

    def test_notebook_detail_date_filtering(self):
        """Test NotebookDetail date query parameter filtering and context."""
        self.client.force_login(self.user)

        # Filter by today's date
        response = self.client.get(
            reverse("notebooks:notebook-detail", kwargs={"pk": self.private_nb.pk}),
            {"date": self.today.isoformat()},
        )
        self.assertEqual(response.status_code, 200)
        context = response.context_data
        entries = list(context["object_list"])
        self.assertIn(self.entry_today, entries)
        self.assertNotIn(self.entry_yesterday, entries)
        self.assertEqual(context["selected_date"], self.today.isoformat())
        self.assertEqual(context["latest_date"], self.today.isoformat())
        self.assertTrue(context["has_filters"])

        # Filter by yesterday's date
        response = self.client.get(
            reverse("notebooks:notebook-detail", kwargs={"pk": self.private_nb.pk}),
            {"date": self.yesterday.isoformat()},
        )
        self.assertEqual(response.status_code, 200)
        context = response.context_data
        entries = list(context["object_list"])
        self.assertNotIn(self.entry_today, entries)
        self.assertIn(self.entry_yesterday, entries)

    def test_notebook_detail_combined_filters(self):
        """Test NotebookDetail date filtering combined with kind, author, tags, and search."""
        # Create an entry on yesterday by other with data_type and distinct tag
        data_entry = Entry.objects.create(
            notebook=self.private_nb,
            created=self.yesterday_dt,
            author=self.other,
            text=json.dumps({"headers": ["Energy", "Counts"], "data": {"0": [100, 200], "1": [50, 75]}}),
            kind=self.data_type,
            tags=["spectrum"],
        )

        self.client.force_login(self.user)

        # Filter date + kind (data)
        response = self.client.get(
            reverse("notebooks:notebook-detail", kwargs={"pk": self.private_nb.pk}),
            {"date": self.yesterday.isoformat(), "kind__id__exact": self.data_type.pk},
        )
        self.assertEqual(response.status_code, 200)
        entries = list(response.context_data["object_list"])
        self.assertEqual(entries, [data_entry])

        # Filter date + kind (text) on same date
        response = self.client.get(
            reverse("notebooks:notebook-detail", kwargs={"pk": self.private_nb.pk}),
            {"date": self.yesterday.isoformat(), "kind__id__exact": self.text_type.pk},
        )
        self.assertEqual(response.status_code, 200)
        entries = list(response.context_data["object_list"])
        self.assertEqual(entries, [self.entry_yesterday])

        # Filter date + author (other)
        response = self.client.get(
            reverse("notebooks:notebook-detail", kwargs={"pk": self.private_nb.pk}),
            {"date": self.yesterday.isoformat(), "author__id__exact": self.other.pk},
        )
        self.assertEqual(response.status_code, 200)
        entries = list(response.context_data["object_list"])
        self.assertEqual(entries, [data_entry])

        # Filter date + tag
        response = self.client.get(
            reverse("notebooks:notebook-detail", kwargs={"pk": self.private_nb.pk}),
            {"date": self.yesterday.isoformat(), "tags": "spectrum"},
        )
        self.assertEqual(response.status_code, 200)
        entries = list(response.context_data["object_list"])
        self.assertEqual(entries, [data_entry])

        # Filter date + search (via SEARCH_VAR 'search')
        response = self.client.get(
            reverse("notebooks:notebook-detail", kwargs={"pk": self.private_nb.pk}),
            {"date": self.yesterday.isoformat(), "search": "Energy"},
        )
        self.assertEqual(response.status_code, 200)
        entries = list(response.context_data["object_list"])
        self.assertEqual(entries, [data_entry])

        # Filter date + search (via 'q' parameter)
        response = self.client.get(
            reverse("notebooks:notebook-detail", kwargs={"pk": self.private_nb.pk}),
            {"date": self.yesterday.isoformat(), "q": "Energy"},
        )
        self.assertEqual(response.status_code, 200)
        entries = list(response.context_data["object_list"])
        self.assertEqual(entries, [data_entry])

    def test_notebook_detail_date_no_matches(self):
        """Test NotebookDetail with a date having no entries returns empty queryset."""
        self.client.force_login(self.user)
        empty_date = "2000-01-01"
        response = self.client.get(
            reverse("notebooks:notebook-detail", kwargs={"pk": self.private_nb.pk}),
            {"date": empty_date},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context_data["object_list"]), [])
        self.assertEqual(response.context_data["selected_date"], empty_date)
        self.assertTrue(response.context_data["has_filters"])

    def test_notebook_detail_invalid_date(self):
        """Test NotebookDetail ignores invalid date query parameter gracefully."""
        self.client.force_login(self.user)
        response = self.client.get(
            reverse("notebooks:notebook-detail", kwargs={"pk": self.private_nb.pk}),
            {"date": "not-a-valid-date"},
        )
        self.assertEqual(response.status_code, 200)
        context = response.context_data
        entries = list(context["object_list"])
        self.assertIn(self.entry_today, entries)
        self.assertIn(self.entry_yesterday, entries)

    def test_entry_data_endpoint(self):
        """Test EntryData JSON endpoint."""
        self.client.force_login(self.user)
        response = self.client.get(
            reverse("notebooks:entry-data", kwargs={"pk": self.entry_today.pk})
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["text"], "Today entry text")

        # Non-member forbidden to access private entry data
        self.client.force_login(self.other)
        response = self.client.get(
            reverse("notebooks:entry-data", kwargs={"pk": self.entry_today.pk})
        )
        self.assertEqual(response.status_code, 403)

    def test_create_entry_modal_get(self):
        """GET request to CreateEntry renders modal form."""
        self.client.force_login(self.user)
        response = self.client.get(
            reverse("notebooks:create-entry", kwargs={"book": self.public_nb.pk, "kind": "text"})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Create Text Entry")

    def test_create_entry_modal_all_kinds_get(self):
        """GET request to CreateEntry renders modal form for all six entry kinds."""
        self.client.force_login(self.user)
        kinds = ["text", "image", "video", "sketch", "data", "file"]
        for kind in kinds:
            response = self.client.get(
                reverse("notebooks:create-entry", kwargs={"book": self.public_nb.pk, "kind": kind})
            )
            self.assertEqual(response.status_code, 200, f"Failed for kind {kind}")
            self.assertContains(response, f"Create {kind.title()} Entry")

    def test_create_entry_modal_post_file_and_sketch(self):
        """POST request to CreateEntry supports image, video, file uploads, and sketch drawings."""
        self.client.force_login(self.user)

        # 1. Image upload
        img_file = SimpleUploadedFile("test.png", b"fake image bytes", content_type="image/png")
        response = self.client.post(
            reverse("notebooks:create-entry", kwargs={"book": self.public_nb.pk, "kind": "image"}),
            {"file": img_file, "text": "Microscope capture", "tags": "microscope, sample"},
        )
        self.assertEqual(response.status_code, 200)
        img_entry = Entry.objects.filter(notebook=self.public_nb, text="Microscope capture").first()
        self.assertIsNotNone(img_entry)
        self.assertEqual(img_entry.kind, self.image_type)
        self.assertTrue(bool(img_entry.file))
        self.assertEqual(img_entry.tags, ["microscope", "sample"])

        # 2. File upload
        doc_file = SimpleUploadedFile("data.pdf", b"fake pdf bytes", content_type="application/pdf")
        response = self.client.post(
            reverse("notebooks:create-entry", kwargs={"book": self.public_nb.pk, "kind": "file"}),
            {"file": doc_file, "text": "Spec sheet"},
        )
        self.assertEqual(response.status_code, 200)
        file_entry = Entry.objects.filter(notebook=self.public_nb, text="Spec sheet").first()
        self.assertIsNotNone(file_entry)
        self.assertEqual(file_entry.kind, self.file_type)

        # 3. Video upload
        vid_file = SimpleUploadedFile("run.mp4", b"fake video bytes", content_type="video/mp4")
        response = self.client.post(
            reverse("notebooks:create-entry", kwargs={"book": self.public_nb.pk, "kind": "video"}),
            {"file": vid_file, "text": "Reaction video"},
        )
        self.assertEqual(response.status_code, 200)
        vid_entry = Entry.objects.filter(notebook=self.public_nb, text="Reaction video").first()
        self.assertIsNotNone(vid_entry)
        self.assertEqual(vid_entry.kind, self.video_type)

        # 4. Sketch base64 payload
        b64_png = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        response = self.client.post(
            reverse("notebooks:create-entry", kwargs={"book": self.public_nb.pk, "kind": "sketch"}),
            {"sketch_data": b64_png, "text": "Reaction scheme", "tags": "scheme; chemistry"},
        )
        self.assertEqual(response.status_code, 200)
        sketch_entry = Entry.objects.filter(notebook=self.public_nb, text="Reaction scheme").first()
        self.assertIsNotNone(sketch_entry)
        self.assertEqual(sketch_entry.kind, self.sketch_type)
        self.assertTrue(bool(sketch_entry.file))
        self.assertEqual(sketch_entry.tags, ["scheme", "chemistry"])

    def test_entry_views_superuser_and_member_permissions(self):
        """Verify superuser can create/edit in private notebooks and non-members are rejected."""
        # Non-member cannot GET create-entry or edit-entry in private notebook
        self.client.force_login(self.other)
        get_res = self.client.get(
            reverse("notebooks:create-entry", kwargs={"book": self.private_nb.pk, "kind": "text"})
        )
        self.assertEqual(get_res.status_code, 403)

        get_edit_res = self.client.get(
            reverse("notebooks:edit-entry", kwargs={"book": self.private_nb.pk, "pk": self.entry_today.pk})
        )
        self.assertEqual(get_edit_res.status_code, 403)

        # Superuser can create entry in private notebook
        self.client.force_login(self.admin)
        admin_post = self.client.post(
            reverse("notebooks:create-entry", kwargs={"book": self.private_nb.pk, "kind": "text"}),
            {"text": "Superuser note", "tags": "admin"},
        )
        self.assertEqual(admin_post.status_code, 200)
        admin_entry = Entry.objects.filter(notebook=self.private_nb, text="Superuser note").first()
        self.assertIsNotNone(admin_entry)
        self.assertEqual(admin_entry.author, self.admin)

        # Superuser can edit entry created by someone else in private notebook
        admin_edit = self.client.post(
            reverse("notebooks:edit-entry", kwargs={"book": self.private_nb.pk, "pk": self.entry_today.pk}),
            {"text": "Superuser edited note", "tags": "admin-edited"},
        )
        self.assertEqual(admin_edit.status_code, 200)
        self.entry_today.refresh_from_db()
        self.assertEqual(self.entry_today.text, "Superuser edited note")

    def test_tag_normalization_on_entry_creation_and_update(self):
        """Verify tags are normalized from comma/semicolon separated strings into lists."""
        self.client.force_login(self.user)

        # Creation with mixed delimiters and spaces
        response = self.client.post(
            reverse("notebooks:create-entry", kwargs={"book": self.public_nb.pk, "kind": "text"}),
            {"text": "Tag test note", "tags": "  alpha ,  beta; gamma  ; ; delta  "},
        )
        self.assertEqual(response.status_code, 200)
        entry = Entry.objects.filter(notebook=self.public_nb, text="Tag test note").first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.tags, ["alpha", "beta", "gamma", "delta"])

        # Update tags
        response = self.client.post(
            reverse("notebooks:edit-entry", kwargs={"book": self.public_nb.pk, "pk": entry.pk}),
            {"text": "Tag test note", "tags": "omega; psi, chi"},
        )
        self.assertEqual(response.status_code, 200)
        entry.refresh_from_db()
        self.assertEqual(entry.tags, ["omega", "psi", "chi"])


    def test_create_entry_modal_post_success(self):
        """POST request to CreateEntry creates new entry and returns JSON with redirect url."""
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("notebooks:create-entry", kwargs={"book": self.public_nb.pk, "kind": "text"}),
            {"text": "Brand new note", "tags": "log, run-1"},
        )
        self.assertEqual(response.status_code, 200)
        json_data = response.json()
        self.assertIn("url", json_data)
        self.assertTrue(
            Entry.objects.filter(notebook=self.public_nb, text="Brand new note").exists()
        )
        entry = Entry.objects.get(notebook=self.public_nb, text="Brand new note")
        self.assertEqual(entry.author, self.user)
        self.assertEqual(entry.tags, ["log", "run-1"])

    def test_create_entry_data_cleans_json(self):
        """POST request to CreateEntry with data kind cleans JSON payload."""
        raw_json = json.dumps({
            "headers": ["x", "y"],
            "data": {"0": [1.0, 2.0], "1": [3.14159265, 4.14159265]}
        })

        self.client.force_login(self.user)
        response = self.client.post(
            reverse("notebooks:create-entry", kwargs={"book": self.public_nb.pk, "kind": "data"}),
            {"text": raw_json, "tags": "data"},
        )
        self.assertEqual(response.status_code, 200)
        entry = Entry.objects.filter(notebook=self.public_nb, kind=self.data_type).first()
        self.assertIsNotNone(entry)
        parsed = json.loads(entry.text)
        self.assertIn("headers", parsed)

    def test_create_entry_permission_denied(self):
        """Non-editor cannot create entry."""
        self.client.force_login(self.other)
        response = self.client.post(
            reverse("notebooks:create-entry", kwargs={"book": self.private_nb.pk, "kind": "text"}),
            {"text": "Unauthorized note", "tags": ""},
        )
        self.assertEqual(response.status_code, 403)

    def test_update_entry_modal_get(self):
        """GET request to UpdateEntry renders modal form."""
        self.client.force_login(self.user)
        response = self.client.get(
            reverse("notebooks:edit-entry", kwargs={"book": self.private_nb.pk, "pk": self.entry_today.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Edit Text Entry")

    def test_update_entry_modal_post_success(self):
        """POST request to UpdateEntry updates entry content and returns JSON response."""
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("notebooks:edit-entry", kwargs={"book": self.private_nb.pk, "pk": self.entry_today.pk}),
            {"text": "Updated entry content", "tags": "updated, tag2"},
        )
        self.assertEqual(response.status_code, 200)
        self.entry_today.refresh_from_db()
        self.assertEqual(self.entry_today.text, "Updated entry content")
        self.assertEqual(self.entry_today.tags, ["updated", "tag2"])

    def test_update_entry_permission_denied(self):
        """Non-author cannot edit entry."""
        self.client.force_login(self.other)
        response = self.client.post(
            reverse("notebooks:edit-entry", kwargs={"book": self.private_nb.pk, "pk": self.entry_today.pk}),
            {"text": "Hijacked content", "tags": ""},
        )
        self.assertEqual(response.status_code, 403)

    def test_update_historical_entry_forbidden(self):
        """Historical entry from a previous day is immutable and cannot be updated."""
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("notebooks:edit-entry", kwargs={"book": self.private_nb.pk, "pk": self.entry_yesterday.pk}),
            {"text": "Trying to edit history", "tags": ""},
        )
        self.assertEqual(response.status_code, 403)

    def test_delete_entry_success(self):
        """Authorized user can delete today's entry."""
        del_nb = Notebook.objects.create(
            name="del-nb",
            title="Delete Notebook",
        )
        temp_entry = Entry.objects.create(
            notebook=del_nb,
            created=timezone.now(),
            author=self.user,
            text="Delete me",
            kind=self.text_type,
        )

        self.client.force_login(self.user)
        response = self.client.post(
            reverse("notebooks:delete-entry", kwargs={"book": del_nb.pk, "pk": temp_entry.pk}),
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Entry.objects.filter(pk=temp_entry.pk).exists())

    def test_delete_historical_entry_forbidden(self):
        """Historical entry from a previous day is immutable and cannot be deleted."""
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("notebooks:delete-entry", kwargs={"book": self.private_nb.pk, "pk": self.entry_yesterday.pk}),
        )
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Entry.objects.filter(pk=self.entry_yesterday.pk).exists())

    def test_delete_entry_permission_denied(self):
        """Non-editor cannot delete entry."""
        self.client.force_login(self.other)
        response = self.client.post(
            reverse("notebooks:delete-entry", kwargs={"book": self.private_nb.pk, "pk": self.entry_today.pk}),
        )
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Entry.objects.filter(pk=self.entry_today.pk).exists())

    def test_create_annotation_success(self):
        """Test POST to entry-annotations creates an annotation and returns 201."""
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("notebooks:entry-annotations", kwargs={"book": self.private_nb.pk, "pk": self.entry_today.pk}),
            json.dumps({
                "text": "Check this result",
                "quote": "sel line 1",
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["text"], "Check this result")
        self.assertEqual(data["quote"], "sel line 1")
        self.assertEqual(data["author"], f"@{self.user.username.title()}")
        self.assertEqual(data["entry_id"], self.entry_today.pk)

        annotation = self.entry_today.annotations.first()
        self.assertIsNotNone(annotation)
        self.assertEqual(annotation.text, "Check this result")
        self.assertEqual(annotation.quote, "sel line 1")
        self.assertEqual(annotation.author, self.user)

    def test_create_annotation_empty_text(self):
        """Test creating an annotation with empty text returns 400 Bad Request."""
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("notebooks:entry-annotations", kwargs={"book": self.private_nb.pk, "pk": self.entry_today.pk}),
            {"text": "", "quote": "some text"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"error": "Comment text is required"})
        self.assertEqual(self.entry_today.annotations.count(), 0)

    def test_create_annotation_as_viewer(self):
        """Test that a non-owner with view access can create an annotation."""
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("notebooks:entry-annotations", kwargs={"book": self.private_nb.pk, "pk": self.entry_today.pk}),
            {"text": "Reviewer comment from member", "quote": "important data"},
        )
        self.assertEqual(response.status_code, 201)
        annotation = self.entry_today.annotations.first()
        self.assertEqual(annotation.author, self.user)
        self.assertEqual(annotation.text, "Reviewer comment from member")

    def test_create_annotation_forbidden_for_non_viewer(self):
        """Test that a user without view access cannot annotate a private notebook entry."""
        self.client.force_login(self.other)
        response = self.client.post(
            reverse("notebooks:entry-annotations", kwargs={"book": self.private_nb.pk, "pk": self.entry_today.pk}),
            {"text": "Unauthorized comment"},
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.entry_today.annotations.count(), 0)

    def test_get_annotations_list(self):
        """Test GET request returns list of annotations in JSON format."""
        self.entry_today.annotations.create(
            text="First note",
            quote="part 1",
            author=self.user,
        )
        self.client.force_login(self.user)
        response = self.client.get(
            reverse("notebooks:entry-annotations", kwargs={"book": self.private_nb.pk, "pk": self.entry_today.pk}),
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["text"], "First note")

    def test_delete_annotation_author(self):
        """Test that the author of an annotation can delete it."""
        annotation = self.entry_today.annotations.create(
            text="Temporary note",
            author=self.user,
        )
        self.client.force_login(self.user)
        response = self.client.delete(
            reverse(
                "notebooks:entry-annotation-detail",
                kwargs={"book": self.private_nb.pk, "pk": self.entry_today.pk, "ann_pk": annotation.pk},
            )
        )
        self.assertEqual(response.status_code, 204)
        self.assertEqual(self.entry_today.annotations.count(), 0)

    def test_delete_annotation_forbidden_non_author(self):
        """Test that a user cannot delete another user's annotation."""
        annotation = self.entry_today.annotations.create(
            text="Member note",
            author=self.user,
        )
        self.client.force_login(self.other)
        response = self.client.delete(
            reverse(
                "notebooks:entry-annotation-detail",
                kwargs={"book": self.private_nb.pk, "pk": self.entry_today.pk, "ann_pk": annotation.pk},
            )
        )
        self.assertEqual(response.status_code, 403)
        self.assertTrue(self.entry_today.annotations.filter(pk=annotation.pk).exists())

    def test_legacy_annotate_notebook_endpoint(self):
        """Test backwards compatibility for annotate-notebook alias with POST method=remove."""
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("notebooks:annotate-notebook", kwargs={"book": self.private_nb.pk, "pk": self.entry_today.pk}),
            {
                "text": "Legacy comment",
                "selection": "legacy quote",
            },
        )
        self.assertEqual(response.status_code, 201)
        annotation = self.entry_today.annotations.first()
        self.assertEqual(annotation.text, "Legacy comment")
        self.assertEqual(annotation.quote, "legacy quote")

        # Remove via legacy method parameter
        remove_response = self.client.post(
            reverse("notebooks:annotate-notebook", kwargs={"book": self.private_nb.pk, "pk": self.entry_today.pk}),
            {
                "method": "remove",
                "pk": annotation.pk,
            },
        )
        self.assertEqual(remove_response.status_code, 200)
        self.assertEqual(self.entry_today.annotations.count(), 0)

    @patch("basiclive.core.notebooks.views.loader.get_template")
    def test_tag_entry(self, mock_get_template):
        """Test TagEntry sets tags on entry."""
        mock_template = MagicMock()
        mock_template.render.return_value = "<div>tagged</div>"
        mock_get_template.return_value = mock_template

        self.client.force_login(self.user)
        response = self.client.post(
            reverse("notebooks:tag-notebook", kwargs={"pk": self.private_nb.pk}),
            {
                "pk": self.entry_today.pk,
                "tags": "crystal, xray, diffraction",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.entry_today.refresh_from_db()
        self.assertEqual(set(self.entry_today.tags), {"crystal", "xray", "diffraction"})
