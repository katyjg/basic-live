# Facility Hardware Custody via System Project Accounts

Physical vessels include both transient user-shipped containers and permanent beamline infrastructure (such as robot automounter carousels, calibration pucks, and alignment trays), while `Container` enforces a non-nullable foreign key to `Project`. We decided to model facility- and beamline-owned hardware using dedicated system-level `Project` accounts, avoiding schema divergence or nullable foreign keys and preserving uniform recursive queries and port-addressing algorithms across all containers.
