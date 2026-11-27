# Scientific commands

Reusable calculations live in `ssta_model`; scripts are thin. Existing processed
scientific inputs and all tracked experiment configurations remain available.

## Active primary model and viewer

The default historical runner configuration is
[bilinear H with diffusion](../configs/historical_surface_flux_bilinear_h.toml).
The existing `runs/historical_surface_flux_bilinear_h/` is complete and preserved;
do not rerun integration for display. Export from its saved outputs and processed
ERA5/H only:

```sh
python experiments/export_historical_viewer.py
```

The destination defaults to `frontend/public/data/era5_comparison/` and must not
exist. Use `--destination runs/historical_display_next` to prepare a replacement
for validation before swapping assets. No H, forcing or ERA5 preparation occurs.
See [viewer contract](../frontend/README.md) and [retirement](../docs/historical_retirement.md).

To reproduce a scientific integration deliberately, choose a new output directory
in a copy of the tracked configuration, then run:

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 python experiments/run_historical_surface_flux.py --config PATH
```

The runner refuses existing outputs. Test with pytest/Ruff and a short
actual-data solve before a long integration. Thread settings avoid BLAS overhead;
physics, conservation and solver tolerances stay in the scientific package.

## Archived sensitivity workflows

Original containing-cell H with and without diffusion are retired from local
native storage and the active viewer. Their configurations and all numerical
implementations remain reproducible. Summaries, model–ERA5 metrics, monthly CSVs,
provenance and unique scientific figures are archived locally under
`runs/archived_historical_sensitivity/`. [Recorded conclusions](../docs/historical_retirement.md)
explain their limitations. Short completed check outputs were also retired after
preserving validation records.

`compare_bilinear_h.py --stage analyse` requires reproduced A/B/C native runs.
`compare_diffusion.py --stage analyse` requires reproduced A/B. Their `export`
stages produce only archived old-format assets under
`runs/archived_historical_sensitivity/`, never the current viewer. The original
`compare_era5_sst.py` retains its explicitly invoked preparation/run/analysis stages
for reproducing the no-diffusion reference. These are archived research commands,
not prerequisites for the current application. Original-H processed inputs remain
required by runtime validation and those configurations.

## Input/H preparation (not run for viewing)

`finalise_h_candidate.py` prepares ERA5-targeted bilinear H from the original MLD
source with limited baseline polar retention. `rebuild_h_field.py` prepares the
old-mask comparison and static diagnostics. Both are separate from integration;
see [candidate provenance](../docs/h_era5_candidate.md) and
[H reconstruction](../docs/h_rebuild.md). Existing processed H/mask comparison
products, original raw MLD and ERA5 SST are preserved. Do not recalculate H,
climatology, forcing regressions or damping simply to regenerate the viewer.
