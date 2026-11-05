from datetime import date, timedelta
from io import StringIO
from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from basiclive.core.lims.forms import AddShipmentForm, ShipmentForm
from basiclive.core.lims.models import (
    Beamline,
    Country,
    Project,
    ProjectMembership,
    ProjectType,
    Region,
    Session,
    Shipment,
    User,
)
from basiclive.core.lims.providers import (
    BaseProjectProvider,
    ExternalMemberData,
    ExternalProjectData,
    ExternalUserData,
    HttpProjectProvider,
    get_project_provider,
)
from basiclive.core.schedule.forms import BeamtimeForm
from basiclive.core.schedule.models import AccessType


class ProjectLifecycleAndProvenanceTests(TestCase):
    def setUp(self):
        self.today = timezone.localdate()

    def test_project_has_provenance_and_validity_fields(self):
        project = Project.objects.create(
            name="syn-1001",
            source_id="EXT-1001",
            start_date=self.today - timedelta(days=10),
            end_date=self.today + timedelta(days=10),
            external_roster=[{"username": "jdoe", "email": "jdoe@example.org", "role": "PI"}],
        )
        project.refresh_from_db()
        self.assertEqual(project.source_id, "EXT-1001")
        self.assertEqual(project.start_date, self.today - timedelta(days=10))
        self.assertEqual(project.end_date, self.today + timedelta(days=10))
        self.assertEqual(len(project.external_roster), 1)
        self.assertEqual(project.external_roster[0]["username"], "jdoe")

    def test_project_lifecycle_states_and_querysets(self):
        unbounded = Project.objects.create(name="unbounded-proj")
        pending = Project.objects.create(
            name="pending-proj",
            start_date=self.today + timedelta(days=5),
            end_date=self.today + timedelta(days=30),
        )
        active = Project.objects.create(
            name="active-proj",
            start_date=self.today - timedelta(days=5),
            end_date=self.today + timedelta(days=5),
        )
        expired = Project.objects.create(
            name="expired-proj",
            start_date=self.today - timedelta(days=30),
            end_date=self.today - timedelta(days=1),
        )

        # Properties
        self.assertFalse(unbounded.is_pending)
        self.assertFalse(unbounded.is_expired)
        self.assertTrue(unbounded.is_operational)

        self.assertTrue(pending.is_pending)
        self.assertFalse(pending.is_expired)
        self.assertTrue(pending.is_operational)

        self.assertFalse(active.is_pending)
        self.assertFalse(active.is_expired)
        self.assertTrue(active.is_operational)

        self.assertFalse(expired.is_pending)
        self.assertTrue(expired.is_expired)
        self.assertFalse(expired.is_operational)

        # QuerySet filters
        operational_names = set(
            Project.objects.filter(
                pk__in=[unbounded.pk, pending.pk, active.pk, expired.pk]
            ).operational().values_list("name", flat=True)
        )
        self.assertEqual(operational_names, {"unbounded-proj", "pending-proj", "active-proj"})

        currently_active_names = set(
            Project.objects.filter(
                pk__in=[unbounded.pk, pending.pk, active.pk, expired.pk]
            ).currently_active().values_list("name", flat=True)
        )
        self.assertEqual(currently_active_names, {"unbounded-proj", "active-proj"})

    def test_active_status_reflects_pending_and_expired_states(self):
        pending = Project.objects.create(
            name="status-pending",
            start_date=self.today + timedelta(days=2),
        )
        expired = Project.objects.create(
            name="status-expired",
            end_date=self.today - timedelta(days=2),
        )
        active_window = Project.objects.create(
            name="status-window",
            start_date=self.today - timedelta(days=2),
            end_date=self.today + timedelta(days=2),
        )

        self.assertEqual(pending.active_status(), "Pending")
        self.assertEqual(expired.active_status(), "Expired")
        self.assertEqual(active_window.active_status(), "New")

        beamline = Beamline.objects.create(name="08ID-1", acronym="08ID-1", contact_phone="555")
        Session.objects.create(name="S1", project=active_window, beamline=beamline)
        self.assertEqual(active_window.active_status(), "Active")

    def test_clean_rejects_end_date_before_start_date(self):
        project = Project(
            name="invalid-dates",
            start_date=self.today + timedelta(days=5),
            end_date=self.today + timedelta(days=1),
        )
        with self.assertRaises(ValidationError) as ctx:
            project.clean()
        self.assertIn("end_date", ctx.exception.message_dict)


