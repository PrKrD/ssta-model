# Repository cleanup and interactive retention

Local audit: 27 November 2026. The audit included ignored files, not just Git
contents. Scientific calculations, inputs, grid, initialisation, parameters and
historical outputs were not changed. No full historical simulation was rerun.
Detailed inventories, deletion plans, checksums and browser screenshots are saved
locally under ignored `runs/repository_cleanup/`.

## Storage measurements

`du -sk .` measured **9,672,744,960 bytes (9.008 GiB)** before cleanup.
After cleanup and final validation it measured **7,993,438,208 bytes (7.444 GiB)**,
a net reduction of **1,679,306,752 allocated bytes (1.564 GiB)**.
This snapshot precedes the small final documentation/commit write. These are
sums of allocated
filesystem blocks, including ignored dependencies/data and `.git`; APFS shared
blocks/compression mean they are not a claim about exclusive physical disk use.

The category table uses measured **logical file bytes**, immediately before and
after each removal. Interactive storage uses the initial audit and final check;
two real browser validation runs increased that category. Negative savings mean
new validation output, not deletion. The category total differs from the whole
workspace block delta because it excludes retained files, audit growth, source
edits and directory/filesystem overhead.

| Category | Before (bytes) | After (bytes) | Saved (bytes) |
|---|---:|---:|---:|
| Interactive simulation outputs | 64,306,868 | 192,866,676 | -128,559,808 |
| Obsolete generated outputs | 1,464,323 | 0 | 1,464,323 |
| Temporary/build files | 1,813,710,281 | 836,536 | 1,812,873,745 |
| Other safe cleanup | 174,176 | 0 | 174,176 |
| **Total** | **1,879,655,648** | **193,703,212** | **1,685,952,436** |

All removed files were Git-ignored. **No tracked files were deleted**, and no Git
history was rewritten. Disk savings therefore do not reduce historical Git
objects. `.git` was 2,252,800 allocated bytes initially; the final commit adds
only source/tests/documentation, not generated datasets.

## Removed and preserved

- Removed `frontend/dist/` after a successful final production build. Its public
  comparison data duplicated the retained `frontend/public/data/` assets. Two
  old local preview processes were stopped before removal; the development
  server remains available. Run `npm run build` before using preview again.
- Removed `.pytest_cache/`, `.ruff_cache/`, and Python `__pycache__/` directories
  under `src/` and `tests/`. Final checks regenerated small Python caches,
  included in the table's after column. Installed dependencies and Vite's active cache remain.
- Removed only four SHA-256-identical duplicate figures from
  `runs/h_rebuild_reproducibility/diagnostics/`: `global_H_comparison.png`,
  `north_atlantic_H_detail.png`, `mask_comparison.png`, and
  `north_atlantic_mask_detail.png`. Canonical originals remain under
  `runs/h_rebuild_comparison/`; the duplicate report's links now point there.
  Reproducibility NetCDF products, summary and report remain.
- Removed 24 Finder `.DS_Store` metadata files. No unique scientific logs,
  observations, figures, source modules or reproduction configurations were removed.

Processed ERA5 SSTA/climatology, PCs, regressions, original and both bilinear H
variants, mask comparisons, original MLD source and ERA5 raw source all remain.
All three full historical experiments and their native comparison figures remain.
All pre-existing protected scientific/display files retained their sizes/mtimes;
six full historical NetCDF SHA-256 values match their saved summaries. Audit
checksums are recorded separately. Repeated preprocessing manifests are retained
as each experiment's provenance, even where their hashes are identical.

## Largest remaining directories

| Directory | Before (allocated bytes) | After (allocated bytes) | Reason retained |
|---|---:|---:|---|
| `data/` | 2,512,248,832 | 2,512,240,640 | Required raw/processed scientific inputs and provenance |
| `runs/` | 2,854,232,064 | 2,989,912,064 | Three full historical experiments, scientific diagnostics and retained interactive results |
| `frontend/` | 3,839,598,592 | 2,024,701,952 | Current comparison assets, working dependencies and source |
| `experiments/` | 36,864 | 36,864 | Thin reproducible scientific commands |
| `src/` | 823,296 | 327,680 | Scientific package and optional local API |
| `configs/` | 24,576 | 24,576 | Reproduction configurations |
| `.venv/` | Not separately sampled | 462,774,272 | Working Python scientific/API toolchain |
| `.git/` | 2,252,800 | 2,244,608 | Repository history; no history rewrite |

## Retention and local application checks

The five-completion policy is described in [interactive damping](interactive_damping.md).
The initial local inventory contained only one completed interactive directory,
`f8dc1c2efdd84bd0ae0f0af2e3e14d96`, about 64 MB. Its request/summary identify
`interactive_damping`, both native files exist, and all 24 display frames exist.
No active worker was running when the initial application of retention was
planned. It was retained; **zero existing runs exceeded the limit**.

After two actual browser validations, three completed runs remain (all below five):
`5708f1643cd4409299801faec589ceb9`, `1e9ed220960b44cdad9b5715bb2f8b23`,
and the original `f8dc1c2efdd84bd0ae0f0af2e3e14d96`, newest first.
No unrecognised/incomplete scientific directories were deleted. Automated tests
exercise six/eight synthetic completions in temporary directories rather than
creating or deleting extra actual research runs to demonstrate the cap.

Validation: **81 Python tests, 32 frontend tests, Ruff lint/format, and production
build passed**. The existing HTTPX TestClient deprecation and Cesium large-bundle
warnings remain nonfatal. Retention tests cover fewer/exactly/more than five,
completion ordering, active/queued protection, transmitting-response protection,
legacy detection, symlinks, partial failure products, HTTP 410 across restart,
completed-result access and cleanup errors preserving successful simulations.

The final browser run used gamma=10 and automatically loaded 24 monthly states.
Month stepping, layer switching (including static H), mouse rotation/zoom and
picking worked. A February interactive tooltip showed -0.55743 K at 38.75 S,
2.75 W, next to the cursor (650,500 -> tooltip 664,514 CSS px), demonstrating
correct canvas-offset handling. Solver source and fixed configuration are unchanged. Both hemispheres of the final
gamma=10 run match the pre-cleanup gamma=10 run exactly: initial state, all 23
integrated fields and active masks. Completed results remain accessible after
restarting the API with the final code.

Desktop container/canvas bounds were checked at 1024, 1280, 1440 and 1920 CSS px;
the left edge is 340 px and width is viewport minus 340. At 900 and 390 px the
globe uses the full width. A resize observer follows layout changes and disconnects
on viewer destruction. Screenshots were inspected; the integrated browser can
reset its emulated viewport to 1024x768, so checks record the actual viewport
alongside bounds. The geographic camera target is unchanged. Timed autoplay in
a visible tab was not directly observed; playback control and stepping tests pass.

## Manual review only

Retain the approximately 17 MB of short historical diffusion/bilinear-H checks:
they are referenced verification experiments, not safely identified obsolete
runs. The approximately 3.5 MB H reproducibility directory has NetCDF files with
different hashes from processed counterparts; these may encode provenance
metadata differences and were preserved. Review with scientific context before
removing. Retain current dissertation figures and candidate/mask diagnostics.
The active Vite cache and installed dependencies are regenerable but useful to
the working application. No unused source module was positively identified.

Inspect future usage with `du -sk data runs frontend .venv .git` and
`du -k -d 2 runs frontend | sort -nr | head -40`. Confirm references and provenance
before deleting individual products. Longer interactive periods will need a
separate output policy if the five-run cap becomes too costly; no formats,
compression or scientific accuracy were changed here.
