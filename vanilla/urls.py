"""mxlive URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/2.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""


from django.conf import settings
from django.conf.urls import include
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth.views import LoginView, LogoutView
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.urls import path

from basiclive.core.lims.conf import settings as lims_settings
from basiclive.core.lims.views import ProxyView

urlpatterns = [
    path('admin/', admin.site.urls, name='admin'),
    path('access/', include('basiclive.core.acl.urls')),
    path('users/',  include('basiclive.core.lims.urls')),
    path('crm/', include('basiclive.core.crm.urls')),
    path('files/<str:section>/<path:path>', ProxyView.as_view(), name='files-proxy'),
    # path('accounts/', include('allauth.urls')),
    path('accounts/login/',  LoginView.as_view(template_name='lims/login.html'), name="login"),
    path('accounts/logout/', LogoutView.as_view(), name="logout"),
    path('api/v2/', include('basiclive.core.api.urls')),
    path('api/v3/', include('basiclive.core.api.urls')),
    path('api/', include('basiclive.core.api.urls')),
    path('reports/', include('reportcraft.urls')),
]

if lims_settings.USE_SCHEDULE:
    urlpatterns += [path('calendar/', include('basiclive.core.schedule.urls'))]

if lims_settings.USE_PUBLICATIONS:
    urlpatterns += [path('publications/', include('basiclive.core.publications.urls'))]

if lims_settings.USE_NOTEBOOKS:
    urlpatterns += [path('notebooks/', include('basiclive.core.notebooks.urls'))]

if settings.DEBUG:
    urlpatterns += staticfiles_urlpatterns()
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

