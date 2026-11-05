# Technique Extensibility via Data and Request Type Schemas

Synchrotron facilities host diverse beamline techniques (macromolecular crystallography, spectroscopy, imaging, scattering) that evolve rapidly and require distinct data collection parameters. We decided to keep core Django models technique-agnostic and handle technique-specific form parameters and metadata schemas dynamically through JSON specifications in `DataType` and `RequestType` rather than class inheritance or hardcoded model migrations.
