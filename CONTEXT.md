# BasicLIVE Domain Context

A framework for creating Beamline Laboratory Information Virtual Environments (LIMS) for light-source facilities.

## Language

### Identity & Organization

**Project**:
An allocated research proposal, scientific program, or billing and shipping account at the facility.
_Avoid_: Account, Client, Customer, Proposal.

**User**:
An individual human researcher, principal investigator, or facility staff member who interacts with the system.
_Avoid_: Project, Account.

**ProjectMembership**:
The formal association of a User with a Project defining their role and operational permissions.
_Avoid_: Assignment, Team Role, Project User.

**Principal Investigator**:
The researcher holding primary scientific and financial accountability for a Project and its shipments.
_Avoid_: Project Lead, Project Owner, Primary Investigator.

**Active Project**:
The currently selected Project context under which a User's session, view queries, and operational actions are performed.
_Avoid_: Current Project, Selected Project, Active Context.

**Facility Account**:
A system-level Project representing the facility or a specific beamline used to own permanent hardware vessels and calibration containers.
_Avoid_: System User, Hardware Project, Admin Project.

**Proposal Portal Sync**:
The integration mechanism that synchronizes approved research proposals and team rosters from a central facility user office portal into BasicLIVE.
_Avoid_: User Importer, Portal Bridge, Sync Service.

**ProjectProvider**:
The pluggable integration provider responsible for synchronizing external Project allocations, temporal validity dates, and staged team rosters into BasicLIVE without eagerly provisioning User accounts prior to first login.
_Avoid_: User Importer, Account Sync, Portal Adapter.

**SSHKey**:
A public cryptographic key registered by a User, used by beamline workstations to authenticate operational connections.
_Avoid_: Private Key, Host Key.

**Country**:
A standardized ISO 3166-1 sovereign state or territory used to record institution and project geographic location.
_Avoid_: Nation, State, Territory.

**Region**:
A standardized ISO 3166-2 primary administrative subdivision of a Country (such as a province or state) associated with a Project.
_Avoid_: Province, State, District, County.

### Facility & Hardware

**Beamline**:
A physical synchrotron radiation experimental station equipped with endstation instrumentation where experiments are performed, or a virtual station configured for software testing and simulation (`simulated`). Operational lifecycle (`active`) distinguishes beamlines in active service from decommissioned or retired stations.
_Avoid_: Station, Instrument, Endstation, Hutch.

**Automounter**:
The robotic sample-changing apparatus mounted on a beamline that automatically transfers samples into the beam.
_Avoid_: Robot, Sample Changer, Carousel.

### Sample Tracking & Containment

**Shipment**:
A tracked physical consignment dispatched by a Project containing containers and samples sent to or returned from the facility.
_Avoid_: Delivery, Package, Consignment.

**Container**:
Any physical vessel with indexed locations that holds samples or sub-containers (such as shipping dewars, pucks, cassettes, or plates). Specialized beamline UI workflows may refer colloquially to pucks or plates while manipulating generic container records.
_Avoid_: Dewar, Puck, Tray, Cane.

**Sample**:
A discrete experimental specimen mounted at an indexed location within a container for beam exposure.
_Avoid_: Specimen, Crystal, Pin.

**Port**:
The composite coordinate identifier derived from the container hierarchy indicating where a sample is physically positioned for robotic mounting.
_Avoid_: Slot, Position, Coordinate, Address.

**LoadHistory**:
A chronological audit record tracking the time interval during which a child container was mounted within a parent container or automounter position.
_Avoid_: Mount Log, Transfer History, Deck History.

**Group**:
A prioritized logical batch of samples within a shipment intended to be handled or measured together.
_Avoid_: Batch, Sub-shipment, Collection.

### Scheduling & Execution

**Beamtime**:
A scheduled calendar time allocation granted to a Project on a specific Beamline.
_Avoid_: Booking, Slot, Reservation.

**Session**:
A discrete period of experimental execution conducted on a Beamline by a Project. On physical production beamlines, sessions require scheduled Beamtime; on virtual simulation stations (`simulated`), ad-hoc sandbox sessions may be launched without allocated shifts.
_Avoid_: Run, Experiment, Shift.

**Simulated Session Cleanup**:
The housekeeping operation (`clean_simulated_sessions`) that permanently purges testing sessions, stretches, datasets, dependent analysis reports, feedback, and activity logs on simulated beamlines exceeding the configured retention lifetime (`SIMULATED_SESSION_LIFETIME_DAYS`).
_Avoid_: Session Pruner, Database Purge, Table Wipe.

