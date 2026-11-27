# SST anomaly model

A fixed, geographically varying mixed-layer SST anomaly model driven by
historical 12-mode atmospheric forcing and raw turbulent heat-flux regressions.
The primary historical simulation uses ERA5-targeted bilinear H, conservative
horizontal diffusion (kappa=1000 m²/s), damping gamma=16.072239642825945 W/m²/K,
and January 1979 ERA5 SSTA initialisation. This is retrospective comparison,
not independent forecast validation. No advection, subduction, seasonal H or
stochastic forcing is added.

Science remains at native 0.25° resolution. The 0.5° Cesium application displays
**Model SSTA**, **ERA5 SSTA**, **Difference — Model − ERA5**, and fixed
**Mixed-layer depth H**, with monthly playback and physical-value tooltips.
An optional local API adds 24-month [interactive damping](docs/interactive_damping.md)
experiments using one gamma control and five-completed-run retention.

## Start locally

Use Python 3.11+ and Node.js 22+, with existing ignored scientific/display inputs:

```sh
python -m pip install -e ".[dev,api,visualization]"
python -m uvicorn ssta_model.api:app --reload
```

In another terminal:

```sh
cd frontend
npm ci
npm run dev
```

Historical viewing works without the API. To generate missing display assets
from the preserved `runs/historical_surface_flux_bilinear_h/` and processed ERA5/H:

```sh
python experiments/export_historical_viewer.py
```

The exporter does not integrate the model and refuses an existing destination;
see [replacement procedure and display contract](frontend/README.md).

## Science and reproducibility

The [primary configuration](configs/historical_surface_flux_bilinear_h.toml) is
also the historical runner's default. The existing complete primary run is
preserved; do not overwrite or rerun it merely to view results. Original-H
no-diffusion/diffusion experiments are retired from local native storage and the
viewer, with [summaries, figures and reproduction guidance](docs/historical_retirement.md)
preserved. Their tracked configurations and numerical implementations remain.

The backward-Euler finite-volume solver uses harmonic face depths, spherical
geometry, periodic longitude, no-flux inactive boundaries and the existing
conservative polar cap. H remains geographically varying and temporally fixed:
maximum valid monthly de Boyer Montégut (2023) climatology
([DOI](https://doi.org/10.17882/91774)), density threshold 0.03 kg/m³ from 10 m.
Bilinear mapping preserves the authorised ERA5 active domain and limited polar
containing-cell values; it does not add observational resolution. rho=1025 kg/m³
and cp=3990 J/kg/K remain fixed. February 1979–October 2026 gives 573 integrated
states after January initialisation. Later observations do not enter dynamics.

Validate with `python -m pytest`, `ruff check .`, `ruff format --check .`, then
`npm test` and `npm run build` from `frontend/`. Generated science and display
assets stay Git-ignored. See [architecture](docs/architecture.md),
[scientific equations](docs/surface_flux_model.md), [ERA5 conventions](docs/era5_comparison.md),
[H reconstruction](docs/h_era5_candidate.md), [experiment commands](experiments/README.md),
[input provenance](data/README.md) and [output/retention guidance](runs/README.md).
