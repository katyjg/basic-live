from django.urls import path
from django.views.decorators.cache import cache_page
from django.views.generic import TemplateView
from . import views, ajax_views, forms

urlpatterns = [
    path('', views.StaffDashboard.as_view(), name='staff-dashboard'),

    path('profile/<slug:username>', views.ProjectProfile.as_view(), name='project-profile'),
    path('profile/<slug:username>/edit', views.ProjectEdit.as_view(), name='edit-profile'),
    path('profile/<slug:username>/labels', views.ProjectLabels.as_view(), name='project-labels'),
    path('profile/<slug:username>/reset', views.ProjectReset.as_view(), name='project-reset'),
    path('profile/<slug:username>/statistics/', views.ProjectStatistics.as_view(), name='project-statistics'),

    path('beamline/<int:pk>/', views.BeamlineDetail.as_view(), name='beamline-detail'),
    path('beamline/usage/', views.UsageSummary.as_view(), name='beamline-usage'),
    path('dewar/<int:pk>/edit/', views.DewarEdit.as_view(), name='dewar-edit'),

    path('shipments/', views.ShipmentList.as_view(), name='shipment-list'),
    path('shipments/new/', views.ShipmentCreate.as_view(), name='shipment-new'),
    path('shipments/<int:pk>/', views.ShipmentDetail.as_view(), name='shipment-detail'),
    path('shipments/<int:pk>/samples/', views.SeatSamples.as_view(), name='seat-samples'),
    path('shipments/<int:pk>/protocol/', views.ShipmentDetail.as_view(template_name="users/entries/shipment-progress.html"), name='shipment-protocol'),
    path('shipments/<int:pk>/data/', views.ShipmentDataList.as_view(), name='shipment-data'),
    path('shipments/<int:pk>/reports/', views.ShipmentReportList.as_view(), name='shipment-reports'),
    path('shipments/<int:pk>/edit/', views.ShipmentEdit.as_view(), name='shipment-edit'),
    path('shipments/<int:pk>/delete/', views.ShipmentDelete.as_view(), name='shipment-delete'),
    path('shipments/<int:pk>/send/', views.SendShipment.as_view(), name='shipment-send'),
    path('shipments/<int:pk>/comments/', views.ShipmentComments.as_view(), name='shipment-comments'),
    path('shipments/<int:pk>/labels/', views.ShipmentLabels.as_view(), name='shipment-labels'),
    path('shipments/<int:pk>/send/update/', views.RecallSendShipment.as_view(), name='shipment-update-send'),
    path('shipments/<int:pk>/receive/', views.ReceiveShipment.as_view(), name='shipment-receive'),
    path('shipments/<int:pk>/return/', views.ReturnShipment.as_view(), name='shipment-return'),
    path('shipments/<int:pk>/return/update/', views.RecallReturnShipment.as_view(), name='shipment-update-return'),
    path('shipments/<int:pk>/archive/', views.ArchiveShipment.as_view(), name='shipment-archive'),
    path('shipments/<int:pk>/add/containers/', views.ShipmentAddContainer.as_view(), name='shipment-add-containers'),
    path('shipments/<int:pk>/add/groups/', views.ShipmentAddGroup.as_view(), name='shipment-add-groups'),

    path('containers/', views.ContainerList.as_view(), name='container-list'),
    path('containers/<int:pk>/', views.ContainerDetail.as_view(), name='container-detail'),
    path('containers/<int:pk>/history/', views.ContainerDetail.as_view(template_name="users/entries/container-history.html"), name='container-history'),
    path('automounter/<int:pk>/history/', views.ContainerDetail.as_view(template_name="users/entries/automounter-history.html"), name='automounter-history'),
    path('containers/<int:pk>/edit/', views.ContainerEdit.as_view(), name='container-edit'),
    path('containers/<int:pk>/samples/', views.ContainerSpreadsheet.as_view(), name='edit-container-samples'),
    path('containers/<int:pk>/delete/', views.ContainerDelete.as_view(), name='container-delete'),
    path('containers/<int:root>/<int:pk>/load/', views.ContainerLoad.as_view(), name='container-load'),
    path('containers/<int:root>/<int:pk>/unload/', ajax_views.UnloadContainer.as_view(), name='container-unload'),
    path('containers/<int:root>/<int:pk>/location/<slug:location>/', views.LocationLoad.as_view(), name='location-load'),
    path('containers/<int:root>/<int:pk>/unload/<slug:username>/', views.EmptyContainers.as_view(), name='empty-containers'),

    path('samples/', views.SampleList.as_view(), name='sample-list'),
    path('samples/stats/', views.SampleStats.as_view(), name='sample-stats'),
    path('samples/<int:pk>/', views.SampleDetail.as_view(), name='sample-detail'),
    path('samples/<int:pk>/edit/', views.SampleEdit.as_view(), name='sample-edit'),
    path('samples/<int:pk>/delete/', views.SampleDelete.as_view(), name='sample-delete'),
    path('samples/<int:pk>/staff/edit/', views.SampleEdit.as_view(form_class=forms.SampleAdminForm), name='sample-admin-edit'),

    path('groups/', views.GroupList.as_view(), name='group-list'),
    path('groups/<int:pk>/', views.GroupDetail.as_view(), name='group-detail'),
    path('groups/<int:pk>/edit/', views.GroupEdit.as_view(), name='group-edit'),
    path('groups/<int:pk>/delete/', views.GroupDelete.as_view(), name='group-delete'),

    path('data/', views.DataList.as_view(), name='data-list'),
    path('data/stats/', views.DataStats.as_view(), name='data-stats'),
    path('data/<int:pk>/', views.DataDetail.as_view(), name='data-detail'),

    path('reports/', views.ReportList.as_view(), name='result-list'),
    path('reports/<int:pk>/', views.ReportDetail.as_view(), name='report-detail'),

    path('activity/', views.ActivityLogList.as_view(), name='activitylog-list'),
    path('activity/<int:pk>/', views.ActivityLogList.as_view(), name='activitylog-detail'),

    path('sessions/', views.SessionList.as_view(), name='session-list'),
    path('sessions/<int:pk>/', views.SessionDetail.as_view(), name='session-detail'),
    path('sessions/<int:pk>/history/', views.SessionDetail.as_view(template_name="users/entries/session-history.html"), name='session-history'),
    path('sessions/<int:pk>/statistics/', views.SessionStatistics.as_view(template_name="users/entries/session-statistics.html"), name='session-statistics'),
    path('sessions/<int:pk>/data/', views.SessionDataList.as_view(), name='session-data'),
    path('sessions/<int:pk>/reports/', views.SessionReportList.as_view(), name='session-reports'),

    path('ajax/create_samples/<int:pk>/', ajax_views.CreateShipmentSamples.as_view(), name='create-samples'),
    path('ajax/update_locations/<int:pk>/', ajax_views.UpdateLocations.as_view(), name='update-locations'),
    path('ajax/update_priority/', cache_page(60*60*24)(ajax_views.UpdatePriority.as_view()), name='update-priority'),
    path('ajax/report/<int:pk>/', ajax_views.FetchReport.as_view(), name='fetch-report'),
    path('ajax/bulk_edit/', ajax_views.BulkSampleEdit.as_view(), name='bulk-edit'),
    path('ajax/layout/<int:pk>/', ajax_views.FetchContainerLayout.as_view(), name='fetch-layout'),

    path('sshkey/<slug:username>/new/', views.SSHKeyCreate.as_view(), name='new-sshkey'),
    path('sshkey/<int:pk>/edit/', views.SSHKeyEdit.as_view(), name='sshkey-edit'),
    path('sshkey/<int:pk>/delete/', views.SSHKeyDelete.as_view(), name='sshkey-delete'),

    path('quick-guide/', TemplateView.as_view(template_name='users/help.html'), name='user-guide'),
    path('guides/<int:pk>/youtube/<slug:video>/', views.GuideView.as_view(template_name="users/components/guide-youtube.html"), name='guide-youtube'),
    path('guides/<int:pk>/flickr/<album>/<photo>/', views.GuideView.as_view(template_name="users/components/guide-flickr.html"), name='guide-flickr'),
    path('guides/<int:pk>/image/', views.GuideView.as_view(template_name="users/components/guide-image.html"), name='guide-image'),
    path('guides/<int:pk>/video/', views.GuideView.as_view(template_name="users/components/guide-video.html"), name='guide-video'),
    path('guides/new/', views.GuideCreate.as_view(), name='new-guide'),
    path('guides/<int:pk>/edit/', views.GuideEdit.as_view(), name='guide-edit'),
    path('guides/<int:pk>/delete/', views.GuideDelete.as_view(), name='guide-delete'),

    path('support/', views.SupportRecordList.as_view(), name='supportrecord-list'),
    path('support/stats/', views.SupportRecordStats.as_view(), name='supportrecord-stats'),
    path('support/new/', views.SupportRecordCreate.as_view(), name='new-supportrecord'),
    path('support/metrics/', views.SupportMetrics.as_view(), name='support-stats'),
    path('support/<int:beamline>/metrics/', views.SupportMetrics.as_view(), name='support-beamline-stats'),
    path('support/<int:pk>/edit/', views.SupportRecordEdit.as_view(), name='supportrecord-edit'),
    path('area/', views.SupportAreaList.as_view(), name='supportarea-list'),
    path('area/new/', views.SupportAreaCreate.as_view(), name='new-supportarea'),
    path('area/<int:pk>/edit/', views.SupportAreaEdit.as_view(), name='supportarea-edit'),

    path('feedback/', views.UserFeedbackList.as_view(), name='user-feedback-list'),
    path('feedback/stats/', views.UserFeedbackStats.as_view(), name='user-feedback-stats'),
    path('feedback/<int:pk>/', views.UserFeedbackDetail.as_view(), name='user-feedback-detail'),
    path('feedback/<str:key>/new/', views.UserFeedbackCreate.as_view(), name='session-feedback'),

]
