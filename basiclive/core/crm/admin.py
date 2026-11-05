from django.contrib import admin
from basiclive.core.crm import models


class SupportAreaAdmin(admin.ModelAdmin):
    list_display = ('name', 'label', 'user_feedback', 'external', 'scale')
    search_fields = ('name', 'label')
    list_filter = ('user_feedback', 'external')


class SupportRecordAdmin(admin.ModelAdmin):
    readonly_fields = ['previous']


admin.site.register(models.LikertScale)
admin.site.register(models.SupportArea, SupportAreaAdmin)
admin.site.register(models.Feedback)
admin.site.register(models.SupportRecord, SupportRecordAdmin)
