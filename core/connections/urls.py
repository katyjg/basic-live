from django.conf.urls import url
from django.urls import path
from . import views


def keyed_url(regex, view, kwargs=None, name=None):
    regex = (r'(?P<signature>(?P<username>[\w_-]+):.+)/') + regex[1:]
    return url(regex, view, kwargs, name)


urlpatterns = [
    url(r'^accesslist/$', views.AccessList.as_view()),
    path('keys/<slug:username>', views.SSHKeys.as_view(), name='project-sshkeys'),
]
