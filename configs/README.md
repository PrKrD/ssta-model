# Experiment configurations

[interactive_damping.toml](interactive_damping.toml) fixes the local interactive
experiment to January 1979–December 1980 with observed initialization, bilinear H
and diffusion. The API overrides only gamma and the unique output directory;
it never rewrites this template or baseline damping. See [local execution](../docs/interactive_damping.md).

[historical_surface_flux_bilinear_h.toml](historical_surface_flux_bilinear_h.toml)
is the primary historical runner default and selects
`mixed_layer_depth.variant="era5_bilinear"`. It originated as the controlled H-only
sensitivity. The default `baseline` variant preserves older configurations.
All forcing/damping/diffusion/initialisation/solver settings match the original-H
diffusion experiment. The loader validates the original complete input mask,
then selects existing candidate H without activating its additional finite cells.
No candidate regeneration or raw MLD reading occurs. See [experiment](../docs/h_sensitivity.md).

[surface_damping.toml](surface_damping.toml) is the unchanged provisional global
coefficient, 16.072239642825945 W m-2 K-1. Its original calibration provenance is
in local `data/processed/manifest.json`. Do not regenerate it or restore removed
raw inputs for this experiment.

[historical_surface_flux_era5_initialised.toml](historical_surface_flux_era5_initialised.toml)
defines the archived no-diffusion reference. Its local native outputs are
retired; configuration, processed original-H inputs and solver remain for
reproduction. An omitted `horizontal_diffusion` switch defaults to false.

[historical_surface_flux_with_diffusion.toml](historical_surface_flux_with_diffusion.toml)
defines the archived original-H diffusion experiment and
adds `physics.horizontal_diffusion=true`, `parameters.kappa_m2_s=1000.0`, and solver
settings. Kappa must be finite/nonnegative and can be changed in a copied
configuration for future sensitivities. At zero, or with the switch false,
integration uses the original backward-Euler kernel exactly. The present task
uses 1000 without tuning against ERA5.

Solver settings are `rtol=1e-12`, `maxiter=500`, independent relative flux residual
limit `1e-10` and maximum absolute physical residual `1e-6` W m-2. Failures abort;
settings are never loosened automatically. rho=1025 kg m-3 and cp=3990 J kg-1 K-1
remain unchanged, and damping is read from the baseline file. All three physical
switches act on the governing equation, not field visibility.

All three historical configurations use January 1979 ERA5 SSTA only for initialization,
then February 1979–October 2026 forcing. Scalar/zero initialization remains an
option in the runner. Paths inside TOML are repository-root relative. Choose new
output directories under `runs/` for reruns or sensitivities. Retired demonstration
configurations are no longer shipped. See [execution](../experiments/README.md).
