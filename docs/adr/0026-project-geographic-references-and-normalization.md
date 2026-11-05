# Normalized Project Geographic References and Region Renaming

`basiclive.core.lims.Project` previously stored geographic location attributes—specifically `country` and `province`—as unconstrained free-form strings (`models.CharField(max_length=180)`). This led to several architectural issues:
- Inconsistent and non-standardized country names and abbreviations (e.g. mix of `"US"`, `"USA"`, `"United States"`, `"CA"`, `"Canada"`).
- Inability to query, filter, or aggregate projects reliably for facility bibliometrics, reporting, and customs manifests.
- Lack of data integrity between administrative subdivisions (provinces/states) and countries (e.g., mismatched pairs could be saved without validation).
- DOM performance bottlenecks if trying to render unconstrained subdivision dropdowns without country-level scoping.
- Inconsistent terminology where the subdivision model was named `Region` (conforming to ISO 3166-2), while `Project` named its attribute `province`.

We decided to normalize `Project` geographic location attributes to reference the ISO 3166-1 `Country` and ISO 3166-2 `Region` models, rename `province` to `region` without backward-compatibility aliases, and provide cascading front-end selection:

1. **Foreign Key Schema References & Naming**:
   - Replaced `Project.country` and `Project.province` CharFields with nullable ForeignKeys:
     - `country = models.ForeignKey(Country, on_delete=models.SET_NULL, null=True, blank=True, related_name="projects", verbose_name=_("Country"))`
     - `region = models.ForeignKey(Region, on_delete=models.SET_NULL, null=True, blank=True, related_name="projects", verbose_name=_("State / Province / Region"))`
   - Explicitly renamed `province` to `region` without an alias property, aligning the domain language with `lims.Region`.
   - Added a `region_code` helper property on `Project` to extract clean ISO subdivision abbreviations (e.g., stripping the ISO prefix `CA-ON` -> `ON`, `US-CT` -> `CT`) for shipping documents and postal layouts.

2. **Geographical Consistency & Auto-Population**:
   - Enforced model-level validation and auto-population in `Project.clean()` and `Project.save()`:
     - If `region` is supplied without an explicit `country`, `project.country` is automatically derived as `project.region.country`.
     - If both `region` and `country` are provided, a `ValidationError` is raised if `project.region.country_id != project.country_id`.

3. **Dynamic Cascading Region Lookup**:
   - Implemented `RegionLookup` (`GET /lims/regions/?country=<id_or_code>`) in `basiclive.core.lims.ajax_views`, protected with `LoginRequiredMixin`. It returns serialized subdivisions for the specified country.
   - Updated `ProjectForm` and `NewProjectForm` with dynamic JavaScript: `region` is disabled until a `country` is selected, and changes to `country` dynamically fetch and populate the valid `region` options.

4. **Shipping & Template Rendering**:
   - Refactored postal address and shipping waybill templates (`address.html`, `pdf/address-base.html`, `pdf/shipping-form.html`) to render `project.region_code|default:project.region.name` and `project.country.name`.
   - Updated geocoding address formulation in `basiclive.core.schedule.models.ScheduledEmail` to compose the lookup string from `region.name` and `country.name`.

5. **Two-Step Legacy Data Migration**:
   - Introduced migration `0119_project_country_region_fk`:
     - Renames existing CharFields to temporary columns (`legacy_country`, `legacy_province`).
     - Adds the new `country` and `region` ForeignKey fields.
     - Runs a best-effort resolution function matching legacy text against ISO alpha-2, alpha-3, and full country names, and matching province codes/names against `Region`.
     - Drops the temporary legacy columns.
