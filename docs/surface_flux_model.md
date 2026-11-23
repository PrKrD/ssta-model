# Historical surface heat-flux model

This first model integrates independent extratropical ocean cells using
historically prescribed atmospheric variability. It is not a stochastic
simulation and has not been validated against observed SST.

The separate [ERA5 retrospective comparison](era5_comparison.md) now evaluates
the historical response against monthly reference anomalies, with observed
January initialization and unchanged physics. This does not establish independent
forecast skill or validate the provisional feedback coefficient. The original
zero-initialized 24-month experiment described below remains available.

## Equations and units

For SST anomaly T (K), prescribed downward heat-flux anomaly F (W m⁻²), fixed
depth H (m), density ρ (kg m⁻³), specific heat cₚ (J kg⁻¹ K⁻¹) and globally uniform
damping γ (W m⁻² K⁻¹):

```text
ρ cₚ H dT/dt = F − γ T
F(x,y,n) = Σ[k=1..12] βₖ(x,y) PCₖ(n)
Tₙ₊₁ = [Tₙ + Δtₙ Fₙ/(ρ cₚ H)] / [1 + Δtₙ γ/(ρ cₚ H)]
```

Positive F warms; positive γ opposes either sign of anomaly. Backward Euler
evaluates damping at the new temperature. Monthly forcing is constant over each
calendar interval. H never changes with time. The maximum positive monthly MLD
climatology is the existing proxy for late-winter depth; this approximation has
not been independently verified as late-winter H.

The pilot chooses ρ=1025 and cₚ=3990 in the configuration, not in numerical
functions. γ comes from the separate [baseline](../configs/surface_damping.toml),
currently 16.072239642825945 W m⁻² K⁻¹, unless the experiment overrides it. It is a
provisional effective coefficient aggregated from reliable positive estimates,
not a fully validated physical feedback constant. Zero damping is supported.

## Inputs and domain

Use only the seven [prepared products](../data/README.md): each hemisphere's
PC, regression and surface files, plus the ERA5 ocean mask. The run also requires
their `manifest.json` for checksum verification and preprocessing provenance.
No raw damping field is loaded during integration.

North and south each use their own original ordered modes 1–12, original PC
signs/standardisation, and raw year-round joint latent-plus-sensible turbulent
coefficients. There is no intercept, seasonal averaging, feedback adjustment,
refitting or combined 24-mode basis. This reconstructed raw turbulent regression
proxy is prescribed as F by modelling choice; it is not the complete observed
net surface heat flux.

The native 0.25° scientific grid is retained. North includes centres ≥20°N; south
includes centres ≤−20°S. The saved `input_valid` mask must exactly match
`lsm < 0.5`, finite positive H, and all 12 finite coefficients on this domain.
No local damping, reliability, sea-ice or open-water criterion gates integration.
Invalid cells remain NaN, including in saved SST. No interpolation or tropical
SST values are introduced. Initial anomalies are zero on valid cells for the
pilot. An alternative finite scalar initial condition can be configured; every
run starts anew at its configured first month (there is no restart mechanism).

## Calendar and output convention

January 1979 PCs force the interval **1 January–1 February 1979** (31 days).
That post-integration SST state has `time = 1979-02-01T00:00:00Z`,
`forcing_month = "1979-01"`, and `time_bounds` spanning that January interval.
These are boundary states, **not monthly mean SST anomalies**. A later comparison
with observed monthly means must account for this distinction.

Timesteps use actual Gregorian month lengths, including leap February. The
24-month pilot's last forcing month is December 1980; its last state is at
1 January 1981. The complete PC record has 574 months, January 1979–October 2026,
whose final boundary would be 1 November 2026.

## Configuration and execution

See the [experiment instructions](../experiments/README.md). The two boolean
`physics.surface_forcing` and `physics.surface_damping` switches respectively
replace F or γ with zero in the equation. They do not hide output layers. Both
off preserves any configured initial anomaly. Positive finite density and heat
capacity, finite initial anomaly, finite nonnegative scalar γ and continuous
available monthly dates are required. Invalid inputs raise errors.

## Numerical evidence and limitations

Controlled [tests](../tests/test_surface_simulation.py) check the disabled-process
identity, signed damping recurrence, approach to F/γ equilibrium, undamped heating
and cooling signs, ordered 12-mode reconstruction, cell-local missing values,
discrete energy closure, leap/calendar boundaries and time alignment. Small
NetCDF fixtures exercise all four physics-switch combinations, nonzero initial
conditions, independent hemispheres, exact repeatability, compression, provenance
checksums, mask validation and overwrite refusal. Tests require no local datasets.

Each real timestep verifies the unrounded discrete heat budget in W m⁻²:

```text
residual = ρ cₚ H (Tₙ₊₁ − Tₙ)/Δtₙ − (Fₙ − γ Tₙ₊₁)
```

The tolerance is 1e−10 times the maximum of 1 W m⁻², |F| and |γT| in that frame.
Active non-finite values fail the run. Stored float32 fields are read back each
month; masks must remain missing and the absolute error must be no greater than
float32 epsilon times max(1 K, max|T|). State and calculations remain float64.
Residuals concern this state, not the rounded output. No anomalies are capped.

Monthly CSV files report area-weighted spatial means using the full-grid
spherical cell areas already defined in the data guide. Standard deviations
(population, ddof=0), extrema and quantiles are **unweighted across active cells**,
not temporal standard deviations. JSON includes each month's statistics, the
range over all saved frames, and the final spatial standard deviation.

Numerical stability and discrete budget closure do not validate the physical
forcing proxy, damping estimate or fixed-depth approximation. Raw regressions
may overlap with explicit SST damping; no independent feedback correction
has been applied. Sea-ice-covered ocean may be active without sea-ice physics.
Initial-condition transients and the lack of transport limit interpretation.
There is no stochastic PC generation, advection, diffusion, subduction, obduction,
salinity, scientific regridding, API or frontend connection. Full-record execution
is supported by configuration; the initial milestone runs only the pilot.