class OperationalGatingAndHybridDeleteTests(TestCase):
    def setUp(self):
        self.today = timezone.localdate()
        self.admin = User.objects.create_superuser(
            username="admin_user", email="admin@example.org", password="secret"
        )
        self.researcher = User.objects.create_user(
            username="researcher", email="researcher@example.org", password="secret"
        )

        self.unbounded = Project.objects.create(name="proj-unbounded", pi=self.researcher)
        self.pending = Project.objects.create(
            name="proj-pending",
            pi=self.researcher,
            start_date=self.today + timedelta(days=7),
            end_date=self.today + timedelta(days=30),
        )
        self.active = Project.objects.create(
            name="proj-active",
            pi=self.researcher,
            start_date=self.today - timedelta(days=7),
            end_date=self.today + timedelta(days=7),
        )
        self.expired = Project.objects.create(
            name="proj-expired",
            pi=self.researcher,
            start_date=self.today - timedelta(days=30),
            end_date=self.today - timedelta(days=1),
        )
        self.beamline = Beamline.objects.create(
            name="08ID-1", acronym="08ID-1", contact_phone="555-0100"
        )
        self.access_type = AccessType.objects.create(
            name="Regular", email_subject="Shift", email_body="Body"
        )

    def test_add_shipment_form_gates_expired_projects(self):
        form = AddShipmentForm(user=self.admin)
        qs_pks = set(form.fields["project"].queryset.values_list("pk", flat=True))
        self.assertIn(self.unbounded.pk, qs_pks)
        self.assertIn(self.pending.pk, qs_pks)
        self.assertIn(self.active.pk, qs_pks)
        self.assertNotIn(self.expired.pk, qs_pks)

        for valid_proj in (self.unbounded, self.pending, self.active):
            valid_form = AddShipmentForm(
                data={"project": valid_proj.pk, "name": f"Ship-{valid_proj.name}", "comments": ""},
                user=self.researcher,
            )
            self.assertTrue(valid_form.is_valid(), valid_form.errors)

        invalid_form = AddShipmentForm(
            data={"project": self.expired.pk, "name": "Ship-Expired", "comments": ""},
            user=self.researcher,
        )
        self.assertFalse(invalid_form.is_valid())

    def test_shipment_form_gates_new_shipment_on_expired_project_but_allows_edit(self):
        new_expired = ShipmentForm(
            data={"project": self.expired.pk, "name": "New-Expired", "comments": ""}
        )
        self.assertFalse(new_expired.is_valid())

        existing = Shipment.objects.create(project=self.expired, name="Historical-Ship")
        edit_expired = ShipmentForm(
            instance=existing,
            data={"project": self.expired.pk, "name": "Historical-Ship-Renamed", "comments": "Updated"},
        )
        self.assertTrue(edit_expired.is_valid(), edit_expired.errors)

    def test_shipment_create_view_blocks_expired_active_project(self):
        self.client.force_login(self.researcher)

        # Switch to pending project -> allowed
        self.client.get(reverse("switch-project", kwargs={"pk": self.pending.pk}))
        resp_pending = self.client.get(reverse("shipment-new"))
        self.assertEqual(resp_pending.status_code, 200)

        # Switch to expired project -> switching succeeds and historical data is readable,
        # but creating a new shipment returns 403
        switch_resp = self.client.get(reverse("switch-project", kwargs={"pk": self.expired.pk}))
        self.assertEqual(switch_resp.status_code, 302)
        self.assertEqual(self.client.session.get("active_project_id"), self.expired.pk)

        data_resp = self.client.get(reverse("data-list"))
        self.assertEqual(data_resp.status_code, 200)

        resp_expired = self.client.get(reverse("shipment-new"))
        self.assertEqual(resp_expired.status_code, 403)

    def test_beamtime_form_gates_expired_projects(self):
        form = BeamtimeForm()
        qs_pks = set(form.fields["project"].queryset.values_list("pk", flat=True))
        self.assertIn(self.unbounded.pk, qs_pks)
        self.assertIn(self.pending.pk, qs_pks)
        self.assertIn(self.active.pk, qs_pks)
        self.assertNotIn(self.expired.pk, qs_pks)

        start = timezone.now() + timedelta(days=10)
        end = start + timedelta(hours=8)

        for valid_proj in (self.pending, self.active):
            valid_bt = BeamtimeForm(
                data={
                    "project": valid_proj.pk,
                    "beamline": self.beamline.pk,
                    "start": start.strftime("%Y-%m-%d %H:%M:%S"),
                    "end": end.strftime("%Y-%m-%d %H:%M:%S"),
                    "access": self.access_type.pk,
                    "comments": "",
                }
            )
            self.assertTrue(valid_bt.is_valid(), valid_bt.errors)

        invalid_bt = BeamtimeForm(
            data={
                "project": self.expired.pk,
                "beamline": self.beamline.pk,
                "start": start.strftime("%Y-%m-%d %H:%M:%S"),
                "end": end.strftime("%Y-%m-%d %H:%M:%S"),
                "access": self.access_type.pk,
                "comments": "",
            }
        )
        self.assertFalse(invalid_bt.is_valid())

    def test_project_delete_guards_external_projects_and_allows_local_projects(self):
        local_proj = Project.objects.create(name="local-facility-acct", source_id=None)
        external_proj = Project.objects.create(name="external-synced-proj", source_id="PORTAL-999")

        self.client.force_login(self.admin)

        # External project cannot be deleted via UI
        ext_get = self.client.get(reverse("project-delete", kwargs={"name": external_proj.name}))
        self.assertEqual(ext_get.status_code, 403)
        ext_post = self.client.post(reverse("project-delete", kwargs={"name": external_proj.name}))
        self.assertEqual(ext_post.status_code, 403)
        self.assertTrue(Project.objects.filter(pk=external_proj.pk).exists())

        # Local project can be accessed and deleted via UI
        loc_get = self.client.get(reverse("project-delete", kwargs={"name": local_proj.name}))
        self.assertEqual(loc_get.status_code, 200)
        loc_post = self.client.post(reverse("project-delete", kwargs={"name": local_proj.name}))
        self.assertIn(loc_post.status_code, (200, 302))
        self.assertFalse(Project.objects.filter(pk=local_proj.pk).exists())


