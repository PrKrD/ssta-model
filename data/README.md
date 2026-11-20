# Local scientific inputs

All raw and processed data here are Git-ignored; only this README is tracked.
The seven supplied NetCDF files are kept with their original names under `raw/`.
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

`--data-dir PATH` selects another local input directory. Initially place the exact
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
| `SST damping.nc` | Selected gamma and original quality flags in both `*_surface.nc` products |

The inventory in the manifest includes **all original variables**, dimensions,
coordinate bounds/order, attributes, sizes and checksums. Product entries record
source hashes, exact selections, compression, dtype policy and round-trip checks.
The report gives individual file sizes, compression savings, independent component
coverage and available/reliable/positive-reliable intersections. Reported NetCDF
savings refer to the compact **working dataset**, excluding the small JSON/Markdown
audit files. Originals remain retained: no original disk space is freed.

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
- Damping selects labelled **primary**, **lag 1** (SST leads flux), **turbulent**,
  in W m⁻² K⁻¹. Gamma remains provisional, signed and unfilled. Original ocean,
  open-water, reliability, negative, large, lag-sensitive and related flags are
  preserved. These flags aggregate source targets/lags; they must not be
  mistaken for flags computed solely from the selected gamma.
- `input_valid` denotes the intersection of ERA5 ocean, positive finite H,
  all 12 finite coefficients, finite gamma and source open-water support.
  Reliability and positivity are **separate** policies, with separate counts;
  no negative damping is silently removed from the physical data.

All scientific floats retain their original dtype (coefficients/PCs/gamma float64,
source-derived H float32). No float64→float32 conversion or rounding is used.
Compression is lossless NetCDF4 zlib level 4 with shuffle. Binary 0/1/NaN flags
use reversible int8 storage with an explicit missing sentinel. Chunks suit
spatial tiles and monthly PC blocks; no global time-by-space forcing cube is saved.

## Future consumption

The future scientific core can independently load a hemisphere's PC, coefficient
and surface files with xarray, assert exact time/mode/grid compatibility, and
choose an explicit validity policy using the retained flags. Preparation and
parameter selection happen outside numerical integration. The current pipeline
does not integrate heat budgets, generate stochastic forcing, recalibrate
damping or communicate with the frontend.

Implementation is in [ssta_model.data](../src/ssta_model/data/), with a thin
[entry script](../experiments/prepare_model_inputs.py). Controlled synthetic
[tests](../tests/test_model_inputs.py) run without the ignored local datasets.
