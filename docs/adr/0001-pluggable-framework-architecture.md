# Pluggable Core Framework Architecture

BasicLIVE is structured as an installable Python package rather than a standalone turnkey application. We decided to distribute core apps (`lims`, `schedule`, `crm`, `acl`, `publications`) as reusable modules so individual beamlines or light-source facilities can deploy customized Django wrapper projects with site-specific authentication, templates, and storage backends.
