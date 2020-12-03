from django.contrib import admin
from basiclive.core.crm import models


admin.site.register(models.LikertScale)
admin.site.register(models.SupportArea)
admin.site.register(models.Feedback)
admin.site.register(models.SupportRecord)
