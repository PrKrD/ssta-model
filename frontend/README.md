# Time-varying numerical field viewer

A framework-free TypeScript/Vite application using CesiumJS. It runs independently
of the Python scientific package and the earlier `globetest` repository. No API,
ion token, remote imagery, scientific datasets or model calculations are required.
WebGL support is required in the browser.

## Run and check

Use Node.js **22 or newer** (required by the retained Cesium lockfile).
From this directory:

```sh
npm ci
npm run dev
npm test
npm run build
npm run preview
```

Open the URL printed by Vite (normally `http://localhost:5173`). Drag to rotate,
scroll/pinch to zoom, and hover or tap a cell for bounds, centre coordinates and
the original numerical value. Change the scale or percentile sliders to recolor
the same cells. Reset restores p2–p98. Gray means missing data, not land.
`npm run preview` serves the production build; a separate frontend CI job runs
installation, build and tests without changing the Python checks.

The demo starts paused. **Play/Pause** controls looping playback; the timeline
selects any of the 120 monthly frames and shows its month and frame number.
**← / →** step one frame. Scrubbing and stepping pause playback; manual steps
stop at the first/last frame, while playing wraps from the last to the first.
Speeds are 0.5×, 1× and 2×, with a baseline of **6 frames per second** (20 seconds
for the full sequence at 1×). Speeds affect presentation only, never timestamps
or underlying values. The legend and any visible tooltip show the current frame's
full UTC timestamp. Playback is suspended while the tab is hidden and resumes
without catching up when it becomes visible.

Cesium assets are copied locally under `/cesium` by Vite. Serve the application
at the web server root; subpath hosting is not configured. The bundle is sizable
because it includes Cesium. No framework or extra test runner was added.

## Components and migration

Adapted from `PrKrD/globetest` frontend at commit
`f3fb7ef74073ab21adeb0b186fdd4b01cc774795`:

- [globe/GridLayer.ts](src/globe/GridLayer.ts): retains batched geometry instances,
  asynchronous readiness handling and per-instance color updates. Rectangular
  cell geometry replaces variable-specific polygons and diagnostic boundaries.
- [globe/ColorScale.ts](src/globe/ColorScale.ts): retains rank-interpolated
  percentiles, sequential square-root normalization and shared cell/legend color
  mapping. Scales now use generic metadata. Diverging limits are symmetric about
  zero, including one-sign fields, rather than using independent signed halves.
- [globe/GridPicking.ts](src/globe/GridPicking.ts): retains Cesium hover/click
  handling with explicit cleanup; picking identifies generic cell IDs.
- [ui/](src/ui/): retains the controls/legend/tooltip responsibilities and bounded
  tooltip positioning. Contents were rewritten for generic fields; native range
  inputs replace bespoke slider dragging and preserve keyboard/touch support.
- [tests/](tests/): adapts the prototype's color tests, Node test runner and
  TypeScript transpilation helper, with boundary-validation, sequence, timing
  and demo tests.

[PlaybackController.ts](src/PlaybackController.ts) owns frame indexing and elapsed
time, with one cancellable animation callback and no Cesium or DOM dependencies.
[ui/PlaybackControls.ts](src/ui/PlaybackControls.ts) supplies native buttons,
timeline and speed selection; [main.ts](src/main.ts) connects these to the
existing renderer. No framework or state-management system is required.

The dependency ranges and locked dependency versions are retained from the
prototype. Viewer setup now lives in [globe/Viewer.ts](src/globe/Viewer.ts);
[main.ts](src/main.ts) only prepares input and wires components. The old
Maximenko JSON URL, velocity/MLD/subduction flags, equatorial diagnostics and
backend exports were removed rather than migrated. No backend code was copied.

## Numerical input boundary

[data/field.ts](src/data/field.ts) defines and validates a deliberately small
in-memory contract. [data/demo.ts](src/data/demo.ts) supplies the current input;
there is no file picker, network loader or backend communication yet.

- `grid`: a stable `id` and ordered `cells`, each with a unique string `id` and
  `west`, `east`, `south`, `north` bounds in degrees east/north. Bounds are finite,
  ordered and within longitude ±180° and latitude ±90°. Longitude spans must be
  at most 180°; split antimeridian-crossing cells before entry. Cells should not
  overlap; validation does not perform a full geometric overlap check.
