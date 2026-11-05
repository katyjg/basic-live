from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from basiclive.core.crm.forms import SupportEntryForm
from basiclive.core.crm.models import SupportArea, SupportRecord
from basiclive.core.lims.models import Beamline, Project

User = get_user_model()


class SupportModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", email="user@example.org", is_staff=True)
        self.project = Project.objects.create(name="Research Project", pi=self.user)
        self.beamline = Beamline.objects.create(name="Beamline 1", acronym="BL1")
        self.area = SupportArea.objects.create(name="Optics & Mirrors", external=False)

    def test_support_area_creation_and_str(self):
        self.assertEqual(str(self.area), "Optics & Mirrors")
        self.assertFalse(self.area.external)
        self.assertFalse(self.area.user_feedback)

    def test_support_area_label_and_display_label(self):
        # Default label is blank, display_label falls back to name
        self.assertEqual(self.area.label, "")
        self.assertEqual(self.area.display_label, "Optics & Mirrors")
        self.assertEqual(str(self.area), "Optics & Mirrors")

        # Custom label returns label for display_label while str remains name
        self.area.label = "Are you satisfied with the optics and mirrors alignment?"
        self.area.save()
        self.assertEqual(self.area.label, "Are you satisfied with the optics and mirrors alignment?")
        self.assertEqual(self.area.display_label, "Are you satisfied with the optics and mirrors alignment?")
        self.assertEqual(str(self.area), "Optics & Mirrors")

    def test_support_record_creation_with_area(self):
        record = SupportRecord.objects.create(
            kind=SupportRecord.TYPE.problem,
            area=self.area,
            staff=self.user,
            project=self.project,
            beamline=self.beamline,
            lost_time=1.5,
            comments="Mirror alignment lost",
            staff_comments="Realigned mirror motors",
        )
        self.assertEqual(record.area, self.area)
        self.assertEqual(record.staff, self.user)
        self.assertEqual(str(record), f"{self.user} | {self.beamline} | {self.project}")
        self.assertEqual(record.area_names, "Optics & Mirrors")

    def test_support_record_without_area(self):
        record = SupportRecord.objects.create(
            kind=SupportRecord.TYPE.info,
            staff=self.user,
            project=self.project,
            beamline=self.beamline,
        )
        self.assertIsNone(record.area)
        self.assertEqual(record.area_names, "")

    def test_support_area_reverse_records_accessor(self):
        record1 = SupportRecord.objects.create(
            kind=SupportRecord.TYPE.problem,
            area=self.area,
            staff=self.user,
            project=self.project,
            beamline=self.beamline,
            lost_time=1.0,
        )
        record2 = SupportRecord.objects.create(
            kind=SupportRecord.TYPE.info,
            area=self.area,
            staff=self.user,
            project=self.project,
            beamline=self.beamline,
            lost_time=0.0,
        )
        self.assertEqual(list(self.area.records.order_by("pk")), [record1, record2])


