# Workstation Remote Access Provisioning via LIMS-Brokered SSH Key Endpoints

Remote beamline workstations require up-to-date user authorization and credential provisioning that matches dynamic shift schedules. We decided that BasicLIVE acts as an authoritative SSH key server and access broker through dedicated ACL endpoints (`/acl/accesslist/` and `/acl/keys/<username>`), allowing Linux workstations to query currently authorized remote users and fetch their public keys over HTTP rather than managing distributed OS-level PAM or static key deployments across experimental endstations.
