from django.urls import path

from . import views

urlpatterns = [
    path('entries/', views.PubEntryList.as_view(), name='pub-entry-list'),
    path('pdbs/', views.PDBEntryList.as_view(), name='pdb-entry-list'),
    path('pdbs/<str:code>/', views.PDBDetail.as_view(), name='pdb-entry-detail'),
    path('subjects/', views.SubjectAreasList.as_view(), name='subject-area-list'),
    path('journals/', views.JournalList.as_view(), name='journal-list'),
    path('pdbtext/', views.PDBEntryText.as_view(), name='pdb-entry-text'),
]