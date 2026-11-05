import unittest

from django.http import HttpResponse
from django.template import Context, Template
from django.test import SimpleTestCase, override_settings
from django.urls import include, path

import basiclive.core.lims.urls as lims_urls
import basiclive.core.lims.views as lims_views

test_urlpatterns = [
    path("", include("basiclive.core.lims.urls")),
    path("logout/", lambda r: HttpResponse("ok"), name="logout"),
]


@override_settings(ROOT_URLCONF="basiclive.core.lims.tests.test_dashboard_delegation")
class DashboardDelegationTests(SimpleTestCase):
    """Test suite verifying removal of turnkey dashboards and delegation to host apps."""

    def test_dashboard_views_removed(self):
        """StaffDashboard and ProjectDetail must not exist in basiclive.core.lims.views."""
        self.assertFalse(hasattr(lims_views, "StaffDashboard"))
        self.assertFalse(hasattr(lims_views, "ProjectDetail"))

    def test_root_route_not_claimed_by_lims_urls(self):
        """basiclive.core.lims.urls must not define a root path '' or 'staff-dashboard'."""
        patterns = [p.pattern.regex.pattern for p in lims_urls.urlpatterns if hasattr(p, "pattern")]
        names = [p.name for p in lims_urls.urlpatterns if hasattr(p, "name")]

        self.assertNotIn("^$", patterns)
        self.assertNotIn("staff-dashboard", names)

    def test_navs_template_renders_without_dashboard_named_url(self):
        """navs.html must link to '/' and render without requiring a 'dashboard' named URL pattern."""
        dummy_user = type(
            "DummyUser",
            (),
            {
                "username": "tester",
                "name": "Test User",
                "is_superuser": False,
                "is_authenticated": True,
            },
        )()
        t = Template("{% include 'lims/navs.html' %}")
        rendered = t.render(Context({"APP_NAME": "BasicLIVE", "user": dummy_user}))
        self.assertIn('href="/"', rendered)
        self.assertNotIn('{% url \'dashboard\' %}', rendered)


urlpatterns = test_urlpatterns

if __name__ == "__main__":
    unittest.main()
