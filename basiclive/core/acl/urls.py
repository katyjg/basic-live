from django.urls import path

from . import views

urlpatterns = [
    path('', views.AccessListView.as_view(), name='access-list'),
    path('history/', views.AccessConnectionList.as_view(), name='access-connections'),
    path('history/stats/', views.AccessConnectionStats.as_view(), name='connection-stats'),
    path('<int:pk>/edit', views.AccessEdit.as_view(), name='access-edit'),
    path('connection/<int:pk>/', views.AccessConnectionDetail.as_view(), name='access-connection-detail'),
    path('keys/<slug:username>/', views.AccessKeys.as_view(), name='project-sshkeys'),
]
