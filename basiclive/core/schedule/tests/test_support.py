from datetime import date, timedelta
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from basiclive.core.schedule.forms import BeamlineSupportForm
from basiclive.core.schedule.models import BeamlineSupport
from basiclive.core.schedule.templatetags.calendar import calendar_view

User = get_user_model()


class BeamlineSupportModelTests(TestCase):
    def setUp(self):
        self.staff_user = User.objects.create_user(
            username="staff1",
            first_name="Alice",
            last_name="Smith",
            email="alice@facility.example.org",
            phone="555-1234",
            is_staff=True,
        )

    def test_beamline_support_creation_and_str(self):
        support = BeamlineSupport.objects.create(
            staff=self.staff_user,
            date=date(2026, 10, 5),
        )
        self.assertEqual(support.staff, self.staff_user)
        self.assertEqual(str(support), "Alice Smith")
        self.assertEqual(support.staff.email, "alice@facility.example.org")
        self.assertEqual(support.staff.phone, "555-1234")


class BeamlineSupportFormTests(TestCase):
    def setUp(self):
        self.staff_user = User.objects.create_user(
            username="staff_form",
            first_name="Bob",
            last_name="Jones",
            email="bob@facility.example.org",
            is_staff=True,
        )
        self.non_staff_user = User.objects.create_user(
            username="regular_user",
            first_name="Charlie",
            last_name="Brown",
            email="charlie@example.org",
            is_staff=False,
        )

    def test_form_valid_with_staff_user(self):
        form_data = {
            "staff": self.staff_user.pk,
            "date": "2026-10-06",
        }
        form = BeamlineSupportForm(data=form_data)
        self.assertTrue(form.is_valid(), form.errors)
        instance = form.save()
        self.assertEqual(instance.staff, self.staff_user)
        self.assertEqual(instance.date, date(2026, 10, 6))

    def test_form_queryset_excludes_non_staff(self):
        form = BeamlineSupportForm()
        staff_choices = list(form.fields['staff'].queryset)
        self.assertIn(self.staff_user, staff_choices)
        self.assertNotIn(self.non_staff_user, staff_choices)


class BeamlineSupportViewTests(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_superuser(
            username="adminuser",
            email="admin@example.org",
            password="adminpassword",
            first_name="Admin",
            last_name="Super",
            phone="555-9999",
        )
        self.client.force_login(self.admin_user)

        self.staff_user = User.objects.create_user(
            username="support_staff",
            first_name="Dana",
            last_name="Scully",
            email="dana@facility.example.org",
            phone="555-1122",
            is_staff=True,
        )
        self.today = timezone.localtime().date()
        self.support = BeamlineSupport.objects.create(
            staff=self.staff_user,
            date=self.today,
        )

    def test_support_detail_view_active(self):
        response = self.client.get(reverse("support-info", kwargs={"pk": self.support.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "DANA")
        self.assertContains(response, "Scully")
        self.assertContains(response, "dana@facility.example.org")
        self.assertContains(response, "555-1122")

    def test_support_detail_view_future(self):
        future_support = BeamlineSupport.objects.create(
            staff=self.staff_user,
            date=self.today + timedelta(days=5),
        )
        response = self.client.get(reverse("support-info", kwargs={"pk": future_support.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Dana will contact you on")

    def test_support_create_view(self):
        post_data = {
            "staff": self.staff_user.pk,
            "date": "2026-10-08",
        }
        response = self.client.post(reverse("new-support"), post_data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(BeamlineSupport.objects.filter(staff=self.staff_user, date=date(2026, 10, 8)).exists())

    def test_support_edit_view(self):
        new_staff = User.objects.create_user(
            username="fox_mulder",
            first_name="Fox",
            last_name="Mulder",
            email="fox@facility.example.org",
            is_staff=True,
        )
        post_data = {
            "staff": new_staff.pk,
            "date": "2026-10-07",
        }
        response = self.client.post(reverse("support-edit", kwargs={"pk": self.support.pk}), post_data)
        self.assertEqual(response.status_code, 200)
        self.support.refresh_from_db()
        self.assertEqual(self.support.staff, new_staff)

    def test_support_delete_view(self):
        response = self.client.post(reverse("support-delete", kwargs={"pk": self.support.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(BeamlineSupport.objects.filter(pk=self.support.pk).exists())

    def test_calendar_view_templatetag(self):
        cal_data = calendar_view(self.today.year, self.today.isocalendar()[1])
        self.assertIn("week", cal_data)
        day_key = self.today.strftime("%Y-%m-%d")
        self.assertIn(day_key, cal_data["week"])
        self.assertEqual(cal_data["week"][day_key]["support"], self.support)
