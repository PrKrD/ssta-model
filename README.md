# Hybrid Statistical-Dynamical Modelling of Global Sea Surface Temperature Anomalies

SSTA Model is a master's research project developing a simplified, physically
interpretable global sea surface temperature (SST) anomaly model with stochastic
atmospheric forcing. The scientific starting point is A. Czaja's October 2026
*Notes on slab mixed layer heat and salt budgets: long timescales*.

**Status:** Python input preparation plus a standalone Cesium viewer with
time-varying synthetic field playback. The supplied scientific inputs can be
organized, losslessly compressed and validated. No model physics, stochastic
forcing or numerical integration is implemented.

## Scientific scope

The intended framework uses geographically varying but temporally fixed
late-winter mixed-layer depth, H(x,y). Begin with surface heat flux forcing and
temperature-dependent surface damping. Introduce and test subsequent processes
incrementally: horizontal advection by mean Ekman and geostrophic circulation,
subduction and obduction between the mixed layer and ocean interior, and
horizontal diffusion. Sea surface salinity is an optional extension, not an
established requirement.

The scientific Python package must run independently of any web interface.
The `globetest` project is an earlier experimental prototype. Its useful globe
rendering and UI patterns have been adapted into the independent frontend; it is
not a runtime dependency. No backend or scientific calculations were migrated.

## Repository layout

| Path | Purpose |
| --- | --- |
| [src/ssta_model/core/](src/ssta_model/core/) | Future orchestration, configuration, grids, state and integration |
| [src/ssta_model/physics/](src/ssta_model/physics/) | Independent physical tendency calculations |
| [src/ssta_model/forcing/](src/ssta_model/forcing/) | Atmospheric forcing and statistically derived spatial patterns |
| [src/ssta_model/data/](src/ssta_model/data/) | Scientific input selection, preparation and validation |
| [src/ssta_model/analysis/](src/ssta_model/analysis/) | Diagnostics, validation and statistical analysis |
| [configs/](configs/) | Tracked experiment configurations |
| [experiments/](experiments/) | Tracked research definitions and thin scripts |
| [tests/](tests/) | Package checks and future controlled scientific tests |
| [docs/](docs/) | Architecture and scientific implementation documentation |
| [frontend/](frontend/) | Standalone Cesium viewer and synthetic field playback |
| [data/](data/) | Ignored local datasets and processing intermediates |
| [runs/](runs/) | Ignored generated results, logs, plots and diagnostics |
| [.github/workflows/](.github/workflows/) | Continuous integration |

See [architecture](docs/architecture.md) for boundaries and future conventions.
Scientific simulation subpackages still contain only descriptive docstrings.

## Development setup

Use Python 3.11 or newer. From the repository root:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m pytest
ruff check .
ruff format --check .
```

Apply formatting with `ruff format .`. CI runs the same installation and checks
on Python 3.11 and 3.12. Hatchling builds the `src/` package; pytest and Ruff are
the only development tools. NumPy, xarray and netCDF4 support the implemented
input-preparation pipeline. Additional scientific dependencies will be added
when required by implemented functionality.

Track experiment definitions and configurations. Write generated outputs under
[runs/](runs/), and local datasets under [data/](data/); both retain tracked
README guidance. Small intentional fixtures may later be tracked under
[tests/](tests/).

## Scientific input preparation

Run `python experiments/prepare_model_inputs.py` to organize the seven supplied
local NetCDF files and generate compact, validated inputs under
`data/processed/`. Originals remain unchanged under
`data/raw/`; both local directories are Git-ignored. See the
[data guide](data/README.md) for exact selections, mask-aware depth mapping,
provisional damping, compression, and generated inventory/coverage reports.
The first-model baseline now uses one provisional area-weighted effective damping
coefficient in [configuration](configs/surface_damping.toml). Runtime spatial
products contain H and its validity information; local damping gaps do not limit
the active domain. No numerical integration is implemented yet.

## Frontend

Use Node.js 22 or newer. From [frontend/](frontend/), run `npm ci`, then
`npm run dev`. Use `npm test` and `npm run build` for checks. The globe displays
arbitrary synthetic anomaly fields in K, not observations or Python model output,
and needs no API, Cesium ion token or external imagery service. See the
[frontend guide](frontend/README.md) for the data contract and migration details.

The next scientific milestone is to specify the first heat-flux-and-damping
model's units, sign conventions, data contracts and controlled validation cases
before implementing it.
