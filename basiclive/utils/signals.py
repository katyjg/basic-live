from django.db.models.signals import ModelSignal

expired = ModelSignal(providing_args=["instance"], use_caching=True)

