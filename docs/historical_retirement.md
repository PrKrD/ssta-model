# Historical experiment retirement and compact viewer

The original-H no-diffusion (A) and original-H diffusion (B) historical runs are
retired from active native storage and the viewer. The **entire bilinear-H plus
diffusion historical run (C)** remains under
`runs/historical_surface_flux_bilinear_h/`, including configuration, native
NetCDF, provenance, diagnostics and scientific figures. This task did not rerun
historical integration, prepare inputs, change physics or rewrite Git history.

## Preserved scientific record

A/B were confirmed `status=complete`, January 1979–October 2026, with 573
integrations after the January observed initial state. Both hemispheres' native
SHA-256 values matched their saved summaries; C passed the same checks. Before
removal, all A/B non-NetCDF records were copied and hash-checked under ignored
`runs/archived_historical_sensitivity/<original-run-name>/`: resolved
configuration, full summary/monthly diagnostics, provenance, preprocessing
manifest, ERA5 metrics, CSV series, verification JSON, reports and every unique
PNG figure. Only the full/derived NetCDF products were omitted from the archive.
The original directories were then removed. The local audit under
`runs/historical_retirement/` records every original file, hash, size and action.

These are previously recorded scientific results, not new analysis. All three
experiments used the same 12-PC historical forcing, raw turbulent regressions,
ERA5 ocean/initialisation support, rho=1025 kg/m³, cp=3990 J/kg/K and global
gamma=16.072239642825945 W/m²/K. A used containing-cell H without diffusion;
B used containing-cell H with kappa=1000 m²/s; C changed H to the ERA5-targeted
bilinear product with the same diffusion. Original containing-cell processed
inputs, both bilinear H variants, masks, raw MLD and ERA5 datasets remain intact.

| Experiment | Hemisphere | Mean monthly spatial r | RMS monthly area RMSE (K) | Mean area bias (K) |
|---|---|---:|---:|---:|
| A: original H, no diffusion | north | 0.283398934 | 0.777949955 | -0.016306279 |
| B: original H, diffusion | north | 0.304289684 | 0.774286183 | -0.016314798 |
| C: bilinear H, diffusion | north | 0.304275716 | 0.774285443 | -0.016303948 |
| A: original H, no diffusion | south | 0.254294427 | 0.569013289 | -0.006012339 |
| B: original H, diffusion | south | 0.271059467 | 0.565812007 | -0.006010945 |
| C: bilinear H, diffusion | south | 0.270948842 | 0.565830974 | -0.006015674 |

Statistics cover 573 integrated months, excluding January initialisation.
Spatial r is unweighted Pearson; RMSE/bias use native ocean areas, with the
existing calendar-label match of model interval ends to ERA5 monthly means.
Full precision, the 550-month spin-up sensitivity and regional statistics remain
in archived summaries/CSV records. These ERA5-related comparisons are retrospective,
not independent predictive validation.

Diffusion reduced spatial variance relative to A (mean B/A variance ratios
0.860749 north and 0.879960 south), modestly raised pattern correlation, and
reduced RMS monthly area RMSE by 0.003664 K north and 0.003201 K south.
Changing B to C then had very small hemispheric effects: r decreased by
0.000013968 north/0.000110625 south; RMSE changed by -0.000000740 K north and
+0.000018967 K south. Maximum local C−B effects were 0.259387 K north and
0.095310 K south. North Atlantic H gradients redistributed anomalies locally;
Labrador/subpolar variability rose slightly while ERA5 series correlations fell
slightly. Smoother H did not demonstrate improved physical skill.

Archived figures include the A/B pattern-correlation, native SST, temporal
variability and regional-series panels, plus B's fixed-H and controlled diffusion
panels. C's entire H-sensitivity figure/metric collection remains in its original
comparison directory. Derived A/B temporal-variability NetCDF were retired;
corresponding figures/metrics remain and the scientific analysis can regenerate
the fields after a deliberate A/B reproduction.

## Reproducibility and inactive workflows

