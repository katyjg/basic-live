# Beamline Control API Boundary and JWT Authentication

Beamline control software requires machine-to-machine integration to resolve sample manifests and report collection events. We decided that BasicLIVE acts strictly as an asynchronous metadata registry and event sink (never directly orchestrating low-level hardware or motion control), and decided to transition machine-to-machine API authentication from custom asymmetric key signing (`VerificationMixin`) to industry-standard JSON Web Tokens (JWT).
