# Experiment configurations

## Baseline surface damping

[surface_damping.toml](surface_damping.toml) is the small tracked baseline for
the first globally uniform effective damping experiment:

- `surface_damping.mode`: `constant`.
- `surface_damping.gamma_w_m2_k`: the computed positive scalar in W m⁻² K⁻¹,
  applied to every active ocean cell in both extratropical hemispheres.

Regenerate from the repository root with
`python experiments/prepare_model_inputs.py`. The existing preparation workflow
computes the value from reliable positive primary/lag-1/turbulent spatial damping
estimates; it never refits the underlying feedback. Full provenance and statistics
are in local `data/processed/manifest.json` and `data/processed/report.md`. See the
[data guide](../data/README.md) for selection, area weights and scientific limits.

Regeneration overwrites the generated baseline, not unrelated configurations.
The value is provisional, not a validated physical constant.

## Historical surface-flux experiment

[historical_surface_flux_pilot.toml](historical_surface_flux_pilot.toml) defines
the 24-month pilot, physical constants, initial state, input/output paths and
two physics switches. It reads the baseline above by default. To override the
coefficient for sensitivity analysis, copy the pilot configuration, select a new
output directory and add a finite nonnegative `gamma_w_m2_k` under its
`[surface_damping]` section. `configuration` may also identify another constant
damping TOML file. Neither approach modifies the prepared spatial inputs.

See the [experiment guide](../experiments/README.md) for commands and full-record
settings; the [model guide](../docs/surface_flux_model.md) defines the equations
and switch semantics.

Keep experiment parameters/units and future random seeds explicit. Reference
local datasets without secrets or machine-specific absolute paths. Generated
experiment outputs belong under [runs/](../runs/).
