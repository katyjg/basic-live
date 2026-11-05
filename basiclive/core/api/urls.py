from django.urls import path
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
    TokenVerifyView
)

from basiclive.core.lims.conf import settings as lims_settings
from . import views

urlpatterns = [
    path('v3/auth/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('v3/auth/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('v3/auth/verify/', TokenVerifyView.as_view(), name='token_verify'),

    # V3 routes (JWT Bearer Token / request.project context)
    path('v3/data/<slug:beamline>/', views.AddData.as_view(), name='api-data'),
    path('v3/projects/', views.FetchProjects.as_view(), name='api-projects'),
    path('v3/report/<slug:beamline>/', views.AddReport.as_view(), name='api-report'),
    path('v3/samples/<slug:beamline>/', views.ProjectSamples.as_view(), name='api-project-samples'),
    path('v3/session/<slug:beamline>/<slug:session>/start/', views.LaunchSession.as_view(), name='api-session-start'),
    path('v3/session/<slug:beamline>/<slug:session>/close/', views.CloseSession.as_view(), name='api-session-close'),

    # V2 legacy routes (asymmetric signed URL fallback)
    path('v2/<slug:signature>:<slug:username>/data/<slug:beamline>/', views.AddData.as_view(), name='v2-data'),
    path('v2/<slug:signature>:<slug:username>/report/<slug:beamline>/', views.AddReport.as_view(), name='v2-report'),
    path('v2/<slug:signature>:<slug:username>/samples/<slug:beamline>/', views.ProjectSamples.as_view(), name='v2-project-samples'),
    path('v2/<slug:signature>:<slug:username>/launch/<slug:beamline>/<slug:session>/', views.LaunchSession.as_view(), name='v2-session-launch'),
    path('v2/<slug:signature>:<slug:username>/close/<slug:beamline>/<slug:session>/', views.CloseSession.as_view(), name='v2-session-close'),
]

if lims_settings.USE_ACL:
    import basiclive.core.acl.views as acl_views
    urlpatterns += [
        # v3
        path('v3/accesslist/', acl_views.EndpointList.as_view()),
        path('v3/keys/<slug:username>/', acl_views.AccessKeys.as_view()),

        # v2
        path('v2/accesslist/', acl_views.EndpointList.as_view()),
        path('v2/keys/<slug:username>/', acl_views.AccessKeys.as_view()),

    ]