Tracked configurations remain for [A](../configs/historical_surface_flux_era5_initialised.toml),
[B](../configs/historical_surface_flux_with_diffusion.toml), and
[C](../configs/historical_surface_flux_bilinear_h.toml). The primary runner now
defaults to C, while the loader's original-H default/validation and all numerical
implementations/tests remain unchanged. To reproduce A/B, explicitly run those
configurations (or copies with fresh output paths) before invoking the archived
analysis scripts. No reproduction was performed during this cleanup.

`compare_era5_sst.py` analysis requires A; `compare_diffusion.py` requires A/B;
`compare_bilinear_h.py` requires A/B/C. Their scientific source remains available.
Archived export stages now write only under `runs/archived_historical_sensitivity/`.
Neither the active viewer, `export_historical_viewer.py`, API nor interactive
exporter opens the retired A/B native outputs.

Short actual-data diffusion and bilinear-H check directories were verified
complete for January–April 1979. Their summaries, resolved configurations,
provenance, monthly diagnostics and original temporary TOML records are archived;
only reproducible native files were removed. The separate H-rebuild reproduction
products had identical variable names/arrays to retained processed counterparts;
their summary/report were archived before removing those duplicate NetCDF files.
Canonical H/mask comparison figures and original processed products remain.

## Active viewer and export validation

`python experiments/export_historical_viewer.py` exports saved C plus processed
ERA5/H to a fresh destination. It never opens A/B or a previous manifest. The
v4 manifest has the same 128762-cell 0.5° geometry, order and 574-month timeline;
each monthly file stores two little-endian float32 arrays (model, ERA5). Static
bilinear H remains `depth.bin`. Model−ERA5 is calculated in the browser, with a
missing operand leaving the difference missing. Model/ERA5 share fixed sampled
SST limits; difference limits are independently symmetric and H is sequential.
Sampling populations now include only the retained SST fields, so percentile
limits can change from the old four-SST-layer population without altering values.

Every model/ERA5 array in all 574 replacement frames was bitwise equal, including
NaNs, to its corresponding old v3 array: 73690694 common finite pairs. H was
byte-identical. Grid, calendar labels, state timestamps and frame labels were
identical. The maximum browser-derived minus old separately rounded difference
was 8.493661880493164e-7 K: the new result subtracts the stored float32 operands
in JavaScript double precision, instead of storing a third rounded array.
192 independent native aggregation checks had maximum error 0 K; maximum
float32 storage error was 4.7672795489006603e-7 K. Scientific sources were
checksummed before/after export.

The historical layer list is Model SSTA, ERA5 SSTA, Difference — Model − ERA5,
and Mixed-layer depth H, plus the latest completed interactive damping run.
Monthly playback, timeline, picking, percentile controls and desktop globe
centering are retained. Existing interactive v1 results are explicitly compatible
because the grid is unchanged; old manifest hashes remain provenance. New
interactive exports require the v4 grid manifest and retain the same 24-month
period, physical settings and five-completion policy. See
[viewer setup](../frontend/README.md) and [interactive API](interactive_damping.md).

## Measured storage and removal inventory

The table uses actual logical file sizes in bytes, including Git-ignored files.
"Old verification runs" counts archived metadata in the after column. "Other"
contains the retired A/B derived temporal-variability NetCDF, whose figures and
metrics remain. A/B non-NetCDF records were moved into the archive without
claiming their retained bytes as savings. The replacement display was generated,
validated and installed before the old six-layer asset tree was deleted.

| Category | Before (bytes) | After (bytes) | Space saved (bytes) |
|---|---:|---:|---:|

| Obsolete historical native outputs | 1,814,769,201 | 0 | 1,814,769,201 |
| Historical Cesium assets | 1,801,494,806 | 611,469,748 | 1,190,025,058 |
| Old verification runs | 18,205,591 | 261,011 | 17,944,580 |
| Other safely removable files | 13,041,312 | 0 | 13,041,312 |
| **Total** | **3,647,510,910** | **611,730,759** | **3,035,780,151** |

The compact historical dataset totals **611469748 bytes**, including
591275104 monthly binary bytes, 19678359 manifest bytes, static H and its export
report. The six-to-two monthly-array reduction saves approximately two thirds
of the frame storage. A successful production build was verified and then its
622799629-byte regenerable `frontend/dist/` copy was removed; it did not exist
at the initial audit and is not included in initial-workspace savings above.

