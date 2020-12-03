from django.urls import path
from . import views

urlpatterns = [
    path('access/', views.AccessListView.as_view(), name='access-list'),
    path('access/history/', views.RemoteConnectionList.as_view(), name='connection-list'),
    path('access/history/stats/', views.RemoteConnectionStats.as_view(), name='connection-stats'),
    path('access/<str:address>/edit', views.AccessEdit.as_view(), name='access-edit'),
    path('access/connection/<int:pk>/', views.RemoteConnectionDetail.as_view(), name='connection-detail'),
]
