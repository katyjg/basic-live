from django.template import Library
from basiclive.core.lims.models import Project

register = Library()


@register.simple_tag
def get_container_projects(obj):
    projects = {
        project: obj.children.filter(project=project)
        for project in Project.objects.filter(
            pk__in=obj.children.values_list('project', flat=True)).distinct()
    }
    return projects


@register.filter
def num_containers(project, container):
    return project.containers.filter(parent=container).count()


@register.simple_tag
def container_project(obj):
    return obj.project
