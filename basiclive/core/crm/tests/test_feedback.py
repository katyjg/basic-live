from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.urls import reverse

from basiclive.core.crm.models import Feedback, SupportArea, LikertScale
from basiclive.core.lims.models import Beamline, Project, Session
from basiclive.utils.encrypt import decrypt

User = get_user_model()


class FeedbackTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.pi = User.objects.create_user(username="prof_jones", email="jones@college.edu")
        self.project = Project.objects.create(name="archaeology-01", pi=self.pi)
        self.beamline = Beamline.objects.create(name="BioCAT", acronym="08B1-1")
        self.session = Session.objects.create(project=self.project, beamline=self.beamline, name="run-alpha")
        self.client.force_login(self.pi)

    def test_session_feedback_key_generation_and_decryption(self):
        key = self.session.feedback_key()
        self.assertIsInstance(key, str)
        decrypted = decrypt(key)
        self.assertEqual(decrypted, f"{self.project.name}:{self.session.name}")

    def test_feedback_create_view_valid_session(self):
        url = reverse('session-feedback', kwargs={'session': self.session.pk, 'project': self.project.name})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertIn('form', resp.context)
        self.assertEqual(resp.context['form'].initial['session'], self.session)

    def test_feedback_create_view_invalid_session_forbidden(self):
        url = reverse('session-feedback', kwargs={'session': 9999, 'project': 'nonexistent-project'})
        resp = self.client.get(url)
        self.assertIn(resp.status_code, [403, 404])

    def test_feedback_survey_submission(self):
        scale = LikertScale.objects.create(
            statement="How satisfied were you?",
            worst="Very Dissatisfied",
            worse="Dissatisfied",
            better="Satisfied",
            best="Very Satisfied"
        )
        area = SupportArea.objects.create(name="Beamline Software", user_feedback=True, scale=scale)

        url = reverse('session-feedback', kwargs={'session': self.session.pk, 'project': self.project.name})
        post_data = {
            'session': self.session.pk,
            'comments': 'Great remote experiment session!',
            'contact': True,
            'beamline-software': ['2'],
        }
        resp = self.client.post(url, data=post_data)
        self.assertEqual(resp.status_code, 302)

        feedback = Feedback.objects.filter(session=self.session).first()
        self.assertIsNotNone(feedback)
        self.assertEqual(feedback.comments, 'Great remote experiment session!')
        self.assertTrue(feedback.contact)
        self.assertEqual(feedback.session.project.name, 'archaeology-01')

    def test_feedback_form_uses_display_label_and_slugified_name(self):
        from basiclive.core.crm.forms import FeedbackForm
        scale = LikertScale.objects.create(
            statement="Rate your experience:",
            worst="Bad", worse="Poor", better="Good", best="Great"
        )
        area_with_label = SupportArea.objects.create(
            name="Remote Access",
            label="How would you rate the responsiveness of remote access software?",
            user_feedback=True,
            scale=scale,
        )
        area_fallback = SupportArea.objects.create(
            name="Data Storage",
            label="",
            user_feedback=True,
            scale=scale,
        )

        form = FeedbackForm()
        self.assertIn("remote-access", form.fields)
        self.assertEqual(
            form.fields["remote-access"].label,
            "How would you rate the responsiveness of remote access software?"
        )
        self.assertIn("data-storage", form.fields)
        self.assertEqual(form.fields["data-storage"].label, "Data Storage")

    def test_feedback_detail_modal_renders_name_and_label(self):
        from basiclive.core.crm.models import AreaFeedback
        scale = LikertScale.objects.create(statement="Survey", worst="1", worse="2", better="3", best="4")
        area = SupportArea.objects.create(
            name="Impact to potential researchers",
            label="What impact could these facilities have on the research of others in your field?",
            user_feedback=True,
            scale=scale,
        )
        feedback = Feedback.objects.create(session=self.session, comments="Helpful assistance")
        AreaFeedback.objects.create(
            feedback=feedback,
            area=area,
            label="Great",
            rating=2,
        )

        admin_user = User.objects.create_superuser(username="admin_test", email="admin@test.edu")
        self.client.force_login(admin_user)
        url = reverse("user-feedback-detail", kwargs={"pk": feedback.pk})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Impact to potential researchers")
        self.assertContains(resp, "What impact could these facilities have on the research of others in your field?")

