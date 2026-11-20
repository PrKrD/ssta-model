# Local scientific inputs

All raw and processed data here are Git-ignored; only this README is tracked.
The original seven supplied NetCDF files were deliberately removed after
preparation to save disk space. Existing processed products and saved model
outputs remain usable. Do not restore raw files or rerun preparation for
[visualization](../experiments/README.md#offline-sst-visualization-export).
The preparation documentation below records the original workflow; its
regeneration command requires separately available originals.
During preparation, the seven files used their original names under `raw/`.
Preparation uses same-filesystem renames, not large-file copies. Original bytes
are verified by SHA-256 before and after processing. Other local files are left
alone. Never commit the NetCDF products or download replacement observations as
part of setup.

## Regenerate

From the repository root, with Python 3.11+ and the editable package installed:

```sh
python -m pip install -e ".[dev]"
python experiments/prepare_model_inputs.py
python -m pytest
ruff check .
ruff format --check .
```

`--data-dir PATH` selects another local input directory;
`--damping-config PATH` selects the generated baseline TOML destination (default
`configs/surface_damping.toml`). Initially place the exact
seven named files below directly here, or in `raw/`. Ambiguous duplicate names
are rejected. Reruns recognize already-organized originals and replace only the
pipeline's own products. Writers verify exact decoded-value/missing-mask round
trips before atomically publishing each NetCDF file. A complete successful run
ends by writing `processed/manifest.json` and `processed/report.md`.

The required libraries are NumPy, xarray and netCDF4; no `globetest` import or
runtime dependency exists. On older macOS installations where newer netCDF4
releases have no compatible wheel, use
`python -m pip install --only-binary=netCDF4 -e ".[dev]"` to select an available
binary release instead of building native libraries. NumPy remains below 2 for
compatibility with the tested netCDF4 1.6.5 wheel. The manifest records Python,
library versions, NetCDF/HDF5 versions and preparation-source hashes.

## Supplied sources and compact products

| Original filename under `raw/` | Retained product under `processed/` |
| --- | --- |
| `Northern Hemisphere PCs.nc` | `north_pcs.nc`: original standardized_pc(time, mode), dates and modes 1–12 |
| `Southern Hemisphere PCs.nc` | `south_pcs.nc`: independent southern PCs on the same dates |
| `NH heat-flux regression.nc` | `north_regression.nc`: year-round coefficient(mode, latitude, longitude), latitude ≥20° |
| `SH heat-flux regression.nc` | `south_regression.nc`: southern coefficients, latitude ≤−20° |
| `ERA5 land–sea mask.nc` | `era5_ocean_mask.nc`: first native fractional mask and ocean classification |
| `Mixed-layer depth.nc` | Fixed H and source coverage in both `*_surface.nc` products |
| `SST damping.nc` | Scalar in `configs/surface_damping.toml`; calibration statistics/provenance in the manifest, no runtime spatial gamma |

The inventory in the manifest includes **all original variables**, dimensions,
coordinate bounds/order, attributes, sizes and checksums. Product entries record
source hashes, exact selections, compression, dtype policy and round-trip checks.
The report gives individual file sizes, compression savings, independent component
coverage before/after the uniform-damping change, sampled ocean areas, and scalar
calibration statistics. Reported NetCDF
savings refer to the compact **working dataset**, excluding the small JSON/Markdown
audit files. The preparation step itself retained originals and freed no original
disk space; their subsequent deliberate removal is separate from compression.

## Scientific selections

- Each hemisphere retains its own 12 unchanged standardized monthly MSLP PCs,
  January 1979–October 2026 (574 continuous months). No refitting, detrending,
  restandardisation, sign changes or combined 24-PC basis is performed.
- The intended forcing is `F' = sum(beta_k * PC_k)` independently in each
  hemisphere, in W m⁻², positive downward. The supplied coefficients are **raw
  year-round joint latent-plus-sensible turbulent heat-flux anomaly regressions**.
  They are not SST-feedback-adjusted. No intercept is included in the runtime
  forcing product; the raw intercept and reconstruction offset are audited.
  Seasonal-only products are rejected, never averaged into an annual fit.
- Runtime spatial fields use the supplied ERA5 **0.25° grid**, not the Cesium
  demonstration grid. Latitude decreases; longitude increases from 0 to 359.75°.
  +20° and −20° are included; the intervening tropical region is excluded.
- ERA5 ocean means `lsm < 0.5`. All 574 monthly classifications are verified
  identical. The first fractional field is retained, including mixed coastal
  values; tiny fraction changes are reported. The published MLD source mask is
  used only to reject invalid depth donors, not to redefine the ERA5 coastline.
- Fixed `H` is the maximum positive finite monthly climatological MLD in source
  ocean cells. This approximates late-winter depth and is **not independently
  verified late-winter H**. Each ERA5 location takes its containing 1° source cell;
  exact internal boundaries choose the north/east donor, longitude wraps, and
  ±90° use the edge cell. A source land/missing-depth donor or ERA5 land location
  stays missing. There is no interpolation, smoothing or nearest-valid filling.
- Depth products preserve valid-month counts, donor coordinates, source ocean
  classification, and minimum/total monthly profile counts (`n_obs`). These are
  coverage diagnostics; zero observations are not used to erase valid mapped
  climatological estimates. Monthly source detail remains in the raw file.
- Damping calibration selects labelled **primary**, **lag 1** (SST leads flux),
  **turbulent**, in W m⁻² K⁻¹. It uses only finite, strictly positive gamma with
  source `reliable == 1` in ERA5 ocean at centre latitudes ≥20°N or ≤−20°S. The
  estimate pools both hemispheres by sampled area; hemisphere means are not
  averaged equally. H, beta and additional sea-ice criteria do not select the
  calibration sample. The initial migration verified these values against both
  previous processed damping fields; subsequent runs reproduce them from raw.
- `input_valid` now denotes **ERA5 ocean ∩ extratropics ∩ finite positive H ∩
  all 12 finite beta**. It does not depend on local gamma, reliability, open-water
  coverage or sea ice. Source sea-ice-covered ocean is included if H/beta are
  valid. Runtime `*_surface.nc` files retain H, its coverage/donor fields and
  `input_valid` only; no gamma or damping-specific quality flags are present.
  The full original spatial damping and quality diagnostics remain unchanged
  under `raw/` for later calibration/sensitivity experiments.

## Uniform damping and geographical areas

The [baseline configuration](../configs/surface_damping.toml) contains one
provisional globally uniform effective coefficient under `[surface_damping]`.
Its numeric value is computed from the inputs, not embedded in processing or
future integration functions. See [configuration guidance](../configs/README.md)
for regeneration and future sensitivity overrides.

Areas use the exact spherical formula
`A = R² Δlongitude × |sin(north_bound) − sin(south_bound)|`, with angles in radians.
Bounds are adjacent-centre midpoints. Latitude edges are clipped at the poles;
longitude neighbours wrap periodically. Compute areas on the full native grid
before selecting hemispheres. The inclusive ±20° rule selects cell centres and
keeps the full footprint of each selected boundary cell. Ocean areas mean the
full areas of cells classified by `lsm < 0.5`, not fractional coastal weights.

The area-reporting convention uses the **6,371,229 m ECMWF/IFS sphere** described
in [ECMWF's spatial-reference documentation](https://confluence.ecmwf.int/pages/viewpage.action?pageId=78296363).
The supplied NetCDF does not declare its radius, so this is an explicit convention,
not an inferred GRIB format. The common radius cancels from the weighted mean
and area fractions; it sets the reported absolute square metres.

The manifest records source damping SHA-256, case/lag/target, exact selection,
area method/radius, code revision/source hashes, pooled and hemispheric means,
sample counts/areas, coverage fractions, and unweighted medians/percentiles.
The calibration sample is independent of the simulation mask. Global unweighted
statistics pool selected cells, rather than pooling hemisphere summaries.

This uniform coefficient simplifies spatially incomplete, reliability-filtered
extratropical estimates and applies them to a wider active ocean domain. It is
**not a uniquely correct or fully validated physical feedback constant**. It may
need calibration or sensitivity analysis. Raw turbulent regressions remain the
prescribed forcing: any overlap between their SST-dependent feedback and explicit
damping is **not independently corrected here**. There is no additional sea-ice
mask, and using this baseline over sea-ice-covered ocean is a limitation. H remains
the maximum-monthly-climatology approximation described above.

All runtime scientific floats retain their original dtype (coefficients/PCs float64,
source-derived H float32). No float64→float32 conversion or rounding is used.
Compression is lossless NetCDF4 zlib level 4 with shuffle. Binary 0/1/NaN flags
use reversible int8 storage with an explicit missing sentinel. Chunks suit
spatial tiles and monthly PC blocks; no global time-by-space forcing cube is saved.

## Runtime consumption

The scientific core independently loads a hemisphere's PC, coefficient
and H-only surface files with xarray, asserts exact time/mode/grid compatibility,
reads the scalar damping configuration and uses the documented `input_valid` mask.
Local spatial gamma is not a simulation input. Preparation and
parameter selection happen outside numerical integration. The preparation pipeline
does not integrate heat budgets, generate stochastic forcing, refit spatial
damping or communicate with the frontend.

The separate [historical experiment](../experiments/README.md) consumes these
products without modifying them. Its
[runtime loader](../src/ssta_model/data/runtime.py) validates coordinates, units,
modes and masks. Integration never opens raw spatial damping.

Implementation is in [ssta_model.data](../src/ssta_model/data/), with a thin
[entry script](../experiments/prepare_model_inputs.py). Controlled synthetic
[tests](../tests/test_model_inputs.py) run without the ignored local datasets.
