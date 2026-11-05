from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from basiclive.core.lims.models import Beamline, Project
from basiclive.core.schedule.models import Beamtime, EmailNotification

User = get_user_model()


class EmailNotificationRecipientTests(TestCase):
    def setUp(self):
        self.pi = User.objects.create_user(username="prof_curie", email="curie@radium.org")
        self.beamline = Beamline.objects.create(name="08B1-1", acronym="08B1-1")
        self.project = Project.objects.create(
            name="radioactivity-lab",
            pi=self.pi,
            contact_email="logistics@radium.org"
        )
        self.beamtime = Beamtime.objects.create(
            project=self.project,
            beamline=self.beamline,
            start=timezone.now() + timedelta(days=14),
            end=timezone.now() + timedelta(days=15)
        )

    @patch('geopy.geocoders.Nominatim.geocode', side_effect=Exception("No network in test"))
    def test_recipient_list_with_pi_and_contact_email(self, mock_geocode):
        notification = EmailNotification(
            beamtime=self.beamtime,
            email_subject="Beamtime Scheduled",
            send_time=timezone.now() + timedelta(days=7)
        )
        recipients = notification.recipient_list()
        self.assertEqual(set(recipients), {"curie@radium.org", "logistics@radium.org"})

    @patch('geopy.geocoders.Nominatim.geocode', side_effect=Exception("No network in test"))
    def test_recipient_list_with_only_pi_email(self, mock_geocode):
        self.project.contact_email = ""
        self.project.save()

        notification = EmailNotification(
            beamtime=self.beamtime,
            email_subject="Beamtime Scheduled",
            send_time=timezone.now() + timedelta(days=7)
        )
        recipients = notification.recipient_list()
        self.assertEqual(recipients, ["curie@radium.org"])

    @patch('geopy.geocoders.Nominatim.geocode', side_effect=Exception("No network in test"))
    def test_recipient_list_with_only_contact_email(self, mock_geocode):
        self.project.pi = None
        self.project.save()

        notification = EmailNotification(
            beamtime=self.beamtime,
            email_subject="Beamtime Scheduled",
            send_time=timezone.now() + timedelta(days=7)
        )
        recipients = notification.recipient_list()
        self.assertEqual(recipients, ["logistics@radium.org"])

    @patch('geopy.geocoders.Nominatim.geocode', side_effect=Exception("No network in test"))
    def test_recipient_list_deduplicates_identical_emails(self, mock_geocode):
        self.project.contact_email = "curie@radium.org"
        self.project.save()

        notification = EmailNotification(
            beamtime=self.beamtime,
            email_subject="Beamtime Scheduled",
            send_time=timezone.now() + timedelta(days=7)
        )
        recipients = notification.recipient_list()
        self.assertEqual(recipients, ["curie@radium.org"])

    @patch('geopy.geocoders.Nominatim.geocode', side_effect=Exception("No network in test"))
    def test_recipient_list_empty_when_no_project(self, mock_geocode):
        orphan_beamtime = Beamtime.objects.create(
            project=None,
            beamline=self.beamline,
            start=timezone.now() + timedelta(days=14),
            end=timezone.now() + timedelta(days=15)
        )
        notification = EmailNotification(
            beamtime=orphan_beamtime,
            email_subject="Beamtime Scheduled",
            send_time=timezone.now() + timedelta(days=7)
        )
        recipients = notification.recipient_list()
        self.assertEqual(recipients, [])