class DummyProjectProvider(BaseProjectProvider):
    def fetch_projects(self):
        return []


class ProjectProviderConfigTests(TestCase):
    def test_default_provider_is_none(self):
        self.assertIsNone(get_project_provider())

    def test_resolve_from_dotted_string(self):
        with override_settings(
            BASICLIVE_LIMS={
                "PROJECT_PROVIDER": "basiclive.core.lims.tests.test_project_providers.DummyProjectProvider"
            }
        ):
            provider = get_project_provider()
            self.assertIsInstance(provider, DummyProjectProvider)
            self.assertEqual(provider.cache_ttl, 900)
            self.assertEqual(provider.options, {})

    def test_resolve_from_backend_options_dict(self):
        with override_settings(
            BASICLIVE_LIMS={
                "PROJECT_PROVIDER": {
                    "BACKEND": "basiclive.core.lims.providers.HttpProjectProvider",
                    "CACHE_TTL": 300,
                    "OPTIONS": {
                        "base_url": "https://portal.example.org/api/v1",
                        "projects_endpoint": "/proposals/active/",
                        "timeout": 5.0,
                    },
                }
            }
        ):
            provider = get_project_provider()
            self.assertIsInstance(provider, HttpProjectProvider)
            self.assertEqual(provider.cache_ttl, 300)
            self.assertEqual(provider.base_url, "https://portal.example.org/api/v1")
            self.assertEqual(provider.projects_endpoint, "/proposals/active/")
            self.assertEqual(provider.timeout, 5.0)

    def test_invalid_provider_config_raises_value_error(self):
        with override_settings(BASICLIVE_LIMS={"PROJECT_PROVIDER": 12345}):
            with self.assertRaises(ValueError):
                get_project_provider()


class StaticSyncProvider(BaseProjectProvider):
    projects_to_return: list[ExternalProjectData] = []

    def fetch_projects(self):
        return list(self.projects_to_return)


