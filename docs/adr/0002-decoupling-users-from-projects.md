# Decoupling Individual Users from Project Accounts

The legacy codebase coupled authentication credentials and scientific research proposals into a single custom user model (`Project(AbstractUser)`), preventing individual researchers and facility staff from maintaining personal identities or holding access across multiple proposals. We decided to separate individual human `User` models (`AUTH_USER_MODEL = 'lims.User'`) from the `Project` (scientific proposal / allocation) entity, linking them via `ProjectMembership`.

## Context

Under the legacy schema, `Project` inherited from Django's `AbstractUser`. Every beamline allocation functioned as a single login account with shared credentials, conflating:
1. Human identity and authentication (username, password, personal email, SSH keys).
2. Institutional and proposal metadata (lead institution, safety approvals, financial codes).
3. Experimental allocations, shipments, datasets, and beamtime shifts.

This model prevented team collaboration, eliminated personal auditability for data collection and ELN entries, and made it impossible for a researcher to collaborate on multiple projects without managing distinct credentials for each.

## Decision

1. **User Identity (`lims.User`)**:
   - Implemented `basiclive.core.lims.models.User(AbstractUser)` as the sole `AUTH_USER_MODEL`.
   - Represents individual human researchers, principal investigators, and beamline staff.
   - Holds personal credentials, contact info, personal `SSHKey` records, and an optional `default_project` for cross-session convenience.
2. **Project Allocation (`lims.Project`)**:
   - Converted `basiclive.core.lims.models.Project` to inherit from `TimeStampedModel`.
   - Represents the research proposal, scientific allocation, billing code, and shipping account.
   - Identifies the lead researcher via an explicit `pi` ForeignKey to `User`.
3. **Session & Scoping Architecture**:
   - Introduced `ProjectContextMiddleware` to manage the active project (`request.project`) within user web sessions, persisting selection in `request.session['active_project_id']`.
   - Provided an active project switcher in the navigation bar (`lims/navs.html`) and `SwitchProjectView` with open-redirect protection.
   - Scoped data views and queries via `ListViewMixin` filtering by `request.project`, and verified access via `User.can_access_project()`.
4. **Machine APIs & Access Control**:
   - Machine APIs and JWT bearer tokens authenticate individual `User` identities and resolve project context via `X-Project` headers.
   - Beamline workstation access validates individual user credentials (`SSHKey`) while granting shift access to all active project team members.
5. **Electronic Lab Notebooks (`basiclive.core.notebooks`)**:
   - Attributed `Entry` and `Annotation` records directly to individual `User` accounts (`author = ForeignKey(settings.AUTH_USER_MODEL)`), establishing individual scientific auditability.
   - Decoupled `Notebook` from project and session ownership, removing legacy `owner`, `members`, `access`, and `editor` fields in favor of staff-governed shared notebooks, while dynamically aggregating project notebook metrics through active team membership (ADR-0024).
