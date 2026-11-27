# Architecture

The scientific core remains independent of the Cesium frontend and optional
local API. Implement only processes required by the research experiment; no
general run manager, database or solver registry is introduced.

The [local damping adapter](interactive_damping.md) is optional. `api.py` handles
three request/status/result endpoints and display-file serving with one active
run. `interactive.py` applies the fixed tracked 24-month template, invokes the
existing runner in a child process and reuses the display aggregation. Active status
lives in memory; completed runs have local timestamp records and unique ignored
directories, with five-completion retention confined to interactive outputs. Scientific core
modules never import FastAPI or the adapter. Only gamma is adjustable.

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
  `mld_rebuild.py` is a separate, explicitly invoked preparation workflow for
  proposed bilinear H and remapped source-mask comparisons. It preserves selected
  runtime products and never integrates SST; see [H rebuild](h_rebuild.md).
  `era5_h_candidate.py` reuses its source/interpolation kernels with the ERA5
  target mask and restricted polar retention; [candidate validation](h_era5_candidate.md)
  stays separate from runtime input/domain selection.
  Runtime H selection now explicitly supports `baseline` and `era5_bilinear`.
  Original inputs/masks are validated first; the selected candidate changes H
  only, with complete active-cell coverage and exact polar-retention checks.
  Observed initialization preserves its original support intersection.
- [analysis](../src/ssta_model/analysis/) owns paired ERA5 metrics, regional series,
  native scientific figures, and the controlled with/without-diffusion comparison.
  Model and ERA5 comparisons use common finite ocean support. Analysis does not
  change simulation parameters or outputs.
- [experiments](../experiments/) provides thin runners/export commands using the
  tracked [configurations](../configs/).

Physics/forcing must not import the orchestrator, and the package must not import
experiments or frontend code. Parameter estimation/preparation is distinct from
applying fixed parameters. H is unchanged de Boyer Montégut (2023) maximum monthly
MLD, using original containing cells or the explicitly selected bilinear variant;
no seasonal depth evolution is introduced.
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

[data/historical_export.py](../src/ssta_model/data/historical_export.py) reads only
saved primary bilinear-H model SST and processed ERA5/H inputs. It never integrates
physics, prepares inputs or opens retired original-H historical outputs. Shared
[comparison aggregation](../src/ssta_model/data/comparison_export.py) supplies the
existing native ocean-area weighting. One unchanged 0.5° grid, two float32 arrays
per monthly file (model, ERA5) and one static bilinear H array form the v4 contract.
The geometry preserves original/bilinear processed-H tile membership for compatibility;
original H is retained as an input, not a selectable display layer.

[frontend](../frontend/) validates those assets and caches at most three monthly
buffers plus static H. Model−ERA5 is subtraction of the two stored operands, with
missing support preserved. Model/ERA5 share fixed SST colour populations; the
difference has its own fixed symmetric population. Static H uses sequential
metre limits and disables playback while preserving the month. Geometry, picking,
timeline and controls are reused. Historical viewing needs no Python runtime.
The optional damping API runs only on explicit submission, polls status and
loads completed static results on that same geometry. Interactive v1 results with
matching geometry remain compatible across the historical v3-to-v4 change;
geometry mismatches are rejected explicitly. No scientific-resolution change occurs.

Archived multi-experiment exporters/analysis remain reproducible but write only
to ignored archive locations, never the active viewer. Their original native
runs must first be reproduced to use them; see [retirement](historical_retirement.md).

## Reproducibility and storage

Track definitions, source, tests and documentation. Scientific inputs live under
ignored `data/`; generated outputs, audits and figures under ignored `runs/`.
Preserve the entire primary bilinear-H historical run. Retired original-H native
outputs have local archived metadata/metrics/figures and tracked configurations;
the active display/export/API do not require them. Specific verified removals,
source hashes and sizes are recorded in local retirement audits. Interactive
retention remains confined to its five most recent completed runs.

Runs retain resolved configuration, original input/preprocessing hashes,
initialization identity, code revision/dirty state/source hashes, software
versions, solver settings/iterations/residuals and monthly statistics. Float64
integration is streamed to checked compressed float32 output. Numerical
conservation/convergence is separate from scientific agreement with ERA5, which
remains retrospective and not independent forecast validation.
