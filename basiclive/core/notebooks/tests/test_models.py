import json
import unittest
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone


from basiclive.core.notebooks.models import (
    Annotation,
    Entry,
    EntryType,
    Notebook,
    entry_storage,
)
from basiclive.core.notebooks.fields import StringListField, DelimitedTextFormField
from basiclive.core.notebooks.utils import (
    clean_json,
    fuzzy_time,
    simpletime,
    timeish,
)

User = get_user_model()


class NotebookModelsTestCase(TestCase):
    @classmethod
    def setUpClass(cls):
        call_command('migrate', verbosity=0)
        super().setUpClass()

    def setUp(self):
        self.user = User.objects.create_superuser(username="user", password="password123", name="User")
        self.other = User.objects.create_user(username="other", password="password123", name="Other")
        self.admin = User.objects.create_superuser(username="admin", password="password123", name="Admin")

        self.entry_type_text, _ = EntryType.objects.get_or_create(name="text")
        self.entry_type_data, _ = EntryType.objects.get_or_create(name="data")

        self.notebook = Notebook.objects.create(
            name="test-notebook",
            title="Test Notebook",
            description="A test notebook description",
        )

    def test_entry_type_natural_key(self):
        self.assertEqual(self.entry_type_text.natural_key(), ("text",))
        fetched = EntryType.objects.get_by_natural_key("text")
        self.assertEqual(fetched, self.entry_type_text)
        self.assertEqual(str(self.entry_type_text), "text")

    def test_notebook_permissions_can_edit(self):
        # Admin editor:
        self.assertTrue(self.notebook.can_edit(self.admin))
        self.assertFalse(self.notebook.can_edit(self.other))

        # Staff editor:
        self.other.is_staff = True
        self.other.save()
        self.assertTrue(self.notebook.can_edit(self.other))

    def test_entry_direct_attachment_and_storage(self):
        entry = Entry.objects.create(
            notebook=self.notebook,
            author=self.user,
            kind=self.entry_type_text,
            text="Direct entry notes",
        )
        self.assertEqual(entry.notebook, self.notebook)
        self.assertIn(entry, self.notebook.entries.all())
        self.assertIn(self.notebook.name, str(entry))

        # Verify entry storage path uses notebook pk and date
        path = entry_storage(entry, "scan.dat")
        today_iso = timezone.localdate(entry.created).isoformat()
        expected_prefix = f"notebooks/{self.notebook.pk}/{today_iso}/"
        self.assertTrue(path.startswith(expected_prefix), f"Expected path to start with {expected_prefix}, got {path}")

    def test_entry_date_queries_via_orm(self):
        now = timezone.now()
        yesterday_dt = now - timedelta(days=1)
        entry1 = Entry.objects.create(
            notebook=self.notebook,
            author=self.user,
            kind=self.entry_type_text,
            created=yesterday_dt,
            text="Yesterday entry",
        )
        entry2 = Entry.objects.create(
            notebook=self.notebook,
            author=self.user,
            kind=self.entry_type_text,
            created=now,
            text="Today entry",
        )

        # Query distinct dates via ORM
        dates = list(self.notebook.entries.dates('created', 'day'))
        self.assertEqual(len(dates), 2)
        self.assertEqual(dates[0], timezone.localdate(yesterday_dt))
        self.assertEqual(dates[1], timezone.localdate(now))

        # Filter by created__date
        today_entries = self.notebook.entries.filter(created__date=timezone.localdate(now))
        self.assertEqual(list(today_entries), [entry2])

    def test_entry_lifecycle_and_tags(self):
        entry = Entry.objects.create(
            notebook=self.notebook,
            author=self.user,
            kind=self.entry_type_text,
            tags=["crystallography", "calibration"],
            text="Initial measurement notes",
        )
        self.assertEqual(entry.tags, ["crystallography", "calibration"])
        self.assertEqual(entry.tag_string(), "crystallography,calibration")
        self.assertTrue(entry.is_editable())
        self.assertTrue(entry.can_edit(self.user))
        self.assertFalse(entry.can_edit(self.other))
        self.assertTrue(entry.can_view(self.admin))

        # Tag field DB round-trip:
        entry.refresh_from_db()
        self.assertEqual(entry.tags, ["crystallography", "calibration"])

    def test_annotation_functionality(self):
        entry = Entry.objects.create(
            notebook=self.notebook,
            author=self.user,
            kind=self.entry_type_text,
            text="Sample collected with 12 keV",
        )
        quote_comment = Annotation.objects.create(
            entry=entry,
            quote="12 keV",
            text="Verify beam energy calibration",
            author=self.user,
        )
        general_comment = Annotation.objects.create(
            entry=entry,
            text="Overall run looks good",
            author=self.user,
        )

        self.assertEqual(entry.annotations.count(), 2)
        self.assertEqual(entry.annotations.with_quotes().count(), 1)
        self.assertEqual(entry.annotations.with_quotes().first(), quote_comment)

        payload = quote_comment.json()
        self.assertEqual(payload["author"], f"@{self.user.name}")
        self.assertEqual(payload["text"], "Verify beam energy calibration")
        self.assertEqual(payload["quote"], "12 keV")
        self.assertEqual(payload["entry_id"], entry.pk)
        self.assertEqual(payload["id"], quote_comment.pk)

        # Entry with annotations is no longer editable by author
        self.assertFalse(entry.is_editable())
        self.assertFalse(entry.can_edit(self.user))

    def test_string_list_field_and_form_field(self):
        field = StringListField()
        self.assertEqual(field.to_python(None), [])
        self.assertEqual(field.to_python("<one><two>"), ["one", "two"])
        self.assertEqual(field.get_prep_value(["alpha", "beta"]), "<alpha><beta>")

        form_field = DelimitedTextFormField()
        self.assertEqual(form_field.to_python("a, b; c"), ["a", "b", "c"])
        self.assertEqual(form_field.prepare_value(["x", "y"]), "x; y")

    def test_utils_clean_json(self):
        data = {
            "data": {
                "0": [0.1234567, 0.1234568],
                "1": [1.0, 2.0],
            }
        }
        cleaned = clean_json(json.dumps(data))
        parsed = json.loads(cleaned)
        self.assertIn("data", parsed)
        self.assertEqual(parsed["data"]["1"], [1.0, 2.0])

    def test_utils_time_helpers(self):
        now = timezone.now()
        self.assertEqual(timeish(now), "now")
        self.assertEqual(timeish(now - timedelta(minutes=5)), "5min")
        self.assertEqual(timeish(now - timedelta(hours=3)), "3h")

        simple = simpletime(now)
        self.assertTrue(len(simple) > 0)

        # Fuzzy time queries:
        q_past = fuzzy_time("< 2 days", field="created")
        self.assertTrue(bool(q_past))


if __name__ == "__main__":
    unittest.main()