class BulkProjectSyncTests(TestCase):
    def setUp(self):
        self.today = timezone.localdate()
        self.existing_pi = User.objects.create_user(
            username="pi_existing",
            email="pi@facility.org",
            first_name="Ada",
            last_name="Lovelace",
        )
        self.existing_member = User.objects.create_user(
            username="member_existing",
            email="member@facility.org",
            first_name="Grace",
            last_name="Hopper",
        )
        self.stale_member = User.objects.create_user(
            username="stale_user",
            email="stale@facility.org",
        )

    def test_sync_projects_upserts_without_eager_user_creation_and_preserves_local_projects(self):
        # Local facility project (source_id=None) must never be modified or deleted
        local_facility = Project.objects.create(
            name="facility-account",
            source_id=None,
            contact_person="Beamline Staff",
        )

        # Pre-existing project to be linked on first sync and have stale membership pruned
        preexisting = Project.objects.create(
            name="gu-2001",
            source_id="PORTAL-2001",
            pi=self.stale_member,
        )

        initial_user_count = User.objects.count()

        StaticSyncProvider.projects_to_return = [
            ExternalProjectData(
                source_id="PORTAL-1001",
                name="gu-1001",
                start_date=self.today - timedelta(days=5),
                end_date=self.today + timedelta(days=60),
                contact_person="Ada Lovelace",
                contact_email="pi@facility.org",
                organisation="Analytical Engine Lab",
                country_code="CA",
                region_code="CA-SK",
                members=[
                    ExternalMemberData(
                        username="pi_existing",
                        email="pi@facility.org",
                        first_name="Ada",
                        last_name="Lovelace",
                        role=ProjectMembership.Role.PI,
                    ),
                    ExternalMemberData(
                        username="",
                        email="MEMBER@FACILITY.ORG",  # Case-insensitive email match
                        first_name="Grace",
                        last_name="Hopper",
                        role=ProjectMembership.Role.CO_INVESTIGATOR,
                    ),
                    ExternalMemberData(
                        username="unlogged_researcher",
                        email="newperson@university.edu",
                        first_name="New",
                        last_name="Person",
                        role=ProjectMembership.Role.MEMBER,
                    ),
                ],
            ),
            ExternalProjectData(
                source_id="PORTAL-2001",
                name="gu-2001",
                start_date=self.today + timedelta(days=10),
                end_date=self.today + timedelta(days=90),
                contact_person="Unlogged PI",
                contact_email="unlogged_pi@university.edu",
                members=[
                    ExternalMemberData(
                        username="unlogged_pi",
                        email="unlogged_pi@university.edu",
                        first_name="Unlogged",
                        last_name="PI",
                        role=ProjectMembership.Role.PI,
                    ),
                    ExternalMemberData(
                        username="member_existing",
                        email="member@facility.org",
                        role=ProjectMembership.Role.MEMBER,
                    ),
                ],
            ),
        ]

        provider = StaticSyncProvider()
        stats = provider.sync_projects()

        self.assertEqual(stats["created"], 1)
        self.assertEqual(stats["updated"], 1)

        # No new User accounts were created for unlogged_researcher or unlogged_pi
        self.assertEqual(User.objects.count(), initial_user_count)
        self.assertFalse(User.objects.filter(username="unlogged_researcher").exists())
        self.assertFalse(User.objects.filter(username="unlogged_pi").exists())

        # Verify PORTAL-1001 creation, attributes, geographic resolution, and roster
        proj1 = Project.objects.get(source_id="PORTAL-1001")
        self.assertEqual(proj1.name, "gu-1001")
        self.assertEqual(proj1.start_date, self.today - timedelta(days=5))
        self.assertEqual(proj1.end_date, self.today + timedelta(days=60))
        self.assertEqual(proj1.contact_person, "Ada Lovelace")
        self.assertEqual(proj1.organisation, "Analytical Engine Lab")
        self.assertIsNotNone(proj1.country)
        self.assertEqual(proj1.country.alpha2, "CA")
        self.assertIsNotNone(proj1.region)
        self.assertEqual(proj1.region.code, "CA-SK")
        self.assertEqual(proj1.pi, self.existing_pi)
        self.assertEqual(len(proj1.external_roster), 3)

        # Existing users have ProjectMembership with mapped roles
        m_pi = ProjectMembership.objects.get(project=proj1, user=self.existing_pi)
        self.assertEqual(m_pi.role, ProjectMembership.Role.PI)
        m_coi = ProjectMembership.objects.get(project=proj1, user=self.existing_member)
        self.assertEqual(m_coi.role, ProjectMembership.Role.CO_INVESTIGATOR)

        # Verify PORTAL-2001 update: stale_member removed, unlogged PI leaves project.pi=None
        preexisting.refresh_from_db()
        self.assertIsNone(preexisting.pi)
        self.assertFalse(
            ProjectMembership.objects.filter(project=preexisting, user=self.stale_member).exists()
        )
        self.assertTrue(
            ProjectMembership.objects.filter(
                project=preexisting,
                user=self.existing_member,
                role=ProjectMembership.Role.MEMBER,
            ).exists()
        )

        # Local project is completely untouched
        local_facility.refresh_from_db()
        self.assertIsNone(local_facility.source_id)
        self.assertEqual(local_facility.contact_person, "Beamline Staff")

    def test_sync_projects_management_command(self):
        StaticSyncProvider.projects_to_return = [
            ExternalProjectData(
                source_id="CMD-3001",
                name="cmd-3001",
                start_date=self.today,
                end_date=self.today + timedelta(days=30),
                members=[],
            )
        ]
        out = StringIO()
        with override_settings(
            BASICLIVE_LIMS={
                "PROJECT_PROVIDER": "basiclive.core.lims.tests.test_project_providers.StaticSyncProvider"
            }
        ):
            call_command("sync_projects", stdout=out)

        self.assertTrue(Project.objects.filter(source_id="CMD-3001", name="cmd-3001").exists())
        self.assertIn("Created: 1", out.getvalue())

    def test_sync_projects_clears_incompatible_region_and_normalizes_roster_and_role_precedence(self):
        # First sync sets CA and CA-SK
        StaticSyncProvider.projects_to_return = [
            ExternalProjectData(
                source_id="PORTAL-4001",
                name="gu-4001",
                country_code="CA",
                region_code="CA-SK",
                members=[
                    ExternalMemberData(
                        username="member_existing",
                        email="member@facility.org",
                        role="CO_I",
                    ),
                    ExternalMemberData(
                        username="member_existing",
                        email="member@facility.org",
                        role="MEMBER",
                    ),
                ],
            )
        ]
        provider = StaticSyncProvider()
        provider.sync_projects()

        proj = Project.objects.get(source_id="PORTAL-4001")
        self.assertEqual(proj.country.alpha2, "CA")
        self.assertEqual(proj.region.code, "CA-SK")
        # Roster stores normalized role
        self.assertEqual(proj.external_roster[0]["role"], ProjectMembership.Role.CO_INVESTIGATOR)
        # CO_INVESTIGATOR wins over MEMBER when user is listed twice
        membership = ProjectMembership.objects.get(project=proj, user=self.existing_member)
        self.assertEqual(membership.role, ProjectMembership.Role.CO_INVESTIGATOR)

        # Second sync changes country to US without a region -> must clear incompatible CA-SK region
        StaticSyncProvider.projects_to_return = [
            ExternalProjectData(
                source_id="PORTAL-4001",
                name="gu-4001",
                country_code="US",
                region_code=None,
                members=[],
            )
        ]
        provider.sync_projects()
        proj.refresh_from_db()
        self.assertEqual(proj.country.alpha2, "US")
        self.assertIsNone(proj.region)


