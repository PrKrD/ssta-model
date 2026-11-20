# Generated runs

Write generated simulations, diagnostics, plots, logs and results here. Everything
except this README is ignored by Git. Use a separate directory per run to avoid
overwriting results. The historical surface-flux experiment refuses existing
output directories, including partial runs. There is no run manager.

Each completed historical run contains:

- `north_sst.nc` and `south_sst.nc`: compressed NetCDF4 SST, coordinates,
  `time_bounds`, `forcing_month`, `input_valid`, fixed H and cell areas. SST
  chunks are one month × up to 64 latitude × 240 longitude cells. Float32
  storage is checked against float64 integration each month. Invalid SST is NaN.
- `north_monthly.csv` and `south_monthly.csv`: area-weighted SST mean, unweighted
  spatial standard deviation/quantiles/extrema, non-finite count, heat-budget
  residual and storage error for each post-integration monthly state.
- `configuration.json`, `provenance.json` and `preprocessing_manifest.json`:
  resolved settings, input/configuration/source SHA-256 hashes, code revision and
  dirty flag, software versions and copied preprocessing provenance. NetCDF
  attributes also embed configuration and run provenance.
- `summary.json`: completion/failure status, runtime, cell counts, statistics
  for each month, final spatial standard deviations, full-run extrema, maximum
  residual/rounding errors, and output file sizes/checksums. Failed runs retain
  their partial outputs; only a `complete` status denotes success.

`time` is the exact UTC interval-end boundary, not a monthly average. For
January forcing the saved boundary is 1 February; `forcing_month` and bounds
identify January explicitly. Do not compare boundary states with observed
monthly means without accounting for this convention. Numerical residuals are
computed before output rounding, and do not measure observational agreement.
No full-resolution forcing cube is saved.

See the [experiment instructions](../experiments/README.md) and
[scientific assumptions](../docs/surface_flux_model.md). Future stochastic runs
must additionally record seeds and random-generator details.

## Generated visualization diagnostics

The offline exporter adds `visualization/export_report.json` and
`visualization/export_report.md` under the selected run, plus the native 0.25°
diagnostic `native_sst_1980-05.png` by default. The map reads saved SST directly,
with longitude/latitude axes, symmetric zero-centred colours in K, and gray
missing regions. It is independent of 5° display aggregation. It labels May's
post-integration state at 1 June 1980 UTC, not a monthly mean.

The JSON display asset is generated separately under `frontend/public/data/`
and remains ignored. Native NetCDF outputs and source provenance are preserved.
The export reports record their SHA-256 identities, tile/frame counts, asset
size, null count and independent sampled area-weighted aggregation errors.
See the [export command](../experiments/README.md#offline-sst-visualization-export).

Track [experiment definitions](../experiments/) and
[configurations](../configs/) separately from generated results.
