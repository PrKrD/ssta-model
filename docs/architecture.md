# Architecture

The scientific package is independent of the Cesium frontend. Implement only
processes required by the research experiment; no API, run manager, database or
solver registry is introduced.

## Scientific responsibilities

- [physics](../src/ssta_model/physics/) owns explicit physical calculations.
  `surface_flux.py` supplies heat capacity/tendency; `horizontal_diffusion.py`
  constructs symmetric conservative face exchanges, geometry, active indexing
  and polar-cap reduction from arrays, without file or xarray dependencies.
- [core](../src/ssta_model/core/) resolves TOML, orchestrates month intervals,
  checks budgets and writes output. `integration.py` retains the original
  independent-cell NumPy backward Euler kernel. `diffusion.py` solves the
  combined implicit finite-volume system using SciPy CG and longitude-line
  block preconditioning. Static geometry is reused, with matrices/factors cached
  for each calendar-month duration. No dense global matrix is formed.
- [forcing](../src/ssta_model/forcing/) reconstructs one monthly field from each
  hemisphere's original ordered 12 PCs and raw year-round turbulent maps. It
  never refits parameters, advances state or reads raw observations.
- [data](../src/ssta_model/data/) validates/loads compact scientific inputs.
  `runtime.py` checks coordinates, units, modes and masks, and can load only the
  configured observed initial month. `era5.py` independently prepares monthly
  SST climatology/anomalies; this is outside integration. Original atmospheric,
  damping and MLD preparation remains separate and is not rerun.
- [analysis](../src/ssta_model/analysis/) owns paired ERA5 metrics, regional series,
  native scientific figures, and the controlled with/without-diffusion comparison.
  Model and ERA5 comparisons use common finite ocean support. Analysis does not
  change simulation parameters or outputs.
- [experiments](../experiments/) provides thin runners/export commands using the
  tracked [configurations](../configs/).

Physics/forcing must not import the orchestrator, and the package must not import
experiments or frontend code. Parameter estimation/preparation is distinct from
applying fixed parameters. H is unchanged de Boyer Montégut (2023) maximum monthly
MLD, mapped by containing cells; no seasonal depth evolution is introduced.
See [equations, geometry, conservation and solver tolerances](surface_flux_model.md)
and [ERA5 time/mask/skill conventions](era5_comparison.md).

## State and conservation

The native grid is 0.25 degrees. Active cells require ERA5 ocean, inclusive
extratropical centres, positive finite H, twelve finite coefficients and, for
observed initialization, finite January 1979 ERA5 SSTA. Missing cells stay NaN.
Initial observations are never assimilated later. February is the first forcing
month; exact interval ends/bounds are retained alongside calendar-month labels.
The independent polar cap is reduced with area-depth weights; native H and the
saved grid are retained unchanged. Residuals at the pole describe that cap volume.

The diffusion operator is a symmetric graph Laplacian with harmonic face H and
spherical face-length/centre-distance ratios. Each active shared face has equal
and opposite exchange; there is no flow through land, missing cells or artificial
tropical edges. Longitude wraps. Fully active exact poles become cap unknowns;
ambiguous partial active polar rows are rejected. Mass positivity makes the
combined backward-Euler matrix SPD. CG and independently computed physical
budgets must converge at every step or the run fails. The disabled/zero-kappa
path preserves the original numerical update exactly.

## Static visualization boundary

[data/diffusion_export.py](../src/ssta_model/data/diffusion_export.py) reads saved
with/without-diffusion SST, ERA5 anomalies and processed H. It never integrates
physics or accesses deleted raw atmospheric/MLD files. It writes one 0.5-degree
grid, five SST arrays per monthly file and one separate static H array, with
source identities and aggregation checks. All three SST versions share finite
native support and areas; H independently uses finite processed depths.

[frontend](../frontend/) validates these static assets and retains at most three
monthly buffers plus H, independently of Python. Geometry and picking are reused;
layer/month changes update colours. SST layers share fixed colour limits where
compared, differences have their own symmetric scales, and H uses a sequential
scale in metres. Static H pauses/disables playback and preserves the month for
returning to SST. No runtime NetCDF parser, backend communication or framework
is required. Obsolete demonstrations and their routes have been removed.

## Reproducibility and storage

Track definitions, source, tests and documentation. Scientific inputs live under
ignored `data/`; generated outputs, audits and figures under ignored `runs/`.
Preserve the full no-diffusion baseline and write diffusion to a separate run.
Only specifically verified obsolete demonstration products are removed; a local
retirement audit records their identities and sizes.

Runs retain resolved configuration, original input/preprocessing hashes,
initialization identity, code revision/dirty state/source hashes, software
versions, solver settings/iterations/residuals and monthly statistics. Float64
integration is streamed to checked compressed float32 output. Numerical
conservation/convergence is separate from scientific agreement with ERA5, which
remains retrospective and not independent forecast validation.
