# Research experiments

Track experiment definitions and thin execution scripts here when needed.
Import reusable functionality from `ssta_model`; do not duplicate calculations
in scripts. Use tracked [configurations](../configs/) and write generated
results, plots and logs under [runs/](../runs/), never beside scripts.

## Historical surface-flux pilot

From the repository root, with the editable Python package installed and the
[seven prepared inputs](../data/README.md) available:

```sh
python experiments/run_historical_surface_flux.py
```

This reads [historical_surface_flux_pilot.toml](../configs/historical_surface_flux_pilot.toml),
runs January 1979–December 1980 in both hemispheres, and writes to
`runs/historical_surface_flux_pilot/`. It starts each active cell at zero K.
Output directories must not already exist: choose a new directory for a rerun;
partial failed runs are preserved with a failed status for inspection.

The script is a thin caller of the scientific package. `--config PATH` selects a
different TOML file. Input, damping-configuration and output paths inside TOML
are relative to the repository root (current directory, or `--root PATH`), not
relative to the TOML file. No datasets are downloaded or generated implicitly.

For sensitivity experiments, copy the configuration, choose a new output
directory, and add `gamma_w_m2_k` under `[surface_damping]`. The baseline file is
still identified in provenance; the resolved override controls integration.
Set `[physics] surface_forcing` or `surface_damping` to `false` to remove that
term from the equation. Parameters and the finite scalar initial anomaly are
also explicit in TOML.

To run the full historical record **after inspecting the pilot**, copy the pilot
configuration to `configs/historical_surface_flux_full.toml`. Change
`experiment.name` to `historical_surface_flux_full`, `experiment.end_month` to
`2026-10`, and `output.directory` to `runs/historical_surface_flux_full`.
Keep `start_month = "1979-01"`, then run:

```sh
python experiments/run_historical_surface_flux.py --config configs/historical_surface_flux_full.toml
```

No scientific source changes are needed. The run streams 574 frames per
hemisphere; it does not retain a full time-space cube. The full period is not
run automatically. Read the [model guide](../docs/surface_flux_model.md) for
equations, units, time alignment, numerical checks and physical limitations,
and the [output guide](../runs/README.md) for diagnostics and provenance.

## Offline SST visualization export

For an existing completed run, from the repository root:

```sh
python -m pip install -e ".[visualization]"
python experiments/export_sst_visualization.py
```

This reads only the two saved SST NetCDF outputs, exports a fixed 5° area-weighted
display sequence to `frontend/public/data/historical_surface_flux_pilot.json`,
and writes export checks/report plus `native_sst_1980-05.png` under the run's
`visualization/` directory. Matplotlib is optional for the package and required
by this command's diagnostic map. The reusable `export_visualization` function
can export JSON without Matplotlib. No new scientific integration is performed.

Original raw datasets were deliberately removed and are not dependencies. Do not
run input preparation to visualize saved output. The exporter does not read PCs,
regressions, prepared-input files, or historical provenance paths.

To regenerate after another completed simulation, pass `--run-dir PATH` and
optionally `--output PATH` and `--map-month YYYY-MM`. For the existing viewer's
default loader, keep the default JSON destination. Start the viewer with
`cd frontend` then `npm run dev`; build after exporting if using production
preview. See [frontend instructions](../frontend/README.md) for binning, masks,
time labels, coastline approximations and the selectable synthetic fallback.

## Historical ERA5 comparison

Install plotting support with `python -m pip install -e ".[dev,visualization]"`.
On fresh outputs, run from the repository root:

```sh
python experiments/compare_era5_sst.py --stage prepare --source data/raw/78c42a1ddf5ba77c929fd589ff5d3c61.nc
python experiments/compare_era5_sst.py --stage run
python experiments/compare_era5_sst.py --stage analyse
python experiments/compare_era5_sst.py --stage export
```

`--stage all` runs the same sequence. Preparation refuses existing ERA5 products;
integration refuses an existing run directory. Do not repeat these stages when
only regenerating diagnostics/display: `analyse` and `export` use existing
scientific outputs and do not read raw SST. Deleted old raw files and the old
preparation pipeline are never required.

The [configuration](../configs/historical_surface_flux_era5_initialised.toml)
initializes January 1979 ERA5 SSTA, then integrates February 1979–October 2026.
The [comparison guide](../docs/era5_comparison.md) specifies the source,
1979–2025 monthly climatology, masks, timestamps, metrics, regional bounds and
spin-up sensitivity. Outputs go to `runs/historical_surface_flux_era5_initialised/`;
its `comparison/` contains CSVs, summary, native variability and five figures.

The ignored static 0.5° assets are under `frontend/public/data/era5_comparison/`.
Export before production builds. Launch with `cd frontend` then `npm run dev`;
comparison loads by default. Its selector preserves the month while switching
Modelled SSTA / ERA5 SSTA / Model−ERA5. `?dataset=pilot` and `?dataset=demo`
retain the earlier datasets. This is retrospective comparison, not independent
forecast validation. No parameter or scientific resolution changes are made.