- `field`: matching `gridId`, `name`, `units`, `description`, default `colorScale`
  (`sequential` or `diverging`), optional UTC ISO `timestamp`, and `values` in
  exactly the same order as `grid.cells`. A changed ordering needs a new grid ID.
- `sequence`: the same common field metadata, plus strictly increasing UTC ISO
  `timestamps` and one numerical `frames` array per timestamp. All frames share
  `gridId`, units and cell ordering; geometry is stored once in the surrounding
  dataset. Validation rejects empty sequences, invalid timestamps and mismatched
  grid IDs, frame counts or cell counts.
- `null` denotes unavailable values. In-memory NaN and infinities are normalized
  to `null`; wrong types, lengths, IDs or bounds are rejected. JSON producers
  should emit `null` directly. Zero stays a valid physical value. No land mask
  or scientific interpretation is inferred.

Sequence input passes through `validateSequenceDataset`; the static
`validateDataset` contract remains available. Validation owns and freezes frame
arrays, converting nonfinite values to `null` once. `sequenceFrame` creates a
small metadata/timestamp wrapper referencing the selected immutable values.
`GridLayer.setField` validates without copying these frozen arrays. Future parsed
outputs can use this boundary independently of their producer. The renderer does
not read NetCDF or import Python. Values remain separate from colors, so display
clipping never changes tooltip values.

Percentiles exclude unavailable values. **The playback population contains every
finite cell value across all frames**, with equal weight per valid cell/frame.
It is sorted once at initialisation. Default p2–p98 limits therefore apply to the
entire sequence, including when a particular frame has missing values or smaller
extrema. Sequential scales stretch their selected range with square-root
normalization. Diverging scales take the larger absolute
percentile endpoint as a symmetric extent, keeping physical zero at the neutral
midpoint. Constant and all-missing fields are supported. The legend uses the same
transfer function as the grid; its bar is linear in numerical values.

`GridLayer` receives the pre-sorted sequence population and retains its resolved
scale while `setField` replaces values/metadata. Limits are recalculated only
when display settings change; reset restores the full-sequence defaults. The
same numerical value therefore keeps the same color through time. Without a
sequence population, the original standalone static-field behavior is retained.

Geometry and viewer instances are reused. Each frame updates per-cell color
attributes, the timestamp and any currently visible tooltip; the fixed legend
gradient is rebuilt only when display settings change. There is no streaming,
backend communication or run manager.

## Synthetic demonstration

The deterministic demo has 288 rectangular 15° cells covering the globe and 120
synthetic monthly timestamps from January 2000 through December 2009. At cell
centres, arbitrary values are generated as
`sin(latitude) × cos(2 × longitude − phase) + 0.35 × cos(latitude) × sin(longitude + 2 × phase)`,
where coordinates are in radians and `phase = 2π × frameIndex / 60`. The two
travelling waves change the spatial pattern smoothly, including across the loop.
Every 29th cell is missing in every frame. Units are illustrative **K**, not a
calibration or claim of physical realism. This is **not observational SST, a
climatology or scientifically simulated ocean output**. Dates are arbitrary demo
labels, with no relationship to historical conditions. No land mask is implied.
The original dimensionless static fixture remains available for existing tests.

All 34,560 cell/frame slots are generated in memory. At this scale, one-time
validation and sorting are inexpensive. Playback uses `requestAnimationFrame`
elapsed time, preserving fractional progress and skipping intermediate displays
when necessary. It renders at most one selected frame per animation callback.
Hidden tabs cancel scheduling; visible stalls longer than one second are discarded
to avoid jumps. Play/pause, speed changes and destruction cancel pending handles
as appropriate. No complete-population sorting, geometry rebuilding or frame-array
copying occurs during playback. There is no temporal interpolation; monthly fields
are displayed as discrete frames.

Tests cover percentile interpolation, sequential/diverging normalization,
clipping, one-sign and constant fields, missing/nonfinite values, data validation,
deterministic demo generation, sequence validation, fixed sequence-wide color
limits, timing, looping, stepping, speed changes and cleanup. Timing tests use an
injected animation clock without real-time sleeps. Unit tests do not create a
WebGL context; interactive rendering should also be checked in a browser after
Cesium or rendering changes.