class SupportFormTests(TestCase):
    def setUp(self):
        self.staff_user = User.objects.create_user(
            username="staffuser", email="staff@example.org", is_staff=True
        )
        self.user = User.objects.create_user(username="scienceuser", email="user@example.org")
        self.user_project = Project.objects.create(name="User Group", pi=self.user)
        self.beamline = Beamline.objects.create(name="Beamline 1", acronym="BL1")
        self.area = SupportArea.objects.create(name="Detectors")

    def test_support_entry_form_valid(self):
        form_data = {
            "kind": "problem",
            "area": self.area.pk,
            "staff": self.staff_user.pk,
            "project": self.user_project.pk,
            "beamline": self.beamline.pk,
            "lost_time": 2.5,
            "comments": "Detector readout error",
            "staff_comments": "Power cycled controller",
        }
        form = SupportEntryForm(data=form_data)
        self.assertTrue(form.is_valid(), form.errors)
        record = form.save()
        self.assertEqual(record.area, self.area)
        self.assertEqual(record.staff, self.staff_user)
        self.assertEqual(record.lost_time, 2.5)

    def test_support_entry_form_layout_contains_area(self):
        form = SupportEntryForm()
        self.assertIn("area", form.fields)
        layout_fields = [
            field_name
            for row in form.body.layout.fields if hasattr(row, 'fields')
            for f in row.fields
            for field_name in (f.fields if hasattr(f, 'fields') else [f])
        ]
        self.assertIn("area", layout_fields)

    def test_support_area_form_valid_with_name_and_label(self):
        from basiclive.core.crm.forms import SupportAreaForm
        form = SupportAreaForm(data={
            "name": "Beamline Computing",
            "label": "How would you rate the speed and stability of data processing software?",
            "user_feedback": True,
        })
        self.assertTrue(form.is_valid(), form.errors)
        area = form.save()
        self.assertEqual(area.name, "Beamline Computing")
        self.assertEqual(area.label, "How would you rate the speed and stability of data processing software?")
        self.assertTrue(area.user_feedback)

    def test_support_area_form_valid_without_label(self):
        from basiclive.core.crm.forms import SupportAreaForm
        form = SupportAreaForm(data={
            "name": "Vacuum Systems",
            "external": True,
        })
        self.assertTrue(form.is_valid(), form.errors)
        area = form.save()
        self.assertEqual(area.name, "Vacuum Systems")
        self.assertEqual(area.label, "")
        self.assertEqual(area.display_label, "Vacuum Systems")

    def test_support_area_form_layout_contains_name_and_label(self):
        from basiclive.core.crm.forms import SupportAreaForm
        form = SupportAreaForm()
        self.assertIn("name", form.fields)
        self.assertIn("label", form.fields)
        layout_fields = [
            field_name
            for row in form.body.layout.fields if hasattr(row, 'fields')
            for f in row.fields
            for field_name in (f.fields if hasattr(f, 'fields') else [f])
        ]
        self.assertIn("name", layout_fields)
        self.assertIn("label", layout_fields)


