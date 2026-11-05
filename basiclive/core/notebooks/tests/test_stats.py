import unittest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase
from django.utils import timezone

from django.core.management import call_command

from basiclive.core.notebooks.models import (
    Annotation,
    Entry,
    EntryType,
    Notebook,
)
from basiclive.core.lims.models import Project, ProjectMembership
from basiclive.core.notebooks import stats


class NotebooksStatsTestCase(TestCase):
    @classmethod
    def setUpClass(cls):
        call_command('migrate', verbosity=0)
        super().setUpClass()

    def setUp(self):
        User = get_user_model()
        self.superuser = User.objects.create_superuser(
            username="admin", password="password", email="admin@example.com"
        )
        self.user1 = User.objects.create_user(
            username="user1", password="password", email="user1@example.com"
        )
        self.user2 = User.objects.create_user(
            username="user2", password="password", email="user2@example.com"
        )

        self.text_type, _ = EntryType.objects.get_or_create(name="text")
        self.data_type, _ = EntryType.objects.get_or_create(name="data")

        # Create public notebook
        self.nb_pub = Notebook.objects.create(
            name="pub-book",
            title="Public Book",
        )
        # Create internal notebook
        self.nb_int = Notebook.objects.create(
            name="int-book",
            title="Internal Book",
        )
        # Create private notebook owned by user1, shared with user2
        self.nb_priv = Notebook.objects.create(
            name="priv-book",
            title="Private Book",
        )

        # Create private notebook owned by user2, not shared
        self.nb_priv2 = Notebook.objects.create(
            name="priv2-book",
            title="Private Book 2",
        )

        # Entries
        self.entry1 = Entry.objects.create(
            notebook=self.nb_pub,
            kind=self.text_type,
            author=self.user1,
            text="Note 1",
        )
        self.entry2 = Entry.objects.create(
            notebook=self.nb_pub,
            kind=self.data_type,
            author=self.user1,
            text='{"title": "Data 1"}',
        )

        self.annotation = Annotation.objects.create(
            entry=self.entry1,
            author=self.user2,
            text="Great note",
        )

    def test_notebook_metrics_all(self):
        """Verify metrics without user filter computes totals across all notebooks."""
        metrics = stats.notebook_metrics()
        self.assertEqual(metrics["total_notebooks"], 4)
        self.assertEqual(metrics["total_days"], 1)
        self.assertEqual(metrics["total_entries"], 2)
        self.assertEqual(metrics["total_annotations"], 1)
        self.assertEqual(metrics["entries_by_kind"], {"text": 1, "data": 1})

    def test_notebook_metrics_superuser(self):
        """Verify superuser sees all notebooks."""
        metrics = stats.notebook_metrics(user=self.superuser)
        self.assertEqual(metrics["total_notebooks"], 4)

    def test_notebook_metrics_anonymous_user(self):
        """Verify anonymous user sees no notebooks."""
        anon = AnonymousUser()
        metrics = stats.notebook_metrics(user=anon)
        self.assertEqual(metrics["total_notebooks"], 0)
        self.assertEqual(metrics["total_entries"], 0)

    def test_notebook_metrics_authenticated_user(self):
        """Verify non-staff authenticated user sees no notebooks, staff sees all."""
        metrics = stats.notebook_metrics(user=self.user2)
        self.assertEqual(metrics["total_notebooks"], 0)

        self.user2.is_staff = True
        self.user2.save()
        metrics_staff = stats.notebook_metrics(user=self.user2)
        self.assertEqual(metrics_staff["total_notebooks"], 4)

    def test_project_notebook_metrics(self):
        """Verify project_notebook_metrics filters notebooks correctly by project team."""
        project1 = Project.objects.create(name="proj1", pi=self.user1)
        ProjectMembership.objects.create(project=project1, user=self.user2, role=ProjectMembership.Role.MEMBER)
        project2 = Project.objects.create(name="proj2")

        Entry.objects.create(
            notebook=self.nb_priv,
            kind=self.text_type,
            author=self.user2,
            text="User 2 note in private book",
        )

        metrics1 = stats.project_notebook_metrics(project1)
        self.assertEqual(metrics1["total_notebooks"], 2)
        self.assertEqual(metrics1["total_days"], 1)
        self.assertEqual(metrics1["total_entries"], 3)
        self.assertEqual(metrics1["entries_by_kind"], {"text": 2, "data": 1})

        metrics2 = stats.project_notebook_metrics(project2)
        self.assertEqual(metrics2["total_notebooks"], 0)
        self.assertEqual(metrics2["total_days"], 0)
        self.assertEqual(metrics2["total_entries"], 0)
        self.assertEqual(metrics2["entries_by_kind"], {})


if __name__ == "__main__":
    unittest.main()
