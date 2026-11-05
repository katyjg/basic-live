# Delegating Dashboard Views to Instance Applications

BasicLIVE is designed as a reusable core framework rather than a turnkey site deployment (ADR-0001). We decided to remove built-in dashboard views (`StaffDashboard`, `ProjectDetail`), their corresponding templates, and the root URL route (`''`) from `basiclive.core.lims`. Individual facility wrapper applications define their own root routes (`/`) and instance-specific dashboards, while framework deletion and form views decouple from assumption of a `'dashboard'` reverse name by redirecting to contextual resource lists or the root path.