class HttpProjectProviderTests(TestCase):
    @patch("basiclive.core.lims.providers.httpx2.get")
    def test_http_project_provider_maps_custom_fields_and_roles(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {
                    "id": 4201,
                    "proposal_id": "mx-4201",
                    "start_date": "2026-01-15",
                    "end_date": "2027-01-15T00:00:00Z",
                    "institution": "Light Source Institute",
                    "pi_name": "Marie Curie",
                    "pi_email": "mcurie@radium.org",
                    "country": "FR",
                    "team": [
                        {
                            "username": "mcurie",
                            "email": "mcurie@radium.org",
                            "first_name": "Marie",
                            "last_name": "Curie",
                            "role": "LEAD_PI",
                        },
                        {
                            "username": "pcurie",
                            "email": "pcurie@radium.org",
                            "first_name": "Pierre",
                            "last_name": "Curie",
                            "role": "CO_I",
                        },
                        {
                            "username": "student1",
                            "email": "student1@radium.org",
                            "role": "EXPERIMENTER",
                        },
                    ],
                }
            ]
        }
        mock_get.return_value = mock_response

        provider = HttpProjectProvider(
            base_url="https://portal.facility.example.org/api/v1",
            headers={"Authorization": "Bearer secret-token"},
            timeout=7.5,
            projects_endpoint="/projects/active/",
            field_map={
                "source_id": "id",
                "name": "proposal_id",
                "start_date": "start_date",
                "end_date": "end_date",
                "organisation": "institution",
                "contact_person": "pi_name",
                "contact_email": "pi_email",
                "country_code": "country",
                "members": "team",
            },
            role_map={
                "LEAD_PI": "PI",
                "CO_I": "CO_INVESTIGATOR",
                "EXPERIMENTER": "MEMBER",
            },
        )

        projects = list(provider.fetch_projects())
        mock_get.assert_called_once_with(
            "https://portal.facility.example.org/api/v1/projects/active/",
            headers={"Authorization": "Bearer secret-token"},
            timeout=7.5,
            follow_redirects=True,
        )
        self.assertEqual(len(projects), 1)
        proj = projects[0]
        self.assertEqual(proj.source_id, "4201")
        self.assertEqual(proj.name, "mx-4201")
        self.assertEqual(proj.start_date, date(2026, 1, 15))
        self.assertEqual(proj.end_date, date(2027, 1, 15))
        self.assertEqual(proj.organisation, "Light Source Institute")
        self.assertEqual(proj.contact_person, "Marie Curie")
        self.assertEqual(proj.contact_email, "mcurie@radium.org")
        self.assertEqual(proj.country_code, "FR")
        self.assertEqual(len(proj.members), 3)
        self.assertEqual(proj.members[0].role, ProjectMembership.Role.PI)
        self.assertEqual(proj.members[1].role, ProjectMembership.Role.CO_INVESTIGATOR)
        self.assertEqual(proj.members[2].role, ProjectMembership.Role.MEMBER)


