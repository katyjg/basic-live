from django.urls import path
from django_cas_ng import views as casviews


urlpatterns = [
    path('login/', casviews.LoginView.as_view(), name='login'),
    path('logout/', casviews.LogoutView.as_view(), name='logout'),
    path('callback/', casviews.CallbackView.as_view(), name='cas_ng_proxy_callback'),
]

