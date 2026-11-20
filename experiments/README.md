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
