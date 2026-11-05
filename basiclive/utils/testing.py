from typing import List, Optional, Tuple
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import RefreshToken

from basiclive.core.lims.models import Project, ProjectMembership

User = get_user_model()


def create_user(
    username: str,
    email: Optional[str] = None,
    password: str = "password123",
    name: str = "",
    is_staff: bool = False,
    is_superuser: bool = False,
    **kwargs
):
    """
    Create and return a User instance.
    """
    email = email or f"{username}@example.org"
    name = name or username.replace("_", " ").title()
    if is_superuser:
        return User.objects.create_superuser(
            username=username,
            email=email,
            password=password,
            name=name,
            **kwargs
        )
    user = User.objects.create_user(
        username=username,
        email=email,
        password=password,
        name=name,
        is_staff=is_staff,
        **kwargs
    )
    return user


def create_project(
    name: str,
    pi=None,
    **kwargs
) -> Project:
    """
    Create and return a Project instance.
    """
    return Project.objects.create(name=name, pi=pi, **kwargs)


def create_project_membership(
    user,
    project: Project,
    role: str = ProjectMembership.Role.MEMBER
) -> ProjectMembership:
    """
    Create and return a ProjectMembership linking user to project.
    """
    membership, _ = ProjectMembership.objects.get_or_create(
        user=user,
        project=project,
        defaults={"role": role}
    )
    if membership.role != role:
        membership.role = role
        membership.save(update_fields=["role"])
    return membership


def create_project_with_team(
    name: str,
    pi=None,
    co_invs: Optional[List] = None,
    members: Optional[List] = None,
    **kwargs
) -> Tuple[Project, dict]:
    """
    Create a project along with PI, co-investigators, and members.
    Returns (project, team_dict).
    """
    if pi is None:
        pi = create_user(username=f"{name}_pi")

    project = create_project(name=name, pi=pi, **kwargs)

    team = {
        "pi": pi,
        "co_invs": [],
        "members": [],
    }

    if co_invs:
        for u in co_invs:
            create_project_membership(u, project, role=ProjectMembership.Role.CO_INVESTIGATOR)
            team["co_invs"].append(u)

    if members:
        for u in members:
            create_project_membership(u, project, role=ProjectMembership.Role.MEMBER)
            team["members"].append(u)

    return project, team


def generate_jwt_token(user) -> str:
    """
    Generate a SimpleJWT access token string for the given user.
    """
    refresh = RefreshToken.for_user(user)
    return str(refresh.access_token)
