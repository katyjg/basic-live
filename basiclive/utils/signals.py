from django.db.models.signals import ModelSignal

expired = ModelSignal(use_caching=True)

