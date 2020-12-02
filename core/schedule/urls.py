from django.urls import path
from . import views, ajax_views


urlpatterns = [
    path('', views.ScheduleView.as_view(), name='schedule'),
    path('view', views.CalendarView.as_view(), name='calendar'),

    path('beamtime/new/', views.BeamtimeCreate.as_view(), name='new-beamtime'),
    path('beamtime/<int:pk>/edit/', views.BeamtimeEdit.as_view(), name='beamtime-edit'),
    path('beamtime/<int:pk>/delete/', views.BeamtimeDelete.as_view(), name='beamtime-delete'),
    path('beamtime/<int:pk>/info/', views.BeamtimeInfo.as_view(), name='beamtime-info'),
    path('beamtime/stats/', views.BeamtimeStats.as_view(), name='beamtime-stats'),

    path('downtime/new/', views.DowntimeCreate.as_view(), name='new-downtime'),
    path('downtime/<int:pk>/edit/', views.DowntimeEdit.as_view(), name='downtime-edit'),
    path('support/new/', views.SupportCreate.as_view(), name='new-support'),
    path('support/<int:pk>/edit/', views.SupportEdit.as_view(), name='support-edit'),
    path('support/<int:pk>/delete/', views.SupportDelete.as_view(), name='support-delete'),
    path('support/<int:pk>/info/', views.SupportDetail.as_view(template_name='schedule/support-info.html'), name='support-info'),
    path('notification/<int:pk>/edit/', views.EmailNotificationEdit.as_view(), name='email-edit'),
    path('notifications/', views.EmailNotificationList.as_view(), name='email-list'),

    path('schedule/week/', views.CalendarView.as_view(template_name="schedule/week.html"), name="this-week"),
    path('schedule/week/<int:year>-W<int:week>/', views.CalendarView.as_view(template_name="schedule/week.html"), name="any-week"),
    path('beamtime/', ajax_views.FetchBeamtime.as_view(), name='beamtime-json'),
    path('downtime/', ajax_views.FetchDowntime.as_view(), name='downtime-json'),

]
