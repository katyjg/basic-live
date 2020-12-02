from django.urls import path

from . import views

urlpatterns = [
    path('entries/', views.PubEntryList.as_view(), name='pub-entry-list'),
    path('pdbs/', views.PDBEntryList.as_view(), name='pdb-entry-list'),
    path('subjects/', views.SubjectAreasList.as_view(), name='subject-area-list'),
    path('journals/', views.JournalList.as_view(), name='journal-list'),
    path('stats/<int:year>/', views.Statistics.as_view(), name='all-yearly-stats'),
    path('stats/<slug:tag>/', views.Statistics.as_view(), name='section-stats'),
    path('stats/<slug:tag>/<int:year>/', views.Statistics.as_view(), name='section-yearly-stats'),
    path('stats/', views.Statistics.as_view(), name='all-stats'),

    path('pdbtext/', views.PDBEntryText.as_view(), name='pdb-entry-text'),
]