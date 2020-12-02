from django.contrib import admin
from mxlive.schedule import models


admin.site.register(models.Beamtime)
admin.site.register(models.AccessType)
admin.site.register(models.FacilityMode)
admin.site.register(models.EmailNotification)
