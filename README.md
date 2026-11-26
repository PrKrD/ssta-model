# SST anomaly model

A research model of a fixed, geographically varying mixed layer, driven by
historical atmospheric variability. The current experiment adds conservative
horizontal diffusion to the surface-forcing/damping baseline and compares both
with ERA5 monthly SST anomalies. This is retrospective comparison, not independent
forecast validation. There is no advection, subduction, salinity, seasonal H or
stochastic forcing.

Science remains at native 0.25-degree resolution. The standalone 0.5-degree Cesium
viewer selects SST with diffusion, without diffusion, ERA5, their differences,
and static mixed-layer depth. It has no Python server or API. Obsolete synthetic
and 24-month demonstrations have been retired.

## Development and execution

Use Python 3.11+ and Node.js 22+:

```sh
python -m pip install -e ".[dev,visualization]"
python -m pytest
ruff check .
ruff format --check .
```

SciPy supplies the sparse SPD solve. Geometry and per-month-duration factors are
reused; no dense matrices or parallel computing framework are introduced.
Existing processed scientific inputs are required; do not restore deleted raw
atmospheric/MLD data or rerun the original preparation pipeline.

After operator tests and a short actual-data check:

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 python experiments/run_historical_surface_flux.py
python experiments/compare_diffusion.py --stage analyse
python experiments/compare_diffusion.py --stage export
cd frontend
npm ci
npm run dev
```

The runner defaults to [diffusion configuration](configs/historical_surface_flux_with_diffusion.toml)
and refuses existing output directories. Preserve the full
[baseline configuration](configs/historical_surface_flux_era5_initialised.toml)
and its generated run. Scientific output, figures and static assets are ignored
by Git. Export before `npm run build`; frontend checks use `npm test`.

## Scientific conventions

The equation uses `(1/H) div(kappa H grad(Theta))`, with harmonic face depths,
spherical geometry, no-flux inactive/domain boundaries, periodic longitude and
a conservative polar cap. Initial kappa is 1000 m2 s-1 without tuning. Constant
surface damping and historical forcing are unchanged. January 1979 ERA5 SSTA
initializes the model; February 1979–October 2026 provides 573 integrations.
Later observations do not enter dynamics. H is the unchanged maximum monthly
**de Boyer Montégut (2023)** climatology, density threshold 0.03 kg m-3 from 10 m,
[DOI](https://doi.org/10.17882/91774), transferred from 1-degree source cells by
containing-cell mapping. It is fixed throughout each simulation.

See [physics, discretisation and solver verification](docs/surface_flux_model.md),
[ERA5 climatology/time/comparison definitions](docs/era5_comparison.md),
[architecture](docs/architecture.md), [experiment commands](experiments/README.md),
[input provenance](data/README.md), [output conventions](runs/README.md) and
[viewer usage](frontend/README.md). Numerical heat conservation does not imply
that the simplified physical model reproduces observed ocean variability.
