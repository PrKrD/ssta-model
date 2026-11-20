# Hybrid Statistical-Dynamical Modelling of Global Sea Surface Temperature Anomalies

SSTA Model is a master's research project developing a simplified, physically
interpretable global sea surface temperature (SST) anomaly model with stochastic
atmospheric forcing. The scientific starting point is A. Czaja's October 2026
*Notes on slab mixed layer heat and salt budgets: long timescales*.

**Status:** architectural foundation only. No physics, stochastic forcing, data
processing algorithms, numerical integration or frontend are implemented.

## Scientific scope

The intended framework uses geographically varying but temporally fixed
late-winter mixed-layer depth, H(x,y). Begin with surface heat flux forcing and
temperature-dependent surface damping. Introduce and test subsequent processes
incrementally: horizontal advection by mean Ekman and geostrophic circulation,
subduction and obduction between the mixed layer and ocean interior, and
horizontal diffusion. Sea surface salinity is an optional extension, not an
established requirement.

The scientific Python package must run independently of any web interface.
The existing `globetest` project is an earlier experimental prototype, not a
runtime dependency; no code has been migrated from it.

## Repository layout

| Path | Purpose |
| --- | --- |
| [src/ssta_model/core/](src/ssta_model/core/) | Future orchestration, configuration, grids, state and integration |
| [src/ssta_model/physics/](src/ssta_model/physics/) | Independent physical tendency calculations |
| [src/ssta_model/forcing/](src/ssta_model/forcing/) | Atmospheric forcing and statistically derived spatial patterns |
| [src/ssta_model/data/](src/ssta_model/data/) | Reusable loading, standardisation and preprocessing |
| [src/ssta_model/analysis/](src/ssta_model/analysis/) | Diagnostics, validation and statistical analysis |
| [configs/](configs/) | Tracked experiment configurations |
| [experiments/](experiments/) | Tracked research definitions and thin scripts |
| [tests/](tests/) | Package checks and future controlled scientific tests |
| [docs/](docs/) | Architecture and scientific implementation documentation |
| [frontend/](frontend/) | Future interactive visualisation application |
| [data/](data/) | Ignored local datasets and processing intermediates |
| [runs/](runs/) | Ignored generated results, logs, plots and diagnostics |
| [.github/workflows/](.github/workflows/) | Continuous integration |

See [architecture](docs/architecture.md) for boundaries and future conventions.
Subpackages currently contain only descriptive docstrings.

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
the only development tools. There are currently no runtime dependencies.
NumPy, SciPy, xarray and suitable NetCDF libraries are likely future scientific
dependencies and will be added when required by implemented functionality.

Track experiment definitions and configurations. Write generated outputs under
[runs/](runs/), and local datasets under [data/](data/); both retain tracked
README guidance. Small intentional fixtures may later be tracked under
[tests/](tests/).

The next milestone is to specify the first heat-flux-and-damping model's units,
sign conventions, data contracts and controlled validation cases before
implementing it.
