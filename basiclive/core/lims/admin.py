from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from basiclive.core.lims import models


class ItemAdmin(admin.ModelAdmin):
    list_display = ('identity', 'project')
    search_fields = ('name', 'project__name')


class ProjectAdmin(admin.ModelAdmin):
    list_display = ('name', 'pi', 'kind', 'contact_person', 'contact_email', 'country', 'region')
    search_fields = (
        'name', 'contact_person', 'contact_email', 'pi__username', 'pi__first_name', 'pi__last_name',
        'country__name', 'region__name'
    )
    list_filter = ('kind', 'country')


class ProjectMemberAdmin(admin.ModelAdmin):
    list_display = ('user', 'project__name')
    list_filter = ('project__designation', 'project__kind')
    search_fields = (
        'user__username', 'user__first_name', 'user__last_name', 'project__name',
        'project__contact_person', 'project__contact_email',
    )


class CountryAdmin(admin.ModelAdmin):
    list_display = ('name', 'alpha2', 'alpha3', 'code')
    search_fields = ('name', 'alpha2', 'alpha3')


class RegionAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'country')
    search_fields = ('name', 'code', 'country__name')
    list_filter = ('country',)


class UserAdmin(DjangoUserAdmin):
    list_display = ('username', 'email', 'name', 'phone', 'is_staff', 'is_active')
    search_fields = ('username', 'name', 'first_name', 'last_name', 'email')


class LocationAdmin(admin.ModelAdmin):
    list_filter = ('kind',)


admin.site.register(models.Guide)
admin.site.register(models.Beamline)
admin.site.register(models.Carrier)
admin.site.register(models.Automounter)
admin.site.register(models.ProjectType)
admin.site.register(models.ProjectDesignation)
admin.site.register(models.Project, ProjectAdmin)
admin.site.register(models.ProjectMembership, ProjectMemberAdmin)
admin.site.register(models.ComponentType)
admin.site.register(models.RequestType)
admin.site.register(models.DataType)
admin.site.register(models.ContainerType)
admin.site.register(models.ContainerLocation, LocationAdmin)

admin.site.register(models.User, UserAdmin)
admin.site.register(models.Country, CountryAdmin)
admin.site.register(models.Region, RegionAdmin)

admin.site.register(models.Shipment, ItemAdmin)
admin.site.register(models.Container, ItemAdmin)
admin.site.register(models.Group, ItemAdmin)
admin.site.register(models.Sample, ItemAdmin)
admin.site.register(models.Request, ItemAdmin)
admin.site.register(models.Data, ItemAdmin)
admin.site.register(models.AnalysisReport, ItemAdmin)
admin.site.register(models.Session, ItemAdmin)