Deleted full directories:

- `runs/historical_surface_flux_era5_initialised/`
- `runs/historical_surface_flux_with_diffusion/`
- `runs/historical_surface_flux_diffusion_check/`
- `runs/historical_surface_flux_bilinear_h_check/`
- `runs/h_rebuild_reproducibility/`
- `runs/historical_retirement/old_display/`, the staged old six-layer contents
  formerly served from `frontend/public/data/era5_comparison/`; that public path
  now contains the validated v4 replacement.
- `frontend/dist/`, after its production build passed.

The temporary `runs/bilinear_h_check.toml` and `runs/diffusion_check_config.toml`
were moved into the archive's `verification_configs/`. No other scientific data
were selected simply to increase savings. New local audit records and two real
interactive validation runs consume space, so the net whole-workspace reduction
is slightly less than the category savings. Generated files remain ignored; no
tracked data file was deleted and Git history/objects were not rewritten.

## Final validation and remaining storage

**83 Python tests, 33 frontend tests, Ruff lint/format and production build passed.**
Existing solver tests continue unchanged. Focused tests export from controlled
primary/processed files with no A/B paths or prior manifest; they verify exact
weighted values, missing operands, fixed H, calendar, input preservation and
refusal to overwrite. Frontend tests verify two-array decoding, calculated signed
differences, shared timelines, static H, permitted layers and rejection of v3.
Interactive/retention tests still pass. Nonfatal TestClient deprecation and
Cesium large-bundle warnings remain.

Actual browser run `d355debd6b174595a04cbad80e4cd971` used gamma=10, completed
24 states and loaded automatically. Its grid-manifest checksum matches the v4
manifest. A second gamma=10 run, `e7d9cff2b1ab47b99af5aad1a5b948f8`, completed after both
retired historical runs had been deleted, loaded automatically and reproduced
the first validation run's native fields exactly. Five completed interactive
runs now remain, within the unchanged five-run limit. A pre-migration retained
run was also decoded/validated through its API manifest and final frame. No interactive result was discarded for this migration.

Historical layer switching preserved frame 16 (May 1980), shared model/ERA5
limits and state timestamps; static H disabled playback. At cell
`comparison-79632`, model=-0.037288397550582886 K and ERA5=-0.4705085754394531 K,
so the displayed difference was exactly 0.43322017788887024 K. Picking/tooltip
and globe rendering worked. At 1440 CSS px the panel ended at 340 px and the
globe occupied the remaining 1100 px, centred at 890 px; the existing narrow
layout remained full-width. Browser screenshots and checks are under the ignored
audit directory. The integrated browser's high-DPI pointer mapping required a
DOM button click for the post-removal run; the actual frontend submission,
status polling, solver and automatic result loading were exercised. Timed autoplay was not separately remeasured; existing timing,
speed and hidden-tab tests continue to pass.

All 78 pre-existing files in the primary run, scientific data and canonical H
comparison directories retained their byte sizes/mtimes; both primary native
NetCDF hashes match saved completion summaries. No core solver, physical,
forcing or input-preparation implementation was changed. Shared display-only
aggregation was moved into `comparison_export.py` without changing its arithmetic.

Remaining large inputs are intentional: ERA5 raw SST, native anomalies/climatology,
PCs/regressions, original and bilinear H/masks and the raw MLD source. Keep the
entire primary run and its scientific figures. The archive's retained reports,
figures and diagnostics are the evidence for retired sensitivity conclusions,
not candidates for automatic deletion. Older cleanup screenshots/audit inventories
and inactive development caches may be reviewed manually after confirming their
continuing value. No further scientific dataset is recommended for deletion.

Whole-workspace `du -sk .` measured **7,993,663,488 allocated bytes** before and
**5,077,114,880 bytes** after cleanup/validation, a net reduction of
**2,916,548,608 bytes (2.716 GiB)**. This snapshot precedes the
small final documentation/commit write. Allocated block sums include ignored
files and differ from logical category sizes; APFS shared blocks/compression
mean they are not a claim of exclusive physical disk use.
