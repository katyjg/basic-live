from django.contrib import admin

from .models import AccessList


class AccessListAdmin(admin.ModelAdmin):
    search_fields = ['name', 'description', 'address']
    list_filter = ['created', 'modified', 'active']
    list_display = ['id', 'name', 'address', 'network_display', 'description', 'active', 'modified']
    ordering = ['-created']
    help_texts = {
        'address': 'Enter an individual IP address (e.g. 192.168.1.50) or CIDR subnet (e.g. 192.168.1.0/24).'
    }

    @admin.display(description='Network / CIDR')
    def network_display(self, obj):
        return str(obj.network)


admin.site.register(AccessList, AccessListAdmin)
