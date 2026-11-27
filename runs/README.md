# Generated scientific outputs

`interactive_damping/<run_id>/` stores each explicitly requested local damping
experiment separately: request TOML, log, scientific `model/` and static
`display/` assets. Status exists only in the running API process. Directories
are not overwritten or automatically deleted. See [interactive damping](../docs/interactive_damping.md).

All contents except this README are ignored by Git. Use a separate directory per
experiment; the runner refuses existing output directories. No run manager exists.

- `historical_surface_flux_era5_initialised/`: preserved February 1979–October
  2026 no-diffusion baseline, initialized from January ERA5 SSTA.
- `historical_surface_flux_with_diffusion/`: separate experiment with conservative
  kappa=1000 m2 s-1 diffusion and otherwise identical inputs/masks/initialization.
- `historical_surface_flux_diffusion_check/`: short actual-data solve verification.
- `historical_surface_flux_bilinear_h/`: separate controlled H-only sensitivity,
  with the same observed initial state and 506881 active cells as the original-H
  diffusion run. `comparison/` contains C/B/A/ERA5 metrics, H-effect CSVs,
  lag-one regional persistence, native global/North Atlantic maps and shared-scale
  variability/series figures. `historical_surface_flux_bilinear_h_check/` is its
  short actual-data verification. See [H sensitivity](../docs/h_sensitivity.md).
- `h_rebuild_comparison/`: preparation-only H/mask statistics, four static
  comparison figures and preservation/provenance report. No historical rerun;
  proposed processed H remains separate. See [H comparison](../docs/h_rebuild.md).
- `h_era5_bilinear_candidate/`: ERA5-targeted H candidate report, coverage and
  gradient statistics, unsupported-cell CSV and four native comparison maps.
  No SST integration; see [candidate domain checks](../docs/h_era5_candidate.md).

Each historical run stores separate north/south compressed NetCDF with
`sst_anomaly(time,latitude,longitude)` (K), original coordinates, fixed H, native
areas, active mask, exact state times/bounds, and forcing-month labels. Initial
January is stored separately as `initial_sst_anomaly`, assigned at 1 February.
Later observations do not enter dynamics. Invalid cells stay NaN. Float64 state
is retained during integration; saved float32 SST is checked before proceeding.

Configuration, source hashes, preprocessing provenance, code revision/dirty flag,
library versions and numerical method are recorded. Monthly CSV/JSON diagnostics
include extrema, quantiles, means, spatial SD, budget residual, CG iterations and
relative residual. A failed solve aborts and marks a partial run failed; only
`status=complete` denotes completion. Polar residuals refer to the independent
cap volume, whose values are expanded onto the original native grid.

`comparison/` contains ERA5 monthly/regional statistics, temporal variability,
controlled diffusion effects, summary JSON, native H/SST comparison figures and
regional/hemispheric time series. Directly comparable maps share colour limits.
The display export report records source identities, aggregate checks and asset
sizes. Static H comes directly from existing processed fields; it is not animated.

The default display uses generated 0.5-degree files under
`frontend/public/data/era5_comparison/`, separate from the 0.25-degree science.
The retired demonstration directories and matching display JSON were positively
identified and deleted; `runs/retired_demo_assets.json` records checks and sizes.
No full historical run or processed input was deleted.

See [commands](../experiments/README.md), [finite volumes and H provenance](../docs/surface_flux_model.md),
[comparison definitions](../docs/era5_comparison.md) and [viewer](../frontend/README.md).
This is retrospective comparison, not independent prediction validation.
