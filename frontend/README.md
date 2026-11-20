# Static numerical field viewer

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
  TypeScript transpilation helper, with new boundary-validation and demo tests.

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
- `null` denotes unavailable values. In-memory NaN and infinities are normalized
  to `null`; wrong types, lengths, IDs or bounds are rejected. JSON producers
  should emit `null` directly. Zero stays a valid physical value. No land mask
  or scientific interpretation is inferred.

Inputs pass through `validateDataset`; `GridLayer` also validates and copies its
inputs. Future parsed outputs can use this boundary without depending on their
producer. The renderer does not read NetCDF or import Python. It keeps numerical
values separate from colors, so percentile clipping never changes tooltip values.

Percentiles exclude unavailable values. Sequential scales stretch their selected
range with square-root normalization. Diverging scales take the larger absolute
percentile endpoint as a symmetric extent, keeping physical zero at the neutral
midpoint. Constant and all-missing fields are supported. The legend uses the same
transfer function as the grid; its bar is linear in numerical values.

`GridLayer.setField` accepts replacement values/metadata for its fixed grid and
updates colors without recreating geometry or the viewer. Legend and tooltip
components accept optional timestamps. This is a static-field interface, not
playback: there is no time controller, streaming, API, or run manager.

## Synthetic demonstration

The deterministic demo has 288 rectangular 15° cells covering the globe. Values
are `sin(latitude) × cos(2 × longitude)` at cell centres, with every 29th value
missing. Units are `1` (dimensionless). This arbitrary mathematical wave is
**not observational SST, a climatology or model output**. It includes positive
and negative values and explicit gaps to exercise the display. It intentionally
has no simulation timestamp or geographic land mask.

Tests cover percentile interpolation, sequential/diverging normalization,
clipping, one-sign and constant fields, missing/nonfinite values, data validation
and deterministic demo generation. They do not create a WebGL context; interactive
rendering should also be checked in a browser after Cesium or rendering changes.
