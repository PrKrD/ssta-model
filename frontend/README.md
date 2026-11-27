# SST anomaly modelling viewer

Framework-free TypeScript/Vite/Cesium. Historical viewing uses local static
assets independently of Python; the optional API runs one interactive damping
experiment at a time. No runtime NetCDF parser, database, ion token or remote
imagery is required. Use WebGL and Node.js 22+.

## Run and regenerate assets

The primary scientific run is `runs/historical_surface_flux_bilinear_h/`.
Existing display assets open immediately with:

```sh
cd frontend
npm ci
npm run dev
npm test
npm run build
```

To export when the destination does not yet exist, from the repository root:

```sh
python experiments/export_historical_viewer.py
```

Only the saved primary model and `data/processed/` are read. No integration, H
reconstruction or regression fitting occurs. For replacement, use
`--destination runs/historical_display_next`, validate that export, then move
the prior `public/data/era5_comparison/` aside and put the validated directory
there. The exporter refuses existing destinations. Build after installing the
assets; Vite copies them into `dist/`. `npm run preview` serves that build.
Remove a regenerable build when no preview server needs it to avoid duplication.
Unknown/old manifest formats produce an explicit regeneration error.

## Layers and playback

The four historical selections are **Model SSTA**, **ERA5 SSTA**,
**Difference — Model − ERA5**, and **Mixed-layer depth H**. Model means the
current bilinear-H, diffusion-enabled historical simulation. All anomaly layers
share 574 calendar states: January 1979 observed initialisation, then February
1979–October 2026 integrations, with exact interval-end timestamps. ERA5 remains
a monthly mean associated by the existing calendar-label convention.

Switching anomaly layers preserves the month. Play loops; scrubbing/stepping
pauses. Speeds are 0.5x/1x/2x at a 6-frame/s baseline; hidden tabs suspend playback.
Static H pauses/disables playback while retaining the historical index. Anomalies
use zero-centred diverging colours; model and ERA5 share fixed full-history
sampled populations, while their difference has its own symmetric population.
H uses a sequential scale in metres. Percentile controls and physical-value
tooltips remain; clipping changes colours only, and limits do not vary by month.

## Compact data boundary

`public/data/era5_comparison/manifest.json` uses `sst-comparison-f32-v4`:
one 0.5-degree grid, calendar/timestamp arrays, frame paths, fixed populations,
provenance and `staticDepth`. Each monthly binary contains **two layer-major
little-endian float32 arrays: model, ERA5**. `depth.bin` contains static bilinear H.
[comparison.ts](src/data/comparison.ts) subtracts stored values for Model−ERA5;
either missing/non-finite operand produces missing, never zero. It validates
metadata, geometry, calendar and buffer sizes, retaining at most three monthly
buffers and one static H buffer. Stale requests cannot replace newer selections.

Native science stays at 0.25°. Model and ERA5 use the same finite native ocean
support and saved cell-area weights. H independently uses finite positive depths.
The geometry intentionally preserves the union of original/bilinear processed
H tiles, including coastal H-only tiles, so retained interactive grids remain
compatible. Original H is used only for that geometry, never displayed as a layer.
SST stays missing outside common support; tropical tiles are omitted. Tooltip
counts describe native H-grid membership, not monthly finite contributors.
Native centres use half-degree bins with periodic longitude and the existing
closed southern/polar edge rules. Coastal rectangles approximate ocean support.

H is maximum monthly de Boyer Montégut (2023) climatology
([DOI](https://doi.org/10.17882/91774)), density threshold 0.03 kg/m³ from 10 m.
Its periodic source-mask-aware bilinear interpolation targets ERA5 ocean;
original H is retained beyond ±89.5° at baseline active cells. H remains fixed,
and interpolation adds no observational resolution.

## Interactive damping and layout

Start `python -m uvicorn ssta_model.api:app --reload` from the root after
installing `.[api]`. Vite proxies `/api` to port 8000. Change gamma with the slider
or precise numerical input, then press **Run Simulation**. The completed
24-state result becomes an additional selection automatically. Historical and
interactive timeline positions are remembered separately. Only gamma changes;
see [fixed settings and five-run retention](../docs/interactive_damping.md).

Interactive v1 outputs remain compatible because the grid ID, bounds, cell order
and geometry are unchanged; old grid-manifest hashes remain provenance, not an
identity test. Returned geometry is validated explicitly. An incompatible grid
is rejected with a reload/regeneration message, never silently remapped.

The app uses a two-column CSS grid: a 340 px sidebar allocation (320 px panel
plus 20 px gutter), then the remaining space for Cesium. A container query uses
an overlay only below the space required for that sidebar plus a 280 px globe
(620 CSS px). Thus 700–900 px widths still have a separate globe area; browser
zoom is handled using the actual container's CSS width. Narrow screens retain
the compact overlaid menu. The globe fills the remaining column at full height.

A resize observer updates the real canvas, projection and rendered frame after
layout or zoom changes. The perspective field of view preserves the original
angle along the shorter canvas axis, preventing initial global-view clipping
in tall/narrow or short/wide spaces. Camera position, orientation and geographic
target are unchanged; rotation and zoom remain available. Picking uses canvas
coordinates and tooltips add its viewport offset.

Layout validation covered 1440, 1024, 900, 800, 700 and 390 px windows at native
Chromium zoom 100%, 125% and 150%, plus the 619/620/621 px transition. Actual
screenshots were checked for the Earth's rendered centre and clipping, alongside
canvas bounds. UI checks covered playback, layer switching, picking, damping
inputs and a mocked completed-result load without running the scientific model.

Generic [field validation](src/data/field.ts), [globe rendering](src/globe/),
[playback](src/PlaybackController.ts) and [UI controls](src/ui/) remain modular.
Cesium assets are bundled under `/cesium`; serve at the website root. The bundle
remains large. See [architecture](../docs/architecture.md),
[historical retirement and storage](../docs/historical_retirement.md) and
[scientific comparison conventions](../docs/era5_comparison.md).
