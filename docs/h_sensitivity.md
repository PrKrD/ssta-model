# Archived historical H-representation sensitivity

The original-H A/B native outputs have been retired after completed analysis.
Their summaries/figures/configurations are archived; the complete C run is the
primary model and remains intact. Active viewing uses only C/ERA5/H via
`python experiments/export_historical_viewer.py`. See
[retirement and recorded results](historical_retirement.md). The descriptions
below document the historical controlled experiment and its reproduction.

This experiment changes **only the representation of fixed H** relative to the
original-H diffusion run. It does not recalibrate parameters or add physics.

| Experiment | H | Diffusion |
|---|---|---|
| A: `historical_surface_flux_era5_initialised` | Original containing-cell | Off |
| B: `historical_surface_flux_with_diffusion` | Original containing-cell | On |
| C: `historical_surface_flux_bilinear_h` | ERA5-targeted bilinear | On |

The primary comparison is C−B. A remains a separate diffusion reference.
All use the same January 1979 ERA5 SSTA initial field and February 1979–October
2026 forcing (573 integrations). The monthly ERA5 climatology and existing
calendar-label versus interval-end approximation are unchanged.

## Runtime selection and domain preservation

`[mixed_layer_depth] variant="baseline"` is the default, including omitted
sections in older configurations. `variant="era5_bilinear"` selects existing
`north_surface_h_era5_bilinear.nc` and `south_surface_h_era5_bilinear.nc`.
The loader never reads the raw MLD file or regenerates the candidate.

It first loads and **fully validates the original inputs and complete baseline
mask**, using the original finite-H/forcing/ERA5 availability rule. Only then
does it load the candidate H, check coordinates/dimensions/metre units, preparation
identity, baseline/target-mask checksums, copied mask and positive finite H at
every authorised cell. The candidate cannot supply an arbitrary subset mask.
Candidate H replaces only the in-memory depth array; the validated baseline mask
is retained exactly. The existing observed-initialisation intersection then acts
on that same mask with the same January ERA5 field. The 46 newly supported
candidate locations never become active.

Active cells remain **232211 north, 274670 south, 506881 combined**. Candidate
H beyond ±89.5° is required to equal original H at active polar cells, with
matching retention flags. The existing polar-cap geometry/solve is unchanged.
Candidate and original processed files remain untouched; selected candidate
identities/checksums are recorded and rechecked after integration.

## Physics and numerics

Source H is maximum valid monthly de Boyer Montégut (2023) MLD. Source validity
uses mask==1; interpolation targets ERA5 lsm<0.5, with invalid source corners
excluded and weights renormalised. See [candidate preparation](h_era5_candidate.md).
Interpolation adds no observational information beyond the original 1° field.

Both heat capacity AH and harmonic face depths in conservative spherical
diffusion use the selected H. The operator is rebuilt once per hemisphere at
startup, then reused. rho=1025, cp=3990, gamma=16.072239642825945 and kappa=1000
retain the existing configuration values. No intercept, forcing fit or process
changes are introduced. CG, preconditioning, convergence/budget thresholds,
no-flux boundaries and periodic longitude are unchanged. Diffusion-off and
zero-kappa paths retain the independent-cell kernel for either H variant.

## Reproduce from existing processed products

First run pytest/Ruff and a short actual-data integration: copy the tracked C
configuration, set end_month=1979-04 and choose a new output directory. Inspect
convergence, budget residuals, masks, initial state and polar retention before
the full run. Existing output directories are protected against overwrite.

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 python experiments/run_historical_surface_flux.py --config configs/historical_surface_flux_bilinear_h.toml
python experiments/compare_bilinear_h.py --stage analyse
python experiments/compare_bilinear_h.py --stage export
cd frontend
npm test
npm run build
npm run dev
```

These analysis/export commands read saved outputs; they do not run integration
or alter A/B. They require all three saved runs, so first reproduce the retired
A/B configurations if repeating the archived comparison. For a fresh reproduction, scientific outputs and diagnostics live under
`runs/historical_surface_flux_bilinear_h/`. Native comparison figures, monthly
metrics, regional series, `h_sensitivity_summary.json` and the execution report
are in its `comparison/` directory.

## Assessment and figures

The comparison requires identical masks, initial values, cell areas, month/state
boundaries, physics parameters, forcing inputs and observed initial source.
Only selected H, experiment name and output paths differ between B and C.
Monthly statistics use the same finite native ocean cells: unweighted spatial
Pearson correlation/population SD and area-weighted bias/RMSE. Summary changes
include absolute differences and percentages relative to |B| (signed bias change
uses that same denominator). The initial month is excluded from skill.

Global and North Atlantic panels pair original/bilinear H with B/C SSTA and
their correctly signed differences. Directly comparable depth/SSTA fields share
limits. A final October 2026 C−B map shows the accumulated trajectory difference,
not a time integral. Temporal SD maps share limits with ERA5. Hemispheric and
regional series include additional rectangular diagnostic boxes: Labrador Sea
50–65°N, 65–45°W; subpolar North Atlantic 45–65°N, 65–10°W. These are explicit
diagnostic selections, not added model parameters or exact basin boundaries.

Persistence is the lag-one correlation of raw monthly area-mean series, with
temporal SD and ERA5 correlations. It includes trend/seasonal/initial-transient
contributions; no significance, decorrelation-timescale or independent predictive
skill claim follows from it. Numerical conservation/convergence does not imply
greater physical accuracy, and smoother H need not improve SST agreement.

The first controlled run found almost unchanged hemispheric ERA5 agreement:
spatial correlations fell slightly, northern RMSE improved very slightly and
southern RMSE worsened very slightly. The North Atlantic showed local warm/cool
redistribution around H gradients; Labrador/subpolar mean-series variability
increased slightly while their ERA5 temporal correlations decreased slightly.
These are small sensitivity responses, not evidence of improved physical skill.
Exact absolute/relative metrics, extrema, source hashes and execution checks are
in the generated comparison summary/report, outside version control.

## Archived browser comparison

The former v3 viewer contained six monthly arrays and two H layers. Its generated
assets are retired after validating every current-model/ERA5 value against the
compact v4 export. Only the four current selections and interactive damping are
active; see [viewer contract](../frontend/README.md). The original A/B/C scientific
analysis and its figures remain in the archive/current C comparison directory.
Archived `compare_bilinear_h.py --stage export` writes under
`runs/archived_historical_sensitivity/`, after reproducing A/B; it never supplies
the active viewer. The original full scientific source/configurations are retained.
