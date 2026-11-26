# Historical research experiments

Reusable science lives in `ssta_model`; entry scripts remain thin. Track
configurations, write generated outputs to `runs/`, and preserve the full
no-diffusion baseline under `runs/historical_surface_flux_era5_initialised/`.
The synthetic and completed 1979–1980 demonstrations have been retired.

## Diffusion experiment

Install dependencies and verify the operator before running:

```sh
python -m pip install -e ".[dev,visualization]"
python -m pytest
ruff check .
ruff format --check .
```

The full [configuration](../configs/historical_surface_flux_with_diffusion.toml)
uses January 1979 ERA5 initialization, February 1979–October 2026 forcing,
kappa=1000 m2 s-1, unchanged damping, fixed H, and explicit solver tolerances.
For a short actual-data check, copy it, set end_month to 1979-04 and choose a
separate output directory; never overwrite the baseline or full diffusion run.
The resolved short-check configuration and numerical diagnostics are kept in
`runs/historical_surface_flux_diffusion_check/`.

After the controlled tests and short check pass, run the full experiment:

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 python experiments/run_historical_surface_flux.py
python experiments/compare_diffusion.py --stage analyse
python experiments/compare_diffusion.py --stage export
```

The thread variables avoid excess BLAS threading overhead, not parallelise the
model. The runner defaults to the diffusion configuration; `--config PATH` and
`--root PATH` remain available. Existing run directories are protected against
overwrite. Changing kappa or disabling diffusion requires a separate configuration
and output directory. A disabled switch or kappa=0 uses the original independent-cell
backward Euler path. The [no-diffusion configuration](../configs/historical_surface_flux_era5_initialised.toml)
remains available for fresh reproductions, not overwriting the preserved baseline.

`compare_diffusion.py --stage all` performs analysis/export only; it does not
rerun integration. It checks identical grids, masks, initial fields and months,
then compares both models with ERA5, calculates diffusion-minus-baseline effects,
and generates native H/SST/variability maps and regional/hemispheric series.
The export writes five monthly SST arrays and separate static H at 0.5-degree
resolution. Launch from `frontend/` with `npm run dev`; export before building.

## Existing SST preparation and baseline

`compare_era5_sst.py` retains `prepare`, `run`, `analyse` and `all` stages for the
original historical ERA5 reference workflow. Preparation requires the newly
supplied SST and refuses existing products; it does not invoke the removed-raw
atmospheric/MLD workflow. Do not repeat preparation for visualization, change the
1979–2025 climatology, recalculate H or recalibrate damping. New static exports
are produced only by `compare_diffusion.py`.

See [surface/diffusion equations](../docs/surface_flux_model.md),
[ERA5 comparison definitions](../docs/era5_comparison.md),
[frontend usage](../frontend/README.md) and [output conventions](../runs/README.md).
Numerical conservation/convergence is distinct from physical agreement with ERA5.
