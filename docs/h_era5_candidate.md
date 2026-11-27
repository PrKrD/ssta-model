# ERA5-targeted bilinear H candidate

This follow-up to the [old-mask rebuild comparison](h_rebuild.md) recomputes H
using **ERA5 ocean as the interpolation target domain**. The original source
values and source-ocean rule remain unchanged. It does not mask a previously
interpolated MLD-domain product: source values are interpolated again with the
correct ERA5 target mask.

The deliverable is a validated candidate. No historical SST/diffusion run has
been performed with it; runtime surface files, forcing, damping, diffusivity,
solver, scientific grid and Cesium remain unchanged. Previous baseline and
old-mask comparison products are preserved.

## Method and polar exception

Use local `data/raw/mld_dr003_ref10m_v2023.nc`, de Boyer Montégut (2023),
[DOI](https://doi.org/10.17882/91774). At each original 1° centre, take the maximum
positive finite monthly `mld_dr003` value with **mask == 1**. Declared fill values
and unsupported source cells remain missing; no n_obs threshold is imposed.

The shared periodic mask-aware bilinear kernel interpolates this fixed source H
to the current 0.25° native grid. Positive weights of valid source-ocean corners
are renormalised; entirely unsupported targets remain NaN. Target ocean is the
existing ERA5 **land_fraction < 0.5**, checked against the saved ocean flags.
No nearest-valid search, zero replacement, coastal filling or extra smoothing
is applied.

For target centres **outside ±89.5° only**, retain the exact existing containing-cell
H where the baseline `input_valid` is active and ERA5 classifies ocean. This is
reuse of an existing baseline value, not extrapolation. `support_method=2` marks
the exception; its bilinear weight and contributor count stay zero. The existing
diffusion polar-cap treatment is unchanged. At ±89.5° itself use interpolation.

## Generate and inspect

With the existing processed inputs and `visualization` extra installed:

```sh
python -m pytest
ruff check .
ruff format --check .
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 python experiments/finalise_h_candidate.py
```

The command refuses existing candidate files/diagnostics. Optional `--source`,
`--processed`, `--output` and `--diagnostics` paths support fresh reproductions.
It does not call original preparation, model integration or display export.

Generated, Git-ignored products:

- `data/processed/north_surface_h_era5_bilinear.nc` and
  `south_surface_h_era5_bilinear.nc`: float64 H (m), ERA5 ocean, exact copied
  `baseline_input_valid`, support-method flags, minimum source-month coverage,
  positive-corner weight before renormalisation and unavailable-ocean flags.
- `runs/h_era5_bilinear_candidate/summary.json` and `report.md`: coverage, changes
  on common finite support, maximum local differences/coordinates, coastal and
  polar statistics, active-mask checks and complete provenance/preservation hashes.
- `unsupported_era5_cells.csv` in that diagnostics directory: exact unsupported
  ERA5 ocean coordinates, original H and baseline-active status. Active gaps
  remain unresolved rather than being filled.
- `global_H_comparison.png`, `north_atlantic_H_detail.png`,
  `candidate_minus_baseline_H.png` and `unavailable_H_in_era5_ocean.png` in that
  directory: native maps with shared depth limits, symmetric differences and
  explicit unsupported/polar/newly-supported categories. Tropical H is omitted
  to match the model's extratropical scope.

Existing processed products and the raw source are hashed before and after
generation. New NetCDF values and coordinates pass exact round-trip checks.
Coverage/differences distinguish source interpolation from polar retention.
Adjacent-cell RMS jumps use common native faces; physical RMS gradients divide
by spherical meridional/parallel distances and omit co-located polar zonal faces.

## Domain compatibility is explicit

`baseline_input_valid` is the prepared mask before any observed-initial-condition
restriction. Covering all of it also covers the historical January-ERA5-initialised
subset, provided its initial-condition policy is retained. Positive finite H on
every original active cell is necessary for preserving that domain. Newly finite
depths on inactive cells are reported separately; they are not activation requests.

The current runtime validator expects `input_valid` to equal an automatically
derived finite-H/forcing mask. Thus a candidate with additional finite H is **not
a direct file replacement**: retaining the original mask would fail that strict
check, while recomputing the mask could expand the domain. A future activation
must deliberately preserve the baseline mask (or explicitly restrict candidate
H outside it) and maintain all other validation and initialization rules. This
preparation task changes neither runtime code nor domain selection.

Coverage compatibility does not validate physical accuracy or unchanged dynamics.
Bilinear H changes heat capacities and diffusion conductances; it is not a
conservative heat-capacity remap. Partial coastal support and large local changes
near sharp source gradients remain scientific considerations for a later rerun.
