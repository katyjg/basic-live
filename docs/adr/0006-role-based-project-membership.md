# Role-Based Project Membership Model

Decoupling individual users from project accounts requires a governance structure for team permissions. We decided to implement an explicit role-based membership model (`ProjectMembership`) with distinct roles (`PI`, `CO_INVESTIGATOR`, and `MEMBER`), ensuring that scientific and shipping accountability remains with the lead researcher while enabling team members to manage samples, view data, and operate beamline instrumentation.

## Context

When research allocations were decoupled from user accounts, projects required a mechanism to associate multiple researchers, define operational privileges, and support team membership lifecycles without losing historical attribution.

## Decision

1. **Membership Model (`lims.ProjectMembership`)**:
   - Links `User` and `Project` with unique `(user, project)` constraints.
   - Incorporates an `is_active` boolean flag to allow revoking or suspending access without deleting historical records.
2. **Role Hierarchy**:
   - **`PI` (Principal Investigator)**: Primary scientific and administrative lead. Holds ultimate authority over project allocation, sample editing, shipments, and team roster management. Mirrors `Project.pi`.
   - **`CO_INVESTIGATOR` (Co-Investigator)**: Senior research partner authorized to manage samples, submit requests, coordinate shipments, and lead experimental sessions.
   - **`MEMBER` (Team Member)**: General research collaborator authorized to create samples, access collected data, participate in beamtime shifts, and operate workstations.
3. **Authorization Interface**:
   - `User.can_access_project(project)` provides a centralized permission check: returns `True` if the user is a superuser, the project's designated PI, or holds an active `ProjectMembership`.
   - `User.get_projects()` dynamically returns all accessible `Project` records across PI assignments and active memberships.