class DeferredUserSyncTests(TestCase):
    def setUp(self):
        cache.clear()
        self.today = timezone.localdate()

    def tearDown(self):
        cache.clear()

    def test_sync_user_matches_staged_external_roster_and_populates_blank_profile_fields(self):
        # Project synced earlier when rfranklin had not yet logged in
        proj_pi = Project.objects.create(
            name="dna-51",
            source_id="PORTAL-51",
            external_roster=[
                {
                    "username": "rfranklin",
                    "email": "rfranklin@kings.ac.uk",
                    "first_name": "Rosalind",
                    "last_name": "Franklin",
                    "role": "PI",
                    "phone": "555-1952",
                }
            ],
        )
        proj_member = Project.objects.create(
            name="dna-52",
            source_id="PORTAL-52",
            external_roster=[
                {
                    "username": "",
                    "email": "RFRANKLIN@KINGS.AC.UK",  # Case-insensitive email match
                    "first_name": "Rosalind",
                    "last_name": "Franklin",
                    "role": "CO_INVESTIGATOR",
                    "phone": "555-1952",
                }
            ],
        )

        # User created with minimal info on first SSO/LDAP login
        user = User.objects.create_user(
            username="rfranklin",
            email="rfranklin@kings.ac.uk",
            first_name="",
            last_name="",
            phone="",
        )

        provider = DummyProjectProvider(cache_ttl=900)
        synced = provider.sync_user(user)
        self.assertTrue(synced)

        user.refresh_from_db()
        self.assertEqual(user.first_name, "Rosalind")
        self.assertEqual(user.last_name, "Franklin")
        self.assertEqual(user.phone, "555-1952")
        self.assertEqual(user.name, "Rosalind Franklin")

        proj_pi.refresh_from_db()
        self.assertEqual(proj_pi.pi, user)
        self.assertTrue(
            ProjectMembership.objects.filter(
                project=proj_pi, user=user, role=ProjectMembership.Role.PI
            ).exists()
        )
        self.assertTrue(
            ProjectMembership.objects.filter(
                project=proj_member, user=user, role=ProjectMembership.Role.CO_INVESTIGATOR
            ).exists()
        )

    def test_sync_user_respects_cache_ttl_and_force_flag(self):
        user = User.objects.create_user(username="cached_researcher", email="cached@example.org")
        provider = DummyProjectProvider(cache_ttl=900)

        with patch.object(provider, "fetch_user", return_value=None) as mock_fetch:
            self.assertTrue(provider.sync_user(user))
            self.assertEqual(mock_fetch.call_count, 1)

            # Second call within TTL window is skipped
            self.assertFalse(provider.sync_user(user))
            self.assertEqual(mock_fetch.call_count, 1)

            # force=True bypasses cache guard
            self.assertTrue(provider.sync_user(user, force=True))
            self.assertEqual(mock_fetch.call_count, 2)

        # When cache_ttl is 0 or None, automatic login sync (force=False) is disabled
        disabled_provider = DummyProjectProvider(cache_ttl=0)
        self.assertFalse(disabled_provider.sync_user(user, force=False))
        self.assertTrue(disabled_provider.sync_user(user, force=True))

    def test_sync_user_reconciles_external_user_data_and_upserts_projects(self):
        existing_proj = Project.objects.create(name="existing-mx", source_id="EXT-MX-1")
        user = User.objects.create_user(username=" DorothyH ", email="dhodgkin@ox.ac.uk".strip())
        user.username = "dhodgkin"
        user.save()

        ext_user_data = ExternalUserData(
            username="dhodgkin",
            email="dhodgkin@ox.ac.uk",
            first_name="Dorothy",
            last_name="Hodgkin",
            phone="555-1964",
            projects=[
                ExternalProjectData(
                    source_id="EXT-B12",
                    name="vit-b12",
                    start_date=self.today - timedelta(days=1),
                    end_date=self.today + timedelta(days=100),
                    organisation="Oxford University",
                    members=[
                        ExternalMemberData(
                            username="dhodgkin",
                            email="dhodgkin@ox.ac.uk",
                            role="PI",
                        )
                    ],
                ),
                ("EXT-MX-1", "CO_INVESTIGATOR"),
            ],
        )

        provider = DummyProjectProvider(cache_ttl=900)
        with patch.object(provider, "fetch_user", return_value=ext_user_data):
            self.assertTrue(provider.sync_user(user))

        user.refresh_from_db()
        self.assertEqual(user.first_name, "Dorothy")
        self.assertEqual(user.last_name, "Hodgkin")
        self.assertEqual(user.phone, "555-1964")

        upserted_proj = Project.objects.get(source_id="EXT-B12")
        self.assertEqual(upserted_proj.name, "vit-b12")
        self.assertEqual(upserted_proj.pi, user)
        self.assertTrue(
            ProjectMembership.objects.filter(
                project=upserted_proj, user=user, role=ProjectMembership.Role.PI
            ).exists()
        )
        self.assertTrue(
            ProjectMembership.objects.filter(
                project=existing_proj, user=user, role=ProjectMembership.Role.CO_INVESTIGATOR
            ).exists()
        )

    @patch("basiclive.core.lims.providers.httpx2.get")
    def test_http_project_provider_fetch_user_parses_user_and_projects(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "username": "kbanister",
            "email": "kbanister@beamline.org",
            "first_name": "K.",
            "last_name": "Banister",
            "phone": "555-0199",
            "projects": [
                {
                    "id": "P-900",
                    "proposal_id": "px-900",
                    "start_date": "2026-03-01",
                    "end_date": "2026-12-31",
                    "role": "LEAD_PI",
                },
                {
                    "id": "P-901",
                    "role": "EXPERIMENTER",
                },
            ],
        }
        mock_get.return_value = mock_response

        provider = HttpProjectProvider(
            base_url="https://portal.facility.example.org/api/v1",
            user_projects_endpoint="/users/{username}/projects/",
            field_map={
                "source_id": "id",
                "name": "proposal_id",
            },
            role_map={
                "LEAD_PI": "PI",
                "EXPERIMENTER": "MEMBER",
            },
        )
        user = User.objects.create_user(username="kbanister", email="kbanister@beamline.org")
        ext_user = provider.fetch_user(user)

        mock_get.assert_called_once_with(
            "https://portal.facility.example.org/api/v1/users/kbanister/projects/",
            headers={},
            timeout=10.0,
            follow_redirects=True,
        )
        self.assertIsNotNone(ext_user)
        self.assertEqual(ext_user.first_name, "K.")
        self.assertEqual(ext_user.last_name, "Banister")
        self.assertEqual(ext_user.phone, "555-0199")
        self.assertEqual(len(ext_user.projects), 2)

    def test_sync_user_handles_fetch_user_network_error_gracefully(self):
        proj = Project.objects.create(
            name="fallback-proj",
            source_id="EXT-FALLBACK",
            external_roster=[
                {
                    "username": "resilient_user",
                    "email": "resilient@example.org",
                    "role": "MEMBER",
                }
            ],
        )
        user = User.objects.create_user(username="resilient_user", email="resilient@example.org")
        provider = DummyProjectProvider(cache_ttl=900)

        with patch.object(provider, "fetch_user", side_effect=RuntimeError("Portal API timeout")):
            with self.assertLogs("basiclive.core.lims.providers", level="WARNING") as cm:
                result = provider.sync_user(user)

        self.assertTrue(result)
        self.assertTrue(any("Portal API timeout" in msg for msg in cm.output))
        self.assertTrue(
            ProjectMembership.objects.filter(
                project=proj, user=user, role=ProjectMembership.Role.MEMBER
            ).exists()
        )
        # Transient fetch_user failure must not stamp the TTL cache, allowing immediate retry
        with patch.object(provider, "fetch_user", return_value=None) as retry_fetch:
            self.assertTrue(provider.sync_user(user))
            self.assertEqual(retry_fetch.call_count, 1)

    def test_sync_user_project_upsert_preserves_existing_pi_memberships_and_roster(self):
        pi_user = User.objects.create_user(username="pi_leader", email="pi@beamline.org")
        team_user = User.objects.create_user(username="team_member", email="member@beamline.org")

        staged_roster = [
            {"username": "pi_leader", "email": "pi@beamline.org", "role": "PI"},
            {"username": "team_member", "email": "member@beamline.org", "role": "MEMBER"},
        ]
        proj = Project.objects.create(
            name="shared-proj",
            source_id="EXT-SHARED-1",
            pi=pi_user,
            external_roster=staged_roster,
        )

        # User B (team_member) logs in and fetch_user returns a user-scoped project summary
        # that only lists team_member's own role (not the full team roster)
        ext_user_data = ExternalUserData(
            username="team_member",
            email="member@beamline.org",
            projects=[
                ExternalProjectData(
                    source_id="EXT-SHARED-1",
                    name="shared-proj",
                    organisation="Updated Institute",
                    members=[
                        ExternalMemberData(
                            username="team_member",
                            email="member@beamline.org",
                            role=ProjectMembership.Role.MEMBER,
                        )
                    ],
                )
            ],
        )

        provider = DummyProjectProvider(cache_ttl=900)
        with patch.object(provider, "fetch_user", return_value=ext_user_data):
            self.assertTrue(provider.sync_user(team_user))

        proj.refresh_from_db()
        self.assertEqual(proj.organisation, "Updated Institute")
        # Existing PI, PI's membership, and full staged external_roster must be preserved
        self.assertEqual(proj.pi, pi_user)
        self.assertEqual(proj.external_roster, staged_roster)
        self.assertTrue(
            ProjectMembership.objects.filter(
                project=proj, user=pi_user, role=ProjectMembership.Role.PI
            ).exists()
        )
        self.assertTrue(
            ProjectMembership.objects.filter(
                project=proj, user=team_user, role=ProjectMembership.Role.MEMBER
            ).exists()
        )

    def test_login_triggers_sync_user_and_resolves_active_project_immediately(self):
        proj = Project.objects.create(
            name="login-proj-1",
            source_id="EXT-LOGIN-1",
            external_roster=[
                {
                    "username": "newlogin",
                    "email": "newlogin@example.org",
                    "first_name": "New",
                    "last_name": "Login",
                    "role": "PI",
                }
            ],
        )
        user = User.objects.create_user(
            username="newlogin",
            email="newlogin@example.org",
            password="secret",
            first_name="",
            last_name="",
        )

        with override_settings(
            BASICLIVE_LIMS={
                "PROJECT_PROVIDER": "basiclive.core.lims.tests.test_project_providers.DummyProjectProvider"
            }
        ):
            logged_in = self.client.login(username="newlogin", password="secret")
            self.assertTrue(logged_in)

            proj.refresh_from_db()
            user.refresh_from_db()
            self.assertEqual(proj.pi, user)
            self.assertEqual(user.first_name, "New")
            self.assertEqual(user.last_name, "Login")

            resp = self.client.get(reverse("data-list"))
            self.assertEqual(resp.status_code, 200)
            user.refresh_from_db()
            self.assertEqual(user.default_project, proj)
            self.assertEqual(self.client.session.get("active_project_id"), proj.pk)

    @patch("basiclive.core.lims.providers.httpx2.get", side_effect=RuntimeError("Connection refused"))
    def test_login_succeeds_when_external_api_errors(self, _mock_get):
        proj = Project.objects.create(
            name="offline-portal-proj",
            source_id="EXT-OFFLINE-1",
            external_roster=[
                {
                    "username": "offline_login",
                    "email": "offline@example.org",
                    "role": "MEMBER",
                }
            ],
        )
        user = User.objects.create_user(
            username="offline_login",
            email="offline@example.org",
            password="secret",
        )

        with override_settings(
            BASICLIVE_LIMS={
                "PROJECT_PROVIDER": {
                    "BACKEND": "basiclive.core.lims.providers.HttpProjectProvider",
                    "CACHE_TTL": 900,
                    "OPTIONS": {
                        "base_url": "https://portal.facility.example.org/api/v1",
                        "user_projects_endpoint": "/users/{username}/projects/",
                    },
                }
            }
        ):
            with self.assertLogs("basiclive.core.lims.providers", level="WARNING"):
                logged_in = self.client.login(username="offline_login", password="secret")
            self.assertTrue(logged_in)
            self.assertTrue(
                ProjectMembership.objects.filter(
                    project=proj, user=user, role=ProjectMembership.Role.MEMBER
                ).exists()
            )

    def test_sync_projects_command_with_user_argument(self):
        proj = Project.objects.create(
            name="cli-user-proj",
            source_id="EXT-CLI-USER",
            external_roster=[
                {
                    "username": "cli_user",
                    "email": "cli@example.org",
                    "role": "CO_INVESTIGATOR",
                }
            ],
        )
        user = User.objects.create_user(username="cli_user", email="cli@example.org")
        out = StringIO()

        with override_settings(
            BASICLIVE_LIMS={
                "PROJECT_PROVIDER": {
                    "BACKEND": "basiclive.core.lims.tests.test_project_providers.DummyProjectProvider",
                    "CACHE_TTL": 0,
                }
            }
        ):
            call_command("sync_projects", "--user", "cli_user", stdout=out)
            self.assertTrue(
                ProjectMembership.objects.filter(
                    project=proj, user=user, role=ProjectMembership.Role.CO_INVESTIGATOR
                ).exists()
            )
            self.assertIn("cli_user", out.getvalue())

            with self.assertRaises(CommandError):
                call_command("sync_projects", "--user", "unknown_username")





