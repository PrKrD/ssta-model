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

Track [experiment definitions](../experiments/) and
[configurations](../configs/) separately from generated results.
