# Proposed bilinear fixed H and ocean-mask comparison

The later [ERA5-targeted candidate](h_era5_candidate.md) recomputes interpolation
with the ERA5 target mask and a restricted polar baseline exception. The original
MLD-target products documented here remain unchanged for comparison.

This preparation-only milestone adds an alternative to the existing containing-cell
H. **Neither historical SST experiment has been rerun with the alternative.** The
ERA5 mask, selected runtime surface products, damping, forcing and Cesium exports
remain unchanged. The new files are not automatically selected by any configuration.

## Source and methods

Use the reuploaded local `data/raw/mld_dr003_ref10m_v2023.nc`, the de Boyer Montégut
(2023) monthly MLD climatology, [DOI](https://doi.org/10.17882/91774). Its variables
are `mld_dr003(time,lat,lon)` in metres and `mask(lat,lon)`; source centres are
−89.5…89.5° latitude and −179.5…179.5° longitude, with twelve climatological months.
Source ocean is exactly **mask == 1**. Declared fill values decode to missing;
only positive finite monthly ocean depths contribute to maximum H. Missing months
are omitted, and unsupported source points remain missing. No profile-count
threshold is added.

The array methods adapt the inspected `globetest/backend/app/mld.py`, without a
runtime dependency on that repository:

1. Reconstruct the source-ocean mask before reducing monthly MLD.
2. Remap the mask by exact spherical rectangular overlap. Latitude overlap uses
   `sin(north)-sin(south)` and longitude overlap is periodic. A target cell is
   ocean at ≥50% source-ocean area, including ties. A 16-float64-epsilon numerical
   tolerance protects mathematical ties; this is not a geographical buffer.
3. Bilinearly interpolate **maximum monthly H**, rather than taking the maximum
   after interpolating monthly fields. Exclude invalid source-ocean corners and
   renormalise remaining positive weights. Target validity is the remapped MLD
   ocean mask, independently of ERA5. No convolution, Gaussian smoothing,
   nearest-valid search or additional filter is used.

The target coordinates come directly from the existing global ERA5 mask, retaining
its descending latitudes and 0…359.75° longitudes. Mask footprints at ±90° are
clipped to the sphere. The old interpolator rejected latitudes outside the source
centres; the current grid includes ±89.75° and ±90°. Proposed H stays **missing
beyond ±89.5°**, with no latitude extrapolation. The remapped mask still covers
those rows. This polar-support decision must be revisited before a model rerun.

## Execute and inspect

From the repository root with existing processed inputs and the reuploaded file:

```sh
python -m pip install -e ".[dev,visualization]"
python -m pytest
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 python experiments/rebuild_h_field.py
```

The command refuses existing output files or diagnostics directories. It never
calls the original multi-dataset preparation pipeline or model integration.
`--source`, `--processed`, `--output` and `--diagnostics` select explicit paths.
For a numerical reproduction without copying scientific inputs, choose a fresh
`--output` directory and a fresh `--diagnostics` directory. Generated timestamps
and binary hashes can differ; decoded numerical values/statistics must agree.

Default products, all Git-ignored:

| Product | Meaning |
|---|---|
| `data/processed/north_surface.nc`, `south_surface.nc` | Preserved containing-cell baseline on ERA5 ocean support |
| `data/processed/north_surface_h_bilinear.nc`, `south_surface_h_bilinear.nc` | Proposed float64 H on remapped MLD ocean support, with minimum contributing month count and valid-corner weight |
| `data/processed/mld_mask_remapped.nc` | Global ERA5/MLD masks, MLD overlap fraction, agreement/disagreement, four categories and spherical cell areas |
| `runs/h_rebuild_comparison/summary.json`, `report.md` | Counts, area fractions, depth/roughness comparisons and preservation/provenance audit |
| `runs/h_rebuild_comparison/global_H_comparison.png` | Current H, proposed H and common-support difference |
| `runs/h_rebuild_comparison/north_atlantic_H_detail.png` | Matching zoom to inspect interpolation and coastal support |
| `runs/h_rebuild_comparison/mask_comparison.png`, `north_atlantic_mask_detail.png` | Both masks plus both-ocean / ERA5-only / MLD-only / both-land categories |

All files record source identity/hash, variables/rules, units, grid/method,
generation time, implementation hash, code revision and software versions.
Baseline inputs are hashed before and after generation. New NetCDF products
undergo exact decoded-value/coordinate round-trip checks. `input_valid` is
deliberately absent from proposed files: future runtime-mask construction is a
separate decision, not an implicit substitution.

## Interpreting the comparison

Mask statistics report global, north/south hemispheric, extratropical and
high-latitude domains. The equator belongs to the northern hemisphere in that
partition. Cell-disagreement fractions divide by all domain cells; area fractions
are reported against both the entire domain and the union of the ocean masks.
Do not interpret cell-count fractions as area fractions near the poles.

H differences and their area-weighted statistics use common finite support.
Separate current-only/proposed-only coverage counts expose domain changes.
Adjacent RMS jumps compare identical native face pairs, including the periodic
seam; they measure roughness in metres, not a gradient per physical distance.
Both depth plots share sequential limits; differences have a separate symmetric
scale. Tropical H is omitted because the baseline contains only extratropics.

Bilinear interpolation can smooth 1° steps without adding source information or
conserving integrated heat capacity. Coastal renormalisation can use just one
valid corner and does not guarantee connectivity across a source-grid land
barrier. The coarser MLD mask and ERA5 mask differ in coastline and inland-water
definitions. A smoother field is not automatically more accurate. Inspect domain
changes, partial-month support, polar gaps and heat-capacity changes before
choosing a mask/H pair for a later controlled SST rerun.

Controlled tests cover source masks/monthly maxima, spherical overlap and ties,
polar footprints, periodic interpolation, linear-field recovery, invalid-corner
renormalisation, wholly invalid support, coordinate order, deterministic results,
mask-statistic denominators and lossless output. The actual-data comparison also
records a local parity audit against the old implementation where both support
the same latitude centres.
