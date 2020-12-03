from django.contrib import admin
from .models import AccessList

runlist_site = admin.AdminSite()


class UserListAdmin(admin.ModelAdmin):
    search_fields = ['name', 'description', 'address']
    list_filer = ['created', 'modified', 'active']
    list_display = ['id', 'name', 'address', 'description', 'active', 'modified']
    ordering = ['-created']


admin.site.register(AccessList, UserListAdmin)