**Stretch**:
A continuous, uninterrupted interval of active beamline usage within a Session used to calculate active machine duration and shift consumption.
_Avoid_: Segment, Active Period, Uptime.

**Downtime**:
A recorded period during which the facility beam delivery or beamline instrumentation was unavailable for scientific operations.
_Avoid_: Outage, Maintenance Window, Shutdown.

**FacilityModeType**:
A canonical classification of facility accelerator operating state (such as normal user delivery, development, maintenance, shutdown, or special beam) defining its label and presentation color.
_Avoid_: Mode Kind, Beam Mode, Machine State.

**FacilityMode**:
A scheduled time interval during which the facility operates in a specific FacilityModeType.
_Avoid_: Mode Shift, Operating Window, Ring Status.

**BeamlineSupport**:
A daily schedule assignment designating the facility staff member serving as the primary point of contact for beamline user operations.
_Avoid_: Duty Officer, On-Call Staff.

**ScheduleProvider**:
The pluggable integration provider responsible for synchronizing FacilityMode intervals, Beamtime allocations, Downtime windows, and BeamlineSupport assignments from an external facility scheduling system.
_Avoid_: Calendar Importer, Mode Fetcher, Schedule Bridge.

**SupportRecord**:
An observational log entry recorded by beamline staff documenting technical assistance, problems encountered, and estimated lost operational hours.
_Avoid_: Help Ticket, Incident Log, Trouble Report.

**Remote Operator**:
An authorized User belonging to a Project who remotely operates beamline workstations and instrumentation during an active Beamtime shift.
_Avoid_: Driver, Remote User, Pilot.

### Experiments & Data

**Request**:
A parameterized instruction or experimental protocol attached to Samples or Groups for execution on the beamline.
_Avoid_: Job, Task, Protocol, Work Order.

**RequestType**:
A reusable specification defining the parameters, validation schema, and form layout for a Request.
_Avoid_: Protocol Type, Job Type.

**DataType**:
A category of experimental data defining expected metadata attributes and visualization templates.
_Avoid_: Experiment Type, Kind, Data Category.

**Data**:
A recorded experimental dataset collected on a beamline, comprising raw frame or scan files and associated collection metadata.
_Avoid_: Dataset, Run Output, Raw Files.

**AnalysisReport**:
The automated or manual processing results, scores, and summary reports derived from one or more Datasets.
_Avoid_: Result, Pipeline Output, Analysis.

**Download Proxy**:
An external service that authenticates and streams raw data files using temporary tokens issued by BasicLIVE.
_Avoid_: Storage Gateway, File Server, Data Broker.

### Scientific Output & Impact

**Publication**:
A formal scientific publication (such as a journal article, thesis, book, or patent) cataloged for institutional bibliometrics and impact reporting.
_Avoid_: Paper, Article, Manuscript.

**Deposition**:
A public structural or biological database entry (such as PDB, EMDB, or CSD) with an assigned accession code, resolution, and DOI resulting from facility research.
_Avoid_: Structure Entry, Protein Deposit, Database Record.

### Electronic Lab Notebooks (ELN)

**Notebook**:
A digital laboratory notebook organizing date-stamped experimental records, observations, and data attachments.
_Avoid_: Logbook, Diary, Journal.

**Entry**:
An individual content record attached directly to a Notebook, classified by an EntryType (such as text, data, file, sketch, image, or video). Chronological date grouping and partitioning are handled dynamically at the presentation and query layers. Entries recorded on previous calendar days or with existing annotations are immutable.
_Avoid_: Note, Post, Record Item, Log Item, Page.

**EntryType**:
A specification defining the content format, metadata structure, and rendering template of an Entry.
_Avoid_: Note Type, Kind, Block Type.

**Annotation**:
A reviewer comment attached to a specific Entry, with an optional text selection quote (`quote`) anchored within the entry content. Attaching an annotation permanently locks the entry against author editing.
_Avoid_: Feedback, Note on Note, Markup, Highlight.

### User Interface & Theming

**IconBackend**:
The pluggable provider responsible for resolving canonical icon names and size tokens into font- or format-specific presentation classes.
_Avoid_: Font Provider, Icon Strategy, Theme Service.

**Canonical Icon Name**:
A provider-neutral semantic identifier representing a conceptual icon independent of vendor prefixing.
_Avoid_: Icon Class, Glyph Code, Font Symbol.

**Icon Size Token**:
A standardized categorical sizing literal (`xs`, `sm`, `md`, `lg`, `xl`) translated into consistent viewport metrics across icon backends.
_Avoid_: Font Scale, Icon Dimensions, Font Size.

