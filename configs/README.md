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
For future sensitivity studies, copy it to a different experiment configuration
and override the scalar there. No solver or override-resolution system is
implemented yet. The value is provisional, not a validated physical constant.

Keep experiment parameters/units and future random seeds explicit. Reference
local datasets without secrets or machine-specific absolute paths. Generated
experiment outputs belong under [runs/](../runs/).
