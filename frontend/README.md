# Historical SST diffusion comparison viewer

Framework-free TypeScript/Vite/Cesium, independent of the scientific Python
runtime. No API, database, runtime NetCDF parser, ion token or remote imagery
is used. WebGL and Node.js 22+ are required.

## Run

From the repository root, after both historical model runs exist:

```sh
python experiments/compare_diffusion.py --stage export
cd frontend
npm ci
npm run dev
npm test
npm run build
npm run preview
```

Export before production builds; Vite copies generated static assets. The
comparison is the only default experience. Missing/old assets produce an
explicit error directing you to regenerate them, with no demonstration fallback.
Synthetic and 24-month demonstration routes, assets and application code were
retired. Useful generic data, colour and playback tests remain.

## Layers and controls

The selector contains:

1. Model SSTA — With diffusion.
2. Model SSTA — Without diffusion.
3. ERA5 SSTA.
4. Model with diffusion − ERA5.
5. Diffusion effect — With minus without.
6. Mixed-layer depth H — Static.

The five time-dependent fields share 574 calendar states (January 1979 observed
initialization, then February 1979–October 2026 integrations). Switching preserves
the selected month. Play/pause loops, previous/next and scrubbing pause, speeds
are 0.5x/1x/2x at a 6-frame/s baseline. Hidden tabs suspend playback. A slower
browser may skip intermediate frames rather than changing scientific timestamps.

Selecting **H** pauses and disables playback but keeps the month index. Returning
to an anomaly field restores that month. H is in metres, fixed throughout the
simulation, and uses a locked sequential colour type; percentile controls remain
available. Anomalies default to zero-centred diverging colours. Both models and
ERA5 share fixed full-history colour populations; each difference has its own
fixed symmetric population. Default p2–p98 limits do not change every month.
SST populations use deterministic rotating samples plus exact extrema, so these
are approximate display percentiles, not modified scientific values. Static H
uses every finite display value. Colour clipping never changes tooltip values.

## Static data contract

`public/data/era5_comparison/manifest.json` uses `sst-comparison-f32-v2` and stores
one grid, chronological calendar labels, exact model state timestamps, frame
paths, fixed populations, provenance and the static-depth path. Each monthly
file has five layer-major little-endian float32 arrays in the order above.
`depth.bin` contains one static array. NaN decodes to missing, not zero.
[comparison.ts](src/data/comparison.ts) validates metadata/0.5-degree geometry,
file sizes and decoded fields, caching at most three monthly buffers plus H.
Latest-request tracking prevents stale network responses overwriting a newer
selection. Failed frame requests pause playback and show an error.

Science stays at native **0.25 degrees**. Display tiles are **0.5 x 0.5 degrees**,
using saved native areas. The three SST fields use exactly the same current
finite ocean support. Differences are with-diffusion minus ERA5 or baseline on
that support. H independently uses finite positive processed depths; geometry
also includes H-only coastal tiles, whose SST values remain missing. Counts in
tooltips describe native H-grid cells assigned to a tile, not a claim of identical
finite contributor counts in every SST frame. Tropical tiles are never invented.

Membership uses native centres and half-open south/north and west/east bins.
Exact edges go north/east; the southern -20-degree and northern polar edges are
closed into their domain's last tile. Longitudes wrap to [-180,180), without
rectangles crossing the antimeridian. Coastal rectangles approximate finite
ocean coverage and do not trace the exact coastline. Gray means missing; bare
globe means omitted geometry. Tooltip/legend metadata identify the field, units,
bounds, aggregate, calendar label or fixed H, and exact state boundary when applicable.

## Architecture and provenance

[data/field.ts](src/data/field.ts) retains generic static and in-memory sequence
validation. [globe/GridLayer.ts](src/globe/GridLayer.ts) builds geometry once and
updates colours; [PlaybackController.ts](src/PlaybackController.ts) remains
DOM/Cesium independent. Controls, picking, legend and tooltip stay modular.
Cesium assets are copied locally under `/cesium`. Serve at the website root;
subpath hosting is not configured. The Cesium bundle remains large.

H is the unchanged maximum monthly de Boyer Montégut (2023) climatology,
[DOI](https://doi.org/10.17882/91774), density threshold 0.03 kg m-3 from 10 m,
originally 1-degree data mapped by containing cells. It is not a monthly animation
or a newly estimated depth. The [native H map](../runs/README.md) is generated
from processed science independently of display aggregation.

See [scientific formulation](../docs/surface_flux_model.md),
[comparison conventions](../docs/era5_comparison.md), and
[commands](../experiments/README.md). This is retrospective comparison of
ERA5-related products, not independent forecast validation. No old raw
atmospheric/MLD files are restored or required by the display workflow.
