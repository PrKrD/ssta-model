# Generated scientific outputs

`interactive_damping/<run_id>/` stores each explicitly requested local damping
experiment separately: request TOML, log, scientific `model/` and static
`display/` assets. Completed runs persist a UTC completion timestamp in
`state.json`. After each
successful run the API retains the five newest completions and deletes older
interactive directories, protecting queued/active work and responses in transit.
Failed jobs retain request/log/error state but remove partial model/display
products. Legacy completions use verified display-manifest mtime; unrecognised
folders require manual review. The primary historical run listed below is
protected. Superseded A/B outputs
were separately retired by explicit instruction, outside interactive retention.
Directories are never overwritten. See [interactive damping](../docs/interactive_damping.md).

All contents except this README are ignored by Git. Use a separate directory per
experiment; the runner refuses existing output directories. No run manager exists.

- `historical_surface_flux_bilinear_h/`: **preserved primary historical model**,
  February 1979–October 2026 after January observed initialisation. Bilinear H,
  conservative diffusion and 506881 original active cells. The entire run,
  provenance, diagnostics and scientific comparison figures remain intact.
- `archived_historical_sensitivity/`: copied metadata, original summaries,
  model–ERA5 metrics/CSV series and unique figures from the retired original-H
  no-diffusion and diffusion runs. Their old full directories/native NetCDF and
  regenerable temporal-variability NetCDF are removed. Short diffusion/bilinear-H
  checks retain metadata/validation records here; their native outputs and the
  duplicate H reproducibility products are removed. No unique input was deleted.
  See [recorded scientific conclusions and storage](../docs/historical_retirement.md).
- `h_rebuild_comparison/`: preparation-only H/mask statistics, four static
  comparison figures and preservation/provenance report. No historical rerun;
  proposed processed H remains separate. See [H comparison](../docs/h_rebuild.md).
- `h_era5_bilinear_candidate/`: ERA5-targeted H candidate report, coverage and
  gradient statistics, unsupported-cell CSV and four native comparison maps.
  No SST integration; see [candidate domain checks](../docs/h_era5_candidate.md).

A complete historical run stores separate north/south compressed NetCDF with
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

Inspect local storage with `du -sk data runs frontend .venv .git` and
`du -k -d 2 runs frontend | sort -nr | head -40`. Include ignored products in
audits; age or ignored status alone does not justify deletion. See the
[cleanup report](../docs/repository_cleanup.md) for measured removals and caveats.

The active `frontend/public/data/era5_comparison/` uses the compact v4 export:
two monthly arrays (primary model, ERA5), browser-derived difference and static
bilinear H. Recreate it with `python experiments/export_historical_viewer.py`
when the destination is absent, or choose a fresh `--destination` before a
validated replacement. Neither retired original-H run is required. The earlier
[cleanup audit](../docs/repository_cleanup.md) describes the preservation policy
at that stage; [historical retirement](../docs/historical_retirement.md) records
this subsequent, explicitly authorised removal and supersedes its A/B retention.
