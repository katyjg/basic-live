from django.contrib import admin
from basiclive.core.schedule import models


admin.site.register(models.Beamtime)
admin.site.register(models.AccessType)
admin.site.register(models.FacilityMode)
