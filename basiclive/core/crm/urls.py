from django.urls import path

from . import views

urlpatterns = [
    path('support/', views.SupportEntryList.as_view(), name='supportrecord-list'),
    path('support/new/', views.SupportEntryCreate.as_view(), name='new-supportrecord'),
    path('support/<int:pk>/edit/', views.SupportEntryEdit.as_view(), name='supportrecord-edit'),
    path('area/', views.SupportAreaList.as_view(), name='supportarea-list'),
    path('area/new/', views.SupportAreaCreate.as_view(), name='new-supportarea'),
    path('area/<int:pk>/edit/', views.SupportAreaEdit.as_view(), name='supportarea-edit'),

    path('feedback/', views.FeedbackList.as_view(), name='user-feedback-list'),
    path('feedback/<int:pk>/', views.FeedbackDetail.as_view(), name='user-feedback-detail'),
    path('feedback/<slug:project>/<int:session>/new/', views.FeedbackCreate.as_view(), name='session-feedback'),
]
