from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver

from basiclive.core.lims.middleware import get_current_project
from basiclive.core.lims.providers import get_project_provider


@receiver(user_logged_in, dispatch_uid="lims_sync_user_projects_on_login")
def sync_user_projects_on_login(sender, user, request=None, **kwargs):
    if not user or not user.is_authenticated:
        return
    provider = get_project_provider()
    if provider is None:
        return
    provider.sync_user(user)
    if request is not None:
        req_user = getattr(request, "user", None)
        if not req_user or not req_user.is_authenticated:
            request.user = user
        request.project = get_current_project(request)
