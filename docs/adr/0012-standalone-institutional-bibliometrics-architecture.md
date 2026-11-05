# Standalone Institutional Bibliometrics Architecture

The `publications` app tracks scientific publications, citations, journal impact metrics, and structural depositions. We decided to model scientific output as an institution-wide standalone bibliometrics catalog organized by subject areas, tags, and funders, rather than strictly coupling each publication or deposition via database foreign keys to individual `Project` or `Beamline` instances.