class SupportViewTests(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_superuser(
            username="adminuser", email="admin@example.org", password="adminpassword"
        )
        self.client.force_login(self.admin_user)

        self.staff_user = User.objects.create_user(
            username="staffmember", email="staffmember@example.org", is_staff=True
        )
        self.user_project = Project.objects.create(name="Science Group", pi=self.admin_user)
        self.beamline = Beamline.objects.create(name="Beamline 1", acronym="BL1")
        self.area1 = SupportArea.objects.create(name="Optics")
        self.area2 = SupportArea.objects.create(name="Cryo")

        self.record1 = SupportRecord.objects.create(
            kind=SupportRecord.TYPE.problem,
            area=self.area1,
            staff=self.staff_user,
            project=self.user_project,
            beamline=self.beamline,
            lost_time=1.0,
            comments="Optics glitch",
        )
        self.record2 = SupportRecord.objects.create(
            kind=SupportRecord.TYPE.info,
            area=self.area2,
            staff=self.staff_user,
            project=self.user_project,
            beamline=self.beamline,
            lost_time=0.0,
            comments="Cryo refill",
        )

    def test_support_record_list_view(self):
        response = self.client.get(reverse("supportrecord-list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Optics")
        self.assertContains(response, "Cryo")

    def test_support_record_list_filter_by_area(self):
        response = self.client.get(reverse("supportrecord-list"), {"area__id__exact": self.area1.pk})
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.record1, response.context["object_list"])
        self.assertNotIn(self.record2, response.context["object_list"])

    def test_support_record_create_view(self):
        post_data = {
            "kind": "problem",
            "area": self.area1.pk,
            "staff": self.staff_user.pk,
            "project": self.user_project.pk,
            "beamline": self.beamline.pk,
            "lost_time": 0.75,
            "comments": "Motor stalled",
            "staff_comments": "Reset stage",
        }
        response = self.client.post(reverse("new-supportrecord"), post_data)
        self.assertEqual(response.status_code, 200)  # ModalForm returns 200 with JSON or redirect
        self.assertTrue(SupportRecord.objects.filter(comments="Motor stalled", area=self.area1, staff=self.staff_user).exists())

    def test_support_record_create_view_initial_staff(self):
        response = self.client.get(reverse("new-supportrecord"))
        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertEqual(form.initial.get("staff"), self.admin_user)

    def test_support_record_edit_view(self):
        post_data = {
            "kind": "problem",
            "area": self.area2.pk,
            "staff": self.staff_user.pk,
            "project": self.user_project.pk,
            "beamline": self.beamline.pk,
            "lost_time": 2.0,
            "comments": "Optics glitch updated to cryo",
            "staff_comments": "Switched area",
        }
        response = self.client.post(reverse("supportrecord-edit", kwargs={"pk": self.record1.pk}), post_data)
        self.assertEqual(response.status_code, 200)
        self.record1.refresh_from_db()
        self.assertEqual(self.record1.area, self.area2)
        self.assertEqual(self.record1.lost_time, 2.0)
        self.assertEqual(self.record1.staff, self.staff_user)

    def test_support_area_list_view_displays_label(self):
        area = SupportArea.objects.create(name="Sample Delivery", label="Rate robotics reliability")
        response = self.client.get(reverse("supportarea-list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sample Delivery")
        self.assertContains(response, "Rate robotics reliability")

    def test_support_area_create_view_with_label(self):
        post_data = {
            "name": "Data Storage",
            "label": "Were file transfers and download speeds acceptable?",
            "user_feedback": True,
        }
        response = self.client.post(reverse("new-supportarea"), post_data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            SupportArea.objects.filter(
                name="Data Storage", label="Were file transfers and download speeds acceptable?"
            ).exists()
        )

    def test_support_area_admin_configuration(self):
        from django.contrib import admin
        area_admin = admin.site._registry[SupportArea]
        self.assertIn("name", area_admin.list_display)
        self.assertIn("label", area_admin.list_display)
        self.assertIn("name", area_admin.search_fields)
        self.assertIn("label", area_admin.search_fields)


class SupportMigrationLogicTests(TestCase):
    def test_populate_area_duplicates_multiarea_records(self):
        import importlib
        migration_module = importlib.import_module("basiclive.core.crm.migrations.0085_populate_supportrecord_area")
        populate_area_from_areas = migration_module.populate_area_from_areas

        area_a = SupportArea.objects.create(name="Area Alpha")
        area_b = SupportArea.objects.create(name="Area Beta")
        user = User.objects.create_user(username="miguser", email="mig@example.org")
        project = Project.objects.create(name="Mig Project", pi=user)
        beamline = Beamline.objects.create(name="Mig BL", acronym="MBL")

        # Create record with area_a
        rec = SupportRecord.objects.create(
            kind="problem",
            area=None,
            project=project,
            beamline=beamline,
            lost_time=1.0,
            comments="Original record",
        )

        class MockRecord:
            def __init__(self, record, areas_list):
                self.record = record
                self.pk = record.pk
                self.areas_list = areas_list
                self.kind = record.kind
                self.staff_id = record.staff_id
                self.user_id = None
                self.project_id = record.project_id
                self.beamline_id = record.beamline_id
                self.comments = record.comments
                self.lost_time = record.lost_time
                self.staff_comments = record.staff_comments
                self.created = record.created
                self.modified = record.modified

            @property
            def areas(self):
                class MockAreas:
                    def __init__(self, items):
                        self.items = items

                    def all(self):
                        return self.items
                return MockAreas(self.areas_list)

            def save(self, update_fields=None):
                self.record.area = self.area
                self.record.save(update_fields=update_fields)

        class MockSupportRecordManager:
            def __init__(self, mock_records):
                self.mock_records = mock_records

            def using(self, alias):
                return self

            def all(self):
                return self.mock_records

            def create(self, **kwargs):
                kwargs.pop('user_id', None)
                return SupportRecord.objects.create(**kwargs)

        class MockSupportRecordModel:
            def __init__(self, mock_records):
                self.objects = MockSupportRecordManager(mock_records)

        class MockApps:
            def get_model(self, app_label, model_name):
                return MockSupportRecordModel([MockRecord(rec, [area_a, area_b])])

        class MockSchemaEditor:
            class MockConnection:
                alias = "default"
            connection = MockConnection()

        populate_area_from_areas(MockApps(), MockSchemaEditor())

        records = SupportRecord.objects.filter(project=project).order_by("pk")
        self.assertEqual(records.count(), 2)
        self.assertEqual(records[0].area, area_a)
        self.assertEqual(records[1].area, area_b)
        self.assertEqual(records[1].comments, "Original record")


class SupportRecordChainIntegrityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="supportuser", email="user@example.org", is_staff=True)
        self.project = Project.objects.create(name="Project Alpha", pi=self.user)
        self.bl1 = Beamline.objects.create(name="Beamline 1", acronym="BL1")
        self.bl2 = Beamline.objects.create(name="Beamline 2", acronym="BL2")
        self.area1 = SupportArea.objects.create(name="Optics")
        self.area2 = SupportArea.objects.create(name="Detectors")
        self.base_time = timezone.now() - timedelta(days=1)

    def test_sequential_record_creation_chains(self):
        r1 = SupportRecord.objects.create(
            kind=SupportRecord.TYPE.problem,
            area=self.area1,
            beamline=self.bl1,
            project=self.project,
            staff=self.user,
            lost_time=1.0,
            created=self.base_time + timedelta(hours=1),
        )
        r2 = SupportRecord.objects.create(
            kind=SupportRecord.TYPE.problem,
            area=self.area1,
            beamline=self.bl1,
            project=self.project,
            staff=self.user,
            lost_time=2.0,
            created=self.base_time + timedelta(hours=2),
        )
        r3 = SupportRecord.objects.create(
            kind=SupportRecord.TYPE.problem,
            area=self.area1,
            beamline=self.bl1,
            project=self.project,
            staff=self.user,
            lost_time=3.0,
            created=self.base_time + timedelta(hours=3),
        )

        r1.refresh_from_db()
        r2.refresh_from_db()
        r3.refresh_from_db()

        self.assertIsNone(r1.previous)
        self.assertEqual(r2.previous, r1)
        self.assertEqual(r3.previous, r2)

        self.assertEqual(r1.next, r2)
        self.assertEqual(r2.next, r3)
        self.assertIsNone(r3.next)

    def test_different_partitions_isolated(self):
        r1 = SupportRecord.objects.create(
            kind=SupportRecord.TYPE.problem,
            area=self.area1,
            beamline=self.bl1,
            project=self.project,
            staff=self.user,
            lost_time=1.0,
            created=self.base_time + timedelta(hours=1),
        )
        r2 = SupportRecord.objects.create(
            kind=SupportRecord.TYPE.problem,
            area=self.area1,
            beamline=self.bl2,
            project=self.project,
            staff=self.user,
            lost_time=1.0,
            created=self.base_time + timedelta(hours=2),
        )
        r3 = SupportRecord.objects.create(
            kind=SupportRecord.TYPE.problem,
            area=self.area2,
            beamline=self.bl1,
            project=self.project,
            staff=self.user,
            lost_time=1.0,
            created=self.base_time + timedelta(hours=3),
        )
        r4 = SupportRecord.objects.create(
            kind=SupportRecord.TYPE.info,
            area=self.area1,
            beamline=self.bl1,
            project=self.project,
            staff=self.user,
            lost_time=0.0,
            created=self.base_time + timedelta(hours=4),
        )

        for r in [r1, r2, r3, r4]:
            r.refresh_from_db()
            self.assertIsNone(r.previous)
            self.assertIsNone(r.next)

    def test_insert_record_in_middle_and_head(self):
        r1 = SupportRecord.objects.create(
            kind=SupportRecord.TYPE.problem,
            area=self.area1,
            beamline=self.bl1,
            project=self.project,
            staff=self.user,
            lost_time=1.0,
            created=self.base_time + timedelta(hours=2),
        )
        r3 = SupportRecord.objects.create(
            kind=SupportRecord.TYPE.problem,
            area=self.area1,
            beamline=self.bl1,
            project=self.project,
            staff=self.user,
            lost_time=1.0,
            created=self.base_time + timedelta(hours=4),
        )

        r2 = SupportRecord.objects.create(
            kind=SupportRecord.TYPE.problem,
            area=self.area1,
            beamline=self.bl1,
            project=self.project,
            staff=self.user,
            lost_time=1.0,
            created=self.base_time + timedelta(hours=3),
        )

        r1.refresh_from_db()
        r2.refresh_from_db()
        r3.refresh_from_db()

        self.assertIsNone(r1.previous)
        self.assertEqual(r2.previous, r1)
        self.assertEqual(r3.previous, r2)
        self.assertEqual(r1.next, r2)
        self.assertEqual(r2.next, r3)

        r0 = SupportRecord.objects.create(
            kind=SupportRecord.TYPE.problem,
            area=self.area1,
            beamline=self.bl1,
            project=self.project,
            staff=self.user,
            lost_time=1.0,
            created=self.base_time + timedelta(hours=1),
        )

        r0.refresh_from_db()
        r1.refresh_from_db()

        self.assertIsNone(r0.previous)
        self.assertEqual(r1.previous, r0)
        self.assertEqual(r0.next, r1)

    def test_update_partition_fields_relinks_both_chains(self):
        a1 = SupportRecord.objects.create(
            kind=SupportRecord.TYPE.problem, area=self.area1, beamline=self.bl1, project=self.project,
            staff=self.user, lost_time=1.0, created=self.base_time + timedelta(hours=1),
        )
        a2 = SupportRecord.objects.create(
            kind=SupportRecord.TYPE.problem, area=self.area1, beamline=self.bl1, project=self.project,
            staff=self.user, lost_time=1.0, created=self.base_time + timedelta(hours=2),
        )
        a3 = SupportRecord.objects.create(
            kind=SupportRecord.TYPE.problem, area=self.area1, beamline=self.bl1, project=self.project,
            staff=self.user, lost_time=1.0, created=self.base_time + timedelta(hours=3),
        )

        b1 = SupportRecord.objects.create(
            kind=SupportRecord.TYPE.problem, area=self.area2, beamline=self.bl1, project=self.project,
            staff=self.user, lost_time=1.0, created=self.base_time + timedelta(hours=1, minutes=30),
        )
        b2 = SupportRecord.objects.create(
            kind=SupportRecord.TYPE.problem, area=self.area2, beamline=self.bl1, project=self.project,
            staff=self.user, lost_time=1.0, created=self.base_time + timedelta(hours=3, minutes=30),
        )

        a2.area = self.area2
        a2.save()

        a1.refresh_from_db()
        a2.refresh_from_db()
        a3.refresh_from_db()
        b1.refresh_from_db()
        b2.refresh_from_db()

        self.assertIsNone(a1.previous)
        self.assertEqual(a3.previous, a1)
        self.assertEqual(a1.next, a3)
        self.assertIsNone(a3.next)

        self.assertIsNone(b1.previous)
        self.assertEqual(a2.previous, b1)
        self.assertEqual(b2.previous, a2)
        self.assertEqual(b1.next, a2)
        self.assertEqual(a2.next, b2)
        self.assertIsNone(b2.next)

    def test_update_created_timestamp_repositions(self):
        r1 = SupportRecord.objects.create(
            kind=SupportRecord.TYPE.problem, area=self.area1, beamline=self.bl1, project=self.project,
            staff=self.user, lost_time=1.0, created=self.base_time + timedelta(hours=1),
        )
        r2 = SupportRecord.objects.create(
            kind=SupportRecord.TYPE.problem, area=self.area1, beamline=self.bl1, project=self.project,
            staff=self.user, lost_time=1.0, created=self.base_time + timedelta(hours=2),
        )
        r3 = SupportRecord.objects.create(
            kind=SupportRecord.TYPE.problem, area=self.area1, beamline=self.bl1, project=self.project,
            staff=self.user, lost_time=1.0, created=self.base_time + timedelta(hours=3),
        )

        r2.created = self.base_time + timedelta(hours=4)
        r2.save()

        r1.refresh_from_db()
        r2.refresh_from_db()
        r3.refresh_from_db()

        self.assertIsNone(r1.previous)
        self.assertEqual(r3.previous, r1)
        self.assertEqual(r2.previous, r3)
        self.assertEqual(r1.next, r3)
        self.assertEqual(r3.next, r2)
        self.assertIsNone(r2.next)

    def test_delete_middle_head_and_tail(self):
        r1 = SupportRecord.objects.create(
            kind=SupportRecord.TYPE.problem, area=self.area1, beamline=self.bl1, project=self.project,
            staff=self.user, lost_time=1.0, created=self.base_time + timedelta(hours=1),
        )
        r2 = SupportRecord.objects.create(
            kind=SupportRecord.TYPE.problem, area=self.area1, beamline=self.bl1, project=self.project,
            staff=self.user, lost_time=1.0, created=self.base_time + timedelta(hours=2),
        )
        r3 = SupportRecord.objects.create(
            kind=SupportRecord.TYPE.problem, area=self.area1, beamline=self.bl1, project=self.project,
            staff=self.user, lost_time=1.0, created=self.base_time + timedelta(hours=3),
        )

        # Delete middle (r2)
        r2.delete()
        r1.refresh_from_db()
        r3.refresh_from_db()
        self.assertIsNone(r1.previous)
        self.assertEqual(r3.previous, r1)
        self.assertEqual(r1.next, r3)

        # Delete head (r1)
        r1.delete()
        r3.refresh_from_db()
        self.assertIsNone(r3.previous)
        self.assertIsNone(r3.next)

    def test_null_area_and_null_beamline_partitions(self):
        n1 = SupportRecord.objects.create(
            kind=SupportRecord.TYPE.info, area=None, beamline=self.bl1, project=self.project,
            staff=self.user, created=self.base_time + timedelta(hours=1),
        )
        n2 = SupportRecord.objects.create(
            kind=SupportRecord.TYPE.info, area=None, beamline=self.bl1, project=self.project,
            staff=self.user, created=self.base_time + timedelta(hours=2),
        )
        n1.refresh_from_db()
        n2.refresh_from_db()
        self.assertIsNone(n1.previous)
        self.assertEqual(n2.previous, n1)

        b1 = SupportRecord.objects.create(
            kind=SupportRecord.TYPE.info, area=self.area1, beamline=None, project=self.project,
            staff=self.user, created=self.base_time + timedelta(hours=1),
        )
        b2 = SupportRecord.objects.create(
            kind=SupportRecord.TYPE.info, area=self.area1, beamline=None, project=self.project,
            staff=self.user, created=self.base_time + timedelta(hours=2),
        )
        b1.refresh_from_db()
        b2.refresh_from_db()
        self.assertIsNone(b1.previous)
        self.assertEqual(b2.previous, b1)


class SupportPreviousMigrationTests(TestCase):
    def test_migration_0088_populate_previous_records(self):
        import importlib
        migration_module = importlib.import_module("basiclive.core.crm.migrations.0088_supportrecord_previous")
        populate_previous_records = migration_module.populate_previous_records

        user = User.objects.create_user(username="prevuser", email="user@example.org")
        project = Project.objects.create(name="Project", pi=user)
        bl = Beamline.objects.create(name="BL", acronym="BL")
        area = SupportArea.objects.create(name="Area")
        base = timezone.now() - timedelta(days=2)

        r1 = SupportRecord.objects.create(
            kind="problem", area=area, beamline=bl, project=project, staff=user, lost_time=1.0,
            created=base + timedelta(hours=1)
        )
        r2 = SupportRecord.objects.create(
            kind="problem", area=area, beamline=bl, project=project, staff=user, lost_time=1.0,
            created=base + timedelta(hours=2)
        )
        r3 = SupportRecord.objects.create(
            kind="problem", area=area, beamline=bl, project=project, staff=user, lost_time=1.0,
            created=base + timedelta(hours=3)
        )

        SupportRecord.objects.all().update(previous=None)
        r1.refresh_from_db()
        r2.refresh_from_db()
        r3.refresh_from_db()
        self.assertIsNone(r1.previous)
        self.assertIsNone(r2.previous)
        self.assertIsNone(r3.previous)

        class MockApps:
            def get_model(self, app_label, model_name):
                return SupportRecord

        class MockSchemaEditor:
            class MockConnection:
                alias = "default"
            connection = MockConnection()

        populate_previous_records(MockApps(), MockSchemaEditor())

        r1.refresh_from_db()
        r2.refresh_from_db()
        r3.refresh_from_db()
        self.assertIsNone(r1.previous)
        self.assertEqual(r2.previous, r1)
        self.assertEqual(r3.previous, r2)


class SupportAreaLabelMigrationTests(TestCase):
    def test_migration_0090_populate_supportarea_label(self):
        import importlib
        migration_module = importlib.import_module("basiclive.core.crm.migrations.0090_supportarea_label")
        populate_supportarea_label = migration_module.populate_supportarea_label
        reverse_populate_supportarea_label = migration_module.reverse_populate_supportarea_label

        area1 = SupportArea.objects.create(name="Area 1", label="")
        area2 = SupportArea.objects.create(name="Area 2", label="")

        class MockApps:
            def get_model(self, app_label, model_name):
                return SupportArea

        class MockSchemaEditor:
            class MockConnection:
                alias = "default"
            connection = MockConnection()

        populate_supportarea_label(MockApps(), MockSchemaEditor())

        area1.refresh_from_db()
        area2.refresh_from_db()
        self.assertEqual(area1.label, "Area 1")
        self.assertEqual(area2.label, "Area 2")

        reverse_populate_supportarea_label(MockApps(), MockSchemaEditor())
        area1.refresh_from_db()
        area2.refresh_from_db()
        self.assertEqual(area1.label, "")
        self.assertEqual(area2.label, "")


