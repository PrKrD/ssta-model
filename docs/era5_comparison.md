# Retrospective ERA5 SST comparison

This is a retrospective ERA5-related experiment, **not independent forecast
validation**. Atmospheric predictors/regressions and the SST reference originate
from ERA5-related products; the climatology also uses the later historical record.

## SST preparation

The newly supplied `data/raw/78c42a1ddf5ba77c929fd589ff5d3c61.nc` contains `sst`,
identified from `long_name = Sea surface temperature`, in K. It has 1,042 monthly
Gregorian records, January 1940–October 2026, with decoded NaN fill values.
Latitude descends 90° to −90°, longitude increases 0° to 359.75°, both at 0.25°.
Coordinates match the model and prepared mask exactly: no regridding is applied.
Original attributes, source identity and SHA-256 are recorded in
`data/processed/era5_ssta_manifest.json`. The supplied file remains unchanged.

Twelve separate calendar-month climatologies use **1979–2025** complete years,
47 finite samples per cell/month where available. SST anomalies are source SST
minus the corresponding monthly mean, in K. There is no detrending, smoothing,
zero filling or amplitude adjustment; warming relative to the reference remains.
Missing source SST or an entirely missing reference month remains NaN. The
reusable processor also supports explicitly identified Celsius SST inputs.

Retained anomalies cover January 1979–October 2026, inclusive extratropical
centres ≥20°N / ≤−20°S, and existing ERA5 `lsm < 0.5`. No new sea-ice mask is used.
The two `*_era5_ssta.nc` files retain float64 `sst_anomaly(time,latitude,longitude)`,
`sst_climatology(month,...)` in K, finite `climatology_count`, and ocean flags,
with lossless compression. Processing uses bounded spatial tiles because the
source compression chunks span 149 months; no global historical cube is loaded.
The old deleted atmospheric/MLD/damping raw files are never restored or accessed,
and the original preparation pipeline is not invoked.

## Initialization, physics and time

[Configuration](../configs/historical_surface_flux_era5_initialised.toml) selects
`initial_conditions.kind = "era5"` and `month = "1979-01"`. Only this observed
field enters the dynamics. The run mask intersects the original model mask with
finite January SSTA; missing initial cells remain inactive permanently. Later
observations never replace or nudge the model state. Scalar/zero initialization
remains available for controlled experiments.

The January mean anomaly is assigned to the **1 February 1979** boundary before
February forcing begins, by modelling convention. It is saved separately as
`initial_sst_anomaly`, with `initial_month` and `initial_time` attributes, and
displayed under January's calendar label. It is excluded from skill statistics.
There are **573 integrations**, February 1979–October 2026; February ends
1 March 1979 and the final state ends 1 November 2026. The display includes
initialized January for **574 calendar states**.

Model interval-end `time`, `time_bounds` and `forcing_month` remain explicit.
Comparison deliberately matches model forcing/calendar labels to ERA5 monthly
means bearing those labels. Boundary states and monthly means are not identical;
no extra monthly-mean approximation or timestamp correction is implemented.

The no-diffusion baseline retains its governing equation, independent ordered
12-mode hemispheric forcing, raw turbulent coefficients, fixed H and backward
Euler. Parameters
remain ρ=1025 kg m⁻³, cₚ=3990 J kg⁻¹ K⁻¹; γ comes from the unchanged
[baseline](../configs/surface_damping.toml). No recalibration, intercept,
feedback correction, new forcing or transport is introduced in that baseline.
The original seven processed products are preserved. The full historical run is
retained for the controlled diffusion comparison below.

## Native comparison diagnostics

[Analysis](../src/ssta_model/analysis/era5_comparison.py) streams native monthly
fields. Each metric uses the current common finite model/ERA5 ocean support.
Spatial Pearson pattern correlation, spatial population standard deviations and
quantiles/ranges are unweighted; means, bias and RMSE use saved native areas.
Difference is **Model − ERA5**. Undefined correlations are missing, not zero.
Hemispheric summaries give mean monthly pattern r, RMS of monthly area-weighted
RMSE and temporal correlation of area-weighted hemispheric mean series. Months
receive equal weight. Temporal variability maps use online population variance
on common finite months, requiring at least two samples.

Regional series use inclusive latitude bounds and half-open longitude bounds;
antimeridian-crossing ranges wrap explicitly:

| Region | Latitude | Longitude (° east) |
| --- | --- | --- |
| North Atlantic | 20 to 65 | −80 to 0 |
| North Pacific | 20 to 65 | 120 to −100 across 180° |
| South Atlantic | −60 to −20 | −70 to 20 |
| South Pacific | −60 to −20 | 150 to −70 across 180° |
| Southern Indian Ocean | −60 to −20 | 20 to 150 |

Sensitivity starts **January 1981**, excluding the first 24 calendar months
counting initialized January 1979. This removes 23 integrated months, as January
was already excluded. It is arbitrary, not proof of complete spin-up. Memory
depends on H through ρcₚH/γ and can persist much longer in deep cells.

Generated figures under the run's `comparison/` are `maps_1980-05.png` (three
native panels, shared model/ERA5 limits), `hemispheric_means.png`,
`temporal_variability.png` (shared positive scale), `pattern_correlation.png`
and `regional_time_series.png`. CSVs and JSON preserve all monthly diagnostics
and both sensitivity summaries.

## Controlled diffusion comparison and half-degree display

The later [controlled H sensitivity](h_sensitivity.md) compares original-H and
bilinear-H diffusion experiments on identical active masks, initial fields,
months, forcing and numerical/physical parameters. Its primary effect is
bilinear-H SSTA minus original-H diffusion SSTA. The current v3 viewer/export
adds this experiment and both static H layers, with shared H limits and access
to the no-diffusion baseline. Use `experiments/compare_bilinear_h.py` for current
analysis/export. The earlier diffusion-only comparison below remains a separate
record; its legacy v2 export is not the current viewer contract.

The new [diffusion experiment](surface_flux_model.md) adds only conservative
horizontal diffusion with kappa=1000 m2 s-1. Forcing, damping, fixed H, initial
fields, masks and month labels match the preserved baseline. Both models are
compared with ERA5 using the same finite support and metric definitions above.
Monthly diffusion-minus-baseline statistics isolate the process effect, including
changes in spatial variance. Improvements or degradations are reported without
retuning parameters.

[data/historical_export.py](../src/ssta_model/data/historical_export.py) exports
only the current saved bilinear-H diffusion model and ERA5 as two monthly arrays,
plus static bilinear H. The browser derives Model−ERA5 from the stored operands,
leaving missing operands missing. All anomaly fields use common finite native
ocean support and area weights. H uses positive finite processed depths
independently. The existing 0.5° geometry, calendar association and native 0.25°
science remain unchanged. Model/ERA5 share fixed sampled colour limits; the
difference has its own symmetric limits and H uses a sequential metre scale.

The original-H reference comparison described earlier is now an archived
experiment. Its configuration, metrics, figures and numerical implementation
remain reproducible, but its full native outputs are retired from local storage.
See [retirement](historical_retirement.md), [viewer usage](../frontend/README.md)
and [execution](../experiments/README.md).

## Interpretation limits

Trend retention is intentional, and poor agreement is not corrected by detrending
or changing amplitudes. Raw turbulent forcing is not complete net heat flux;
its SST-dependent component is not removed, and damping remains provisional.
Fixed maximum-monthly H, missing transport, sea-ice physics and seasonal depth
limit interpretation. Coastal/ice-affected source SST extrema warrant source
quality and representativeness checks; they are retained, not silently capped.
Weak agreement does not isolate one particular missing physical mechanism.
