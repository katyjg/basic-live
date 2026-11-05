from django.contrib.auth.views import LogoutView
from django.urls import path
from django.views.decorators.cache import cache_page

from . import views, ajax_views, forms

urlpatterns = [
    path('logout/', LogoutView.as_view(), name='logout'),
    path('projects/', views.ProjectList.as_view(), name='project-list'),
    path('projects/dashboard/', views.ProjectList.as_view(), name='user-dashboard'),
    path('projects/switch/<int:pk>/', views.SwitchProjectView.as_view(), name='switch-project'),
    path('projects/switch/', views.SwitchProjectView.as_view(), name='switch-project-form'),
    path('projects/new/', views.ProjectCreate.as_view(), name='new-project'),
    path('projects/<slug:name>/', views.ProjectProfile.as_view(), name='project-profile'),
    path('projects/<slug:name>/edit/', views.ProjectEdit.as_view(), name='project-edit'),
    path('projects/<slug:name>/labels/', views.ProjectLabels.as_view(), name='project-labels'),
    path('projects/<slug:name>/info/', views.ProjectInfo.as_view(), name='project-info'),
    path('projects/<slug:name>/delete/', views.ProjectDelete.as_view(), name='project-delete'),
    path('regions/', ajax_views.RegionLookup.as_view(), name='region-list-ajax'),

    # User routes
    path('users/', views.UserList.as_view(), name='user-list'),
    path('users/<str:username>/', views.UserDetailView.as_view(), name='user-detail'),
    path('users/<str:username>/edit/', views.UserEditView.as_view(), name='user-edit'),
    path('users/<slug:username>/sshkey/new/', views.SSHKeyCreate.as_view(), name='new-sshkey'),
    path('users/<slug:username>/sshkey/<int:pk>/edit/', views.SSHKeyEdit.as_view(), name='sshkey-edit'),
    path('users/<slug:username>/sshkey/<int:pk>/delete/', views.SSHKeyDelete.as_view(), name='sshkey-delete'),

    path('beamline/<int:pk>/', views.BeamlineDetail.as_view(), name='beamline-detail'),
    path('automounter/<int:pk>/edit/', views.AutomounterEdit.as_view(), name='automounter-edit'),

    path('requests/', views.RequestList.as_view(), name='request-list'),
    path('requests/new/', views.RequestWizardCreate.as_view(), name='request-new'),
    path('requests/<int:pk>/', views.RequestDetail.as_view(), name='request-detail'),
    path('requests/<int:pk>/edit/', views.RequestWizardEdit.as_view(), name='request-edit'),
    path('requests/<int:pk>/delete/', views.RequestDelete.as_view(), name='request-delete'),
    path('requests/<int:pk>/staff/edit/', views.RequestEdit.as_view(), name='request-admin-edit'),
    path('requests/types/', views.RequestTypeList.as_view(), name='request-type-list'),
    path('requests/types/<int:pk>/', views.RequestTypeDetail.as_view(), name='request-type-detail'),
    path('requests/types/new/', views.RequestTypeCreate.as_view(), name='new-request-type'),
    path('requests/types/<int:pk>/edit/', views.RequestTypeEdit.as_view(), name='request-type-edit'),
    path('requests/types/<int:pk>/delete/', views.RequestTypeEdit.as_view(), name='request-type-delete'),
    path('requests/types/<int:pk>/layout/', views.RequestTypeLayout.as_view(), name='request-type-layout'),

    path('shipments/', views.ShipmentList.as_view(), name='shipment-list'),
    path('shipments/new/', views.ShipmentCreate.as_view(), name='shipment-new'),
    path('shipments/<int:pk>/', views.ShipmentDetail.as_view(), name='shipment-detail'),
    path('shipments/<int:pk>/samples/', views.SeatSamples.as_view(), name='seat-samples'),
    path(
        'shipments/<int:pk>/requests/',
        views.ShipmentDetail.as_view(template_name="lims/details/shipment-requests.html"),
        name='shipment-requests'
    ),
    path(
        'shipments/<int:pk>/groups/',
        views.ShipmentDetail.as_view(template_name="lims/details/shipment-samples.html"),
        name='shipment-samples'
    ),
    path('shipments/<int:pk>/data/', views.ShipmentDataList.as_view(), name='shipment-data'),
    path('shipments/<int:pk>/reports/', views.ShipmentReportList.as_view(), name='shipment-reports'),
    path('shipments/<int:pk>/edit/', views.ShipmentEdit.as_view(), name='shipment-edit'),
    path('shipments/<int:pk>/delete/', views.ShipmentDelete.as_view(), name='shipment-delete'),
    path('shipments/<int:pk>/send/', views.SendShipment.as_view(), name='shipment-send'),
    path('shipments/<int:pk>/comments/', views.ShipmentComments.as_view(), name='shipment-comments'),
    path('shipments/<int:pk>/labels/', views.ShipmentLabels.as_view(), name='shipment-labels'),
    path('shipments/<int:pk>/recall-send/', views.RecallSendShipment.as_view(), name='shipment-recall-send'),
    path('shipments/<int:pk>/receive/', views.ReceiveShipment.as_view(), name='shipment-receive'),
    path('shipments/<int:pk>/return/', views.ReturnShipment.as_view(), name='shipment-return'),
    path('shipments/<int:pk>/recall-return/', views.RecallReturnShipment.as_view(), name='shipment-recall-return'),
    path('shipments/<int:pk>/archive/', views.ArchiveShipment.as_view(), name='shipment-archive'),
    path('shipments/<int:pk>/containers/add/', views.ShipmentAddContainer.as_view(), name='shipment-add-containers'),
    path('shipments/<int:pk>/groups/add/', views.ShipmentAddGroup.as_view(), name='shipment-add-groups'),

    path('containers/', views.ContainerList.as_view(), name='container-list'),
    path('containers/<int:pk>/', views.ContainerDetail.as_view(), name='container-detail'),
    path('containers/<int:pk>/history/', views.ContainerHistory.as_view(), name='container-history'),
    path('automounter/<int:pk>/history/', views.AutomounterHistory.as_view(), name='automounter-history'),
    path('containers/<int:pk>/edit/', views.ContainerEdit.as_view(), name='container-edit'),
    path('containers/<int:pk>/samples/', views.ContainerSpreadsheet.as_view(), name='edit-container-samples'),
    path('containers/<int:pk>/delete/', views.ContainerDelete.as_view(), name='container-delete'),
    path('containers/<int:root>/<int:pk>/load/', views.ContainerLoad.as_view(), name='container-load'),
    path('containers/<int:root>/<int:pk>/unload/', ajax_views.UnloadContainer.as_view(), name='container-unload'),
    path(
        'containers/<int:root>/<int:pk>/location/<slug:location>/',
        views.LocationLoad.as_view(), name='location-load'
    ),
    path(
        'containers/<int:root>/<int:pk>/unload-project/<slug:project>/',
        views.EmptyContainers.as_view(), name='empty-containers'
    ),

    path('samples/', views.SampleList.as_view(), name='sample-list'),
    path('samples/<int:pk>/', views.SampleDetail.as_view(), name='sample-detail'),
    path('samples/<int:pk>/edit/', views.SampleEdit.as_view(), name='sample-edit'),
    path('samples/<int:pk>/delete/', views.SampleDelete.as_view(), name='sample-delete'),
    path(
        'samples/<int:pk>/staff/edit/', views.SampleEdit.as_view(form_class=forms.SampleAdminForm),
        name='sample-admin-edit'
    ),

    path('groups/', views.GroupList.as_view(), name='group-list'),
    path('groups/<int:pk>/', views.GroupDetail.as_view(), name='group-detail'),
    path('groups/<int:pk>/edit/', views.GroupEdit.as_view(), name='group-edit'),
    path('groups/<int:pk>/delete/', views.GroupDelete.as_view(), name='group-delete'),

    path('data/', views.DataList.as_view(), name='data-list'),
    path('data/<int:pk>/', views.DataDetail.as_view(), name='data-detail'),

    path('reports/', views.ReportList.as_view(), name='result-list'),
    path('reports/<int:pk>/', views.ReportDetail.as_view(), name='report-detail'),

    path('activity/', views.ActivityLogList.as_view(), name='activitylog-list'),

    path('sessions/', views.SessionList.as_view(), name='session-list'),
    path('sessions/<int:pk>/', views.SessionDetail.as_view(), name='session-detail'),
    path(
        'sessions/<int:pk>/history/',
        views.SessionDetail.as_view(template_name="lims/modal/session-history.html"),
        name='session-history'
    ),
    path(
        'sessions/<int:pk>/statistics/',
        views.SessionStatistics.as_view(template_name="lims/details/session-statistics.html"),
        name='session-statistics'
    ),
    path('sessions/<int:pk>/data/', views.SessionDataList.as_view(), name='session-data'),
    path('sessions/<int:pk>/reports/', views.SessionReportList.as_view(), name='session-reports'),

    path('ajax/create_samples/<int:pk>/', ajax_views.CreateShipmentSamples.as_view(), name='create-samples'),
    path('ajax/update_locations/<int:pk>/', ajax_views.UpdateLocations.as_view(), name='update-locations'),
    path('ajax/update_priority/', cache_page(60*60*24)(ajax_views.UpdatePriority.as_view()), name='update-priority'),
    path('ajax/update_group_priority/', ajax_views.UpdateGroupPriority.as_view(), name='update-group-priority'),
    path('ajax/update_request_priority/', ajax_views.UpdateRequestPriority.as_view(), name='update-request-priority'),
    path('ajax/report/<int:pk>/', ajax_views.FetchReport.as_view(), name='fetch-report'),
    path('ajax/request/', ajax_views.FetchRequest.as_view(), name='fetch-request'),
    path('ajax/bulk_edit/', ajax_views.BulkSampleEdit.as_view(), name='bulk-edit'),
    path('ajax/layout/<int:pk>/', ajax_views.FetchContainerLayout.as_view(), name='fetch-layout'),

    path(
        'guides/<int:pk>/youtube/<slug:video>/',
        views.GuideView.as_view(template_name="lims/modal/guide-youtube.html"),
        name='guide-youtube'
    ),
    path(
        'guides/<int:pk>/flickr/<album>/<photo>/',
        views.GuideView.as_view(template_name="lims/modal/guide-flickr.html"),
        name='guide-flickr'
    ),
    path(
        'guides/<int:pk>/image/',
        views.GuideView.as_view(template_name="lims/modal/guide-image.html"),
        name='guide-image'
    ),
    path(
        'guides/<int:pk>/video/',
        views.GuideView.as_view(template_name="lims/modal/guide-video.html"),
        name='guide-video'
    ),
    path('guides/new/', views.GuideCreate.as_view(), name='new-guide'),
    path('guides/<int:pk>/edit/', views.GuideEdit.as_view(), name='guide-edit'),
    path('guides/<int:pk>/delete/', views.GuideDelete.as_view(), name='guide-delete'),

    path('loader/<slug:beamline>/', views.PuckLoader.as_view(), name='puck-loader'),
    path('loader/<slug:beamline>/<slug:project>/', views.PuckLoader.as_view(), name='project-puck-loader'),
    path('loader/<slug:beamline>/<slug:project>/<int:puck>/', views.SelectPuck.as_view(), name='loader-select-puck'),
    path('loader/<slug:beamline>/pending/', views.CheckPending.as_view(), name='loader-check-pending'),
    path('loader/<slug:beamline>/load/<slug:position>', views.LoadPuck.as_view(), name='loader-load-puck'),
    path('loader/<slug:beamline>/unload/<slug:position>', views.UnloadPuck.as_view(), name='loader-unload-puck'),

    path('settings/edit/', views.EditSettings.as_view(), name='settings-edit'),
]

handler403 = 'lims.views.custom_403_view'
handler404 = 'lims.views.custom_404_view'
handler500 = 'lims.views.custom_500_view'
