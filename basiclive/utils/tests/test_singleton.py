import unittest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection, models
from django.test import TransactionTestCase

from basiclive.core.lims.models import SystemSettings
from basiclive.utils.singleton import Singleton, SingletonManager


class TestSetting(Singleton):
    name = models.CharField(max_length=100, default="Default Name")
    value = models.IntegerField(default=10)

    class Meta:
        app_label = "basiclive"


class ValidatingSetting(Singleton):
    code = models.CharField(max_length=10, default="valid")

    class Meta:
        app_label = "basiclive"

    def clean(self):
        super().clean()
        if self.code == "invalid":
            raise ValidationError("Code cannot be invalid.")


class SingletonTests(TransactionTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with connection.schema_editor() as editor:
            editor.create_model(TestSetting)
            editor.create_model(ValidatingSetting)

    @classmethod
    def tearDownClass(cls):
        with connection.schema_editor() as editor:
            editor.delete_model(TestSetting)
            editor.delete_model(ValidatingSetting)
        super().tearDownClass()

    def setUp(self):
        super().setUp()
        TestSetting.objects.all().delete()
        ValidatingSetting.objects.all().delete()

    def test_abstract_model_metadata(self):
        self.assertTrue(Singleton._meta.abstract)
        created_field = Singleton._meta.get_field("created")
        modified_field = Singleton._meta.get_field("modified")
        self.assertTrue(created_field.auto_now_add)
        self.assertTrue(modified_field.auto_now)
        with self.assertRaises(AttributeError):
            _ = Singleton.objects
        self.assertIsInstance(TestSetting.objects, SingletonManager)

    def test_load_creates_initial_record(self):
        self.assertEqual(TestSetting.objects.count(), 0)
        obj = TestSetting.load()
        self.assertEqual(obj.id, 1)
        self.assertEqual(obj.name, "Default Name")
        self.assertEqual(obj.value, 10)
        self.assertEqual(TestSetting.objects.count(), 1)

    def test_load_returns_existing_record(self):
        created_obj = TestSetting.objects.create(name="Custom Initial", value=42)
        loaded_obj = TestSetting.load()
        self.assertEqual(loaded_obj.id, 1)
        self.assertEqual(loaded_obj.id, created_obj.id)
        self.assertEqual(loaded_obj.name, "Custom Initial")
        self.assertEqual(loaded_obj.value, 42)
        self.assertEqual(TestSetting.objects.count(), 1)

    def test_save_forces_id_one(self):
        instance = TestSetting(id=99, name="Forced ID", value=123)
        instance.save()
        self.assertEqual(instance.id, 1)
        self.assertEqual(TestSetting.objects.count(), 1)
        fetched = TestSetting.objects.get(id=1)
        self.assertEqual(fetched.name, "Forced ID")
        self.assertEqual(fetched.value, 123)

    def test_save_deletes_extraneous_rows(self):
        TestSetting.objects.create(name="Primary", value=1)
        # Manually insert extra rows with different IDs
        with connection.cursor() as cursor:
            cursor.execute(
                f"INSERT INTO {TestSetting._meta.db_table} (id, name, value, created, modified) "
                "VALUES (2, 'Ghost 1', 100, '2026-01-01 00:00:00', '2026-01-01 00:00:00')"
            )
            cursor.execute(
                f"INSERT INTO {TestSetting._meta.db_table} (id, name, value, created, modified) "
                "VALUES (3, 'Ghost 2', 200, '2026-01-01 00:00:00', '2026-01-01 00:00:00')"
            )
        self.assertEqual(TestSetting.objects.count(), 3)

        # Saving the singleton should delete all rows where id != 1
        obj = TestSetting.load()
        obj.name = "Cleaned"
        obj.save()

        self.assertEqual(TestSetting.objects.count(), 1)
        self.assertEqual(TestSetting.objects.first().id, 1)
        self.assertEqual(TestSetting.objects.first().name, "Cleaned")

    def test_save_invokes_clean(self):
        # Invalid code should raise ValidationError during save()
        obj = ValidatingSetting(code="invalid")
        with self.assertRaises(ValidationError):
            obj.save()
        self.assertEqual(ValidatingSetting.objects.count(), 0)

        # Valid code succeeds
        obj.code = "valid"
        obj.save()
        self.assertEqual(ValidatingSetting.objects.count(), 1)

    def test_manager_create_on_empty(self):
        obj = TestSetting.objects.create(name="Created First", value=77)
        self.assertEqual(obj.id, 1)
        self.assertEqual(obj.name, "Created First")
        self.assertEqual(obj.value, 77)
        self.assertEqual(TestSetting.objects.count(), 1)

    def test_manager_create_updates_existing(self):
        first = TestSetting.objects.create(name="First", value=1)
        second = TestSetting.objects.create(name="Second", value=2)
        self.assertEqual(first.id, 1)
        self.assertEqual(second.id, 1)
        self.assertEqual(second.name, "Second")
        self.assertEqual(second.value, 2)
        self.assertEqual(TestSetting.objects.count(), 1)
        reloaded = TestSetting.objects.get(id=1)
        self.assertEqual(reloaded.name, "Second")

    def test_manager_create_strips_id_and_pk(self):
        obj1 = TestSetting.objects.create(id=999, name="Stripped ID")
        self.assertEqual(obj1.id, 1)
        self.assertEqual(TestSetting.objects.count(), 1)

        obj2 = TestSetting.objects.create(pk=888, name="Stripped PK")
        self.assertEqual(obj2.id, 1)
        self.assertEqual(obj2.name, "Stripped PK")
        self.assertEqual(TestSetting.objects.count(), 1)

    def test_manager_get_or_create(self):
        # Initial creation via defaults
        defaults = {"name": "GOC Created", "value": 50}
        obj, created = TestSetting.objects.get_or_create(defaults=defaults)
        self.assertTrue(created)
        self.assertEqual(obj.id, 1)
        self.assertEqual(obj.name, "GOC Created")
        self.assertEqual(obj.value, 50)
        # Caller's dictionary should not be modified
        self.assertEqual(defaults, {"name": "GOC Created", "value": 50})

        # Fetch existing record (defaults should be ignored)
        obj2, created2 = TestSetting.objects.get_or_create(defaults={"name": "Ignored", "value": 999})
        self.assertFalse(created2)
        self.assertEqual(obj2.id, 1)
        self.assertEqual(obj2.name, "GOC Created")
        self.assertEqual(obj2.value, 50)
        self.assertEqual(TestSetting.objects.count(), 1)

    def test_manager_get_or_create_with_kwargs(self):
        # Empty table: kwargs should be merged into creation defaults
        obj, created = TestSetting.objects.get_or_create(id=77, pk=88, name="Via Kwargs", value=60)
        self.assertTrue(created)
        self.assertEqual(obj.id, 1)
        self.assertEqual(obj.name, "Via Kwargs")
        self.assertEqual(obj.value, 60)
        self.assertEqual(TestSetting.objects.count(), 1)

    def test_manager_update_or_create_create(self):
        obj, created = TestSetting.objects.update_or_create(defaults={"name": "UOC Create", "value": 11})
        self.assertTrue(created)
        self.assertEqual(obj.id, 1)
        self.assertEqual(obj.name, "UOC Create")
        self.assertEqual(obj.value, 11)
        self.assertEqual(TestSetting.objects.count(), 1)

    def test_manager_update_or_create_update(self):
        TestSetting.objects.create(name="Initial", value=10)

        # Update with defaults dict
        defaults = {"name": "UOC Update", "value": 20}
        obj, created = TestSetting.objects.update_or_create(defaults=defaults)
        self.assertFalse(created)
        self.assertEqual(obj.id, 1)
        self.assertEqual(obj.name, "UOC Update")
        self.assertEqual(obj.value, 20)
        self.assertEqual(TestSetting.objects.count(), 1)
        self.assertEqual(defaults, {"name": "UOC Update", "value": 20})

        # Update directly via kwargs
        obj2, created2 = TestSetting.objects.update_or_create(id=55, pk=66, name="Direct Kwarg Update")
        self.assertFalse(created2)
        self.assertEqual(obj2.id, 1)
        self.assertEqual(obj2.name, "Direct Kwarg Update")
        self.assertEqual(TestSetting.objects.count(), 1)

    def test_manager_update_or_create_with_create_defaults(self):
        # When creating: create_defaults should take precedence
        obj, created = TestSetting.objects.update_or_create(
            defaults={"name": "Update Name", "value": 100},
            create_defaults={"name": "Create Name", "value": 200},
        )
        self.assertTrue(created)
        self.assertEqual(obj.id, 1)
        self.assertEqual(obj.name, "Create Name")
        self.assertEqual(obj.value, 200)

        # When updating: defaults should be used
        obj2, created2 = TestSetting.objects.update_or_create(
            defaults={"name": "Updated Name", "value": 300},
            create_defaults={"name": "Create Again", "value": 400},
        )
        self.assertFalse(created2)
        self.assertEqual(obj2.id, 1)
        self.assertEqual(obj2.name, "Updated Name")
        self.assertEqual(obj2.value, 300)
        self.assertEqual(TestSetting.objects.count(), 1)

    def test_bulk_create_prohibited(self):
        with self.assertRaises(PermissionDenied) as ctx:
            TestSetting.objects.bulk_create([TestSetting(name="A"), TestSetting(name="B")])
        self.assertEqual(str(ctx.exception), "Bulk creation is prohibited on Singleton models.")

    def test_bulk_update_prohibited(self):
        instance = TestSetting.objects.create(name="Existing")
        with self.assertRaises(PermissionDenied) as ctx:
            TestSetting.objects.bulk_update([instance], fields=["name"])
        self.assertEqual(str(ctx.exception), "Bulk updating is prohibited on Singleton models.")

    def test_timestamps_tracking(self):
        obj = TestSetting.objects.create(name="Timed")
        self.assertIsNotNone(obj.created)
        self.assertIsNotNone(obj.modified)
        initial_created = obj.created
        initial_modified = obj.modified

        obj.name = "Timed Modified"
        obj.save()
        obj.refresh_from_db()

        self.assertEqual(obj.created, initial_created)
        self.assertGreaterEqual(obj.modified, initial_modified)

    def test_system_settings_integration(self):
        # Verify concrete SystemSettings model from basiclive.core.lims inherits and functions correctly
        SystemSettings.objects.all().delete()
        self.assertEqual(SystemSettings.objects.count(), 0)

        settings_obj = SystemSettings.load()
        self.assertEqual(settings_obj.id, 1)
        self.assertEqual(settings_obj.name, "ACME Facility")
        self.assertEqual(SystemSettings.objects.count(), 1)

        updated_obj = SystemSettings.objects.create(name="Custom Beamline Facility", acronym="CBF")
        self.assertEqual(updated_obj.id, 1)
        self.assertEqual(updated_obj.name, "Custom Beamline Facility")
        self.assertEqual(updated_obj.acronym, "CBF")
        self.assertEqual(SystemSettings.objects.count(), 1)

        reloaded = SystemSettings.load()
        self.assertEqual(reloaded.name, "Custom Beamline Facility")


if __name__ == "__main__":
    unittest.main()
