from django.urls import path
from . import views

urlpatterns = [
    path('access/', views.AccessListView.as_view(), name='access-list'),
    path('access/history/', views.RemoteConnectionList.as_view(), name='connection-list'),
    path('access/history/stats/', views.RemoteConnectionStats.as_view(), name='connection-stats'),
    path('access/<str:address>/edit', views.AccessEdit.as_view(), name='access-edit'),
    path('access/connection/<int:pk>/', views.RemoteConnectionDetail.as_view(), name='connection-detail'),
    path('users/', views.ProjectList.as_view(), name='user-list'),
    path('users/new/', views.ProjectCreate.as_view(), name='new-project'),
    path('users/<slug:username>/', views.UserStats.as_view(), name='user-detail'),
    path('users/<slug:username>/info/', views.UserDetail.as_view(), name='user-info'),
    path('users/<slug:username>/delete/', views.ProjectDelete.as_view(), name='user-delete')
]
