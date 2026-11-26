"""Controlled MLD-mask/H rebuild; never changes the model's selected inputs.

Overlap and interpolation adapt globetest/backend/app/mld.py's array methods.
Unlike that prototype, the target may include exact poles: overlap cells are
clipped to the sphere and H outside source-centre support stays missing.
"""

import json
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import xarray as xr

from ssta_model.data.model_inputs import (
    SPATIAL,
    extratropics,
    require,
    same_grid,
    spherical_cell_areas,
)
from ssta_model.data.prepare import checksum

METHOD = "ssta_model.data.mld_rebuild"


def regular_axis(values, name, *, cyclic=False, descending=False):
    values = np.asarray(values, dtype="f8")
    require(
        values.ndim == 1 and len(values) >= 2 and np.isfinite(values).all(),
        f"Invalid {name} coordinates",
    )
    delta = np.diff(values)
    require(
        (np.all(delta > 0) or (descending and np.all(delta < 0)))
        and np.allclose(delta, delta[0], rtol=0, atol=1e-10),
        f"Expected regular monotonic {name}",
    )
    step = abs(delta[0])
    if cyclic:
        require(np.isclose(step * len(values), 360), f"Incomplete cyclic {name}")
    else:
        require(np.all(abs(values) <= 90), f"Invalid latitude {name}")
    return values, step


def source_fixed_depth(dataset):
    """Reconstruct mask==1 and maximum available positive monthly depth in metres."""
    require(
        dataset.mld_dr003.dims == ("time", "lat", "lon")
        and dataset.mask.dims == ("lat", "lon")
        and dataset.sizes["time"] == 12,
        "Expected twelve monthly MLD fields and a source mask",
    )
    for name, unit in (("lat", "degrees_north"), ("lon", "degrees_east")):
        require(dataset[name].attrs.get("unit") == unit, f"Unexpected {name} units")
    require(dataset.mld_dr003.attrs.get("unit") == "m", "MLD must be metres")
    lat, dy = regular_axis(dataset.lat.values, "source latitude")
    lon, dx = regular_axis(dataset.lon.values, "source longitude", cyclic=True)
    require(
        len(lat) == 180
        and len(lon) == 360
        and dy == dx == 1
        and np.array_equal(lat[[0, -1]], [-89.5, 89.5])
        and np.array_equal(lon[[0, -1]], [-179.5, 179.5]),
        "Expected original global 1-degree MLD centres",
    )
    ocean = dataset.mask.values == 1
    raw = dataset.mld_dr003.values.astype("f8")
    # xarray decodes the declared _FillValue to NaN before this boundary.
    valid = ocean[None] & np.isfinite(raw) & (raw > 0)
    count = valid.sum(axis=0).astype("i2")
    maximum = np.max(np.where(valid, raw, -np.inf), axis=0)
    maximum[count == 0] = np.nan
    return ocean, maximum, count


def overlap_ocean_mask(ocean, source_lat, source_lon, target_lat, target_lon):
    """Exact spherical rectangle overlap fraction and majority mask (ties ocean).

    R² and the degrees-to-radians longitude factor cancel in the fraction.
    Latitude bounds at poles are clipped, retaining target coordinate order.
    """
    sy, dy = regular_axis(source_lat, "source latitude")
    sx, dx = regular_axis(source_lon, "source longitude", cyclic=True)
    ty, ey = regular_axis(target_lat, "target latitude", descending=True)
    tx, ex = regular_axis(target_lon, "target longitude", cyclic=True)
    ocean = np.asarray(ocean)
    require(
        ocean.dtype == bool and ocean.shape == (len(sy), len(sx)), "Mask shape/type"
    )
    require(
        np.isclose(sy[0] - dy / 2, -90) and np.isclose(sy[-1] + dy / 2, 90),
        "Source mask must cover the sphere",
    )
    lower = np.maximum(np.clip(ty[:, None] - ey / 2, -90, 90), sy - dy / 2)
    upper = np.minimum(np.clip(ty[:, None] + ey / 2, -90, 90), sy + dy / 2)
    latitude = np.where(
        upper > lower, np.sin(np.deg2rad(upper)) - np.sin(np.deg2rad(lower)), 0
    )
    tx = sx[0] + (tx - sx[0]) % 360
    longitude = np.zeros((len(tx), len(sx)))
    for shift in (-360, 0, 360):
        lower = np.maximum(tx[:, None] - ex / 2, sx + shift - dx / 2)
        upper = np.minimum(tx[:, None] + ex / 2, sx + shift + dx / 2)
        longitude += np.maximum(upper - lower, 0)
    total = (
        np.sin(np.deg2rad(np.clip(ty + ey / 2, -90, 90)))
        - np.sin(np.deg2rad(np.clip(ty - ey / 2, -90, 90)))
    )[:, None] * ex
    fraction = np.clip(latitude @ ocean.astype("f8") @ longitude.T / total, 0, 1)
    # Roundoff protection for mathematical 50/50 ties, not a coastal buffer.
    return fraction, fraction >= 0.5 - 16 * np.finfo(float).eps


def bilinear_depth(depth, counts, source_lat, source_lon, target_lat, target_lon, mask):
    """Periodic bilinear H with invalid corners removed and weights renormalised.

    No interpolation beyond source latitude centres, nearest-valid searches or
    additional smoothing. Returns H, minimum contributing month count, weight.
    """
    sy, dy = regular_axis(source_lat, "source latitude")
    sx, dx = regular_axis(source_lon, "source longitude", cyclic=True)
    ty, _ = regular_axis(target_lat, "target latitude", descending=True)
    tx, _ = regular_axis(target_lon, "target longitude", cyclic=True)
    depth, counts, mask = np.asarray(depth), np.asarray(counts), np.asarray(mask)
    require(
        depth.shape == counts.shape == (len(sy), len(sx))
        and mask.shape == (len(ty), len(tx))
        and mask.dtype == bool,
        "Interpolation field/mask shapes differ",
    )
    xp = ((tx - sx[0]) % 360) / dx
    x0 = np.floor(xp).astype(int) % len(sx)
    fx = (xp - np.floor(xp))[None, :]
    yp = np.clip((ty - sy[0]) / dy, 0, len(sy) - 1)
    y0 = np.floor(yp).astype(int)
    fy = (yp - y0)[:, None]
    y1 = np.minimum(y0 + 1, len(sy) - 1)
    numerator = np.zeros(mask.shape)
    weight = np.zeros(mask.shape)
    coverage = np.full(mask.shape, 13, dtype="i2")
    for y, x, w in (
        (y0, x0, (1 - fy) * (1 - fx)),
        (y0, (x0 + 1) % len(sx), (1 - fy) * fx),
        (y1, x0, fy * (1 - fx)),
        (y1, (x0 + 1) % len(sx), fy * fx),
    ):
        value = depth[np.ix_(y, x)]
        count = counts[np.ix_(y, x)]
        valid = np.isfinite(value) & (value > 0) & (count > 0) & (count <= 12) & (w > 0)
        numerator += np.where(valid, value, 0) * w
        weight += np.where(valid, w, 0)
        coverage = np.where(valid, np.minimum(coverage, count), coverage)
    valid = mask & (ty[:, None] >= sy[0]) & (ty[:, None] <= sy[-1]) & (weight > 0)
    result = np.full(mask.shape, np.nan)
    np.divide(numerator, weight, out=result, where=valid)
    coverage[~valid] = 0
    return result, coverage, np.where(valid, weight, 0)


def mask_statistics(era5, mld, area, select):
    """Counts plus area fractions; denominators are explicit and reproducible."""
    different = (era5 != mld) & select
    union = (era5 | mld) & select
    return {
        "cells": int(select.sum()),
        "era5_ocean_cells": int((era5 & select).sum()),
        "mld_ocean_cells": int((mld & select).sum()),
        "both_ocean_cells": int((era5 & mld & select).sum()),
        "era5_only_cells": int((era5 & ~mld & select).sum()),
        "mld_only_cells": int((mld & ~era5 & select).sum()),
        "disagreement_cells": int(different.sum()),
        "disagreement_cell_fraction": float(different.sum() / select.sum()),
        "disagreement_area_m2": float(area[different].sum()),
        "disagreement_domain_area_fraction": float(
            area[different].sum() / area[select].sum()
        ),
        "disagreement_union_ocean_area_fraction": float(
            area[different].sum() / area[union].sum()
        ),
    }


def rebuild_h(source, processed, diagnostics, output=None):
    """Write separate proposed products, static diagnostics and source-preservation audit."""
    from ssta_model.analysis.h_comparison import (
        compare_depths,
        plot_comparison,
        write_report,
    )

    source, processed, diagnostics = map(Path, (source, processed, diagnostics))
    output = processed if output is None else Path(output)
    outputs = [output / f"{h}_surface_h_bilinear.nc" for h in ("north", "south")]
    mask_path = output / "mld_mask_remapped.nc"
    require(
        not any(p.exists() for p in [*outputs, mask_path]),
        "Rebuild outputs already exist",
    )
    require(not diagnostics.exists(), "Diagnostics directory already exists")
    protected = [
        source,
        *sorted(processed.glob("*.nc")),
        *sorted(processed.glob("*.json")),
    ]
    before = {str(p): checksum(p) for p in protected}
    with (
        xr.open_dataset(source, decode_times=False) as raw,
        xr.open_dataset(processed / "era5_ocean_mask.nc") as target,
    ):
        ocean, fixed, counts = source_fixed_depth(raw)
        lat, lon = target.latitude.values, target.longitude.values
        require(
            np.all(np.diff(lat) == -0.25) and np.all(np.diff(lon) == 0.25),
            "Expected current 0.25-degree target",
        )
        require(np.isin(target.ocean, [0, 1]).all(), "Invalid ERA5 mask values")
        fraction, old = overlap_ocean_mask(
            ocean, raw.lat.values, raw.lon.values, lat, lon
        )
        depth, coverage, weight = bilinear_depth(
            fixed, counts, raw.lat.values, raw.lon.values, lat, lon, old
        )
        era5 = target.ocean.values == 1
        area = spherical_cell_areas(target).values
        attrs = {
            "prepared_by": METHOD,
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "source_file": str(source),
            "source_sha256": before[str(source)],
            "source_variables": "mld_dr003(time,lat,lon), mask(lat,lon)",
            "source_mask_rule": "mask == 1",
            "source_product": "de Boyer Montégut (2023), mld_dr003_ref10m_v2023.nc; https://doi.org/10.17882/91774",
            "fixed_depth": "Maximum of available positive finite monthly climatological MLD in source ocean; no n_obs threshold",
            "target_grid": "Existing native ERA5 centres, 0.25 degrees; original coordinate order retained",
            "mask_regridding": "Exact spherical overlap-area fraction >= 0.5; mathematical ties ocean (16 float64 eps roundoff tolerance); longitude periodic; polar bounds clipped",
            "depth_regridding": "Periodic mask-aware bilinear of fixed H; invalid corners excluded, remaining weights renormalised; no extra filtering",
            "polar_policy": "H missing outside source-centre latitudes [-89.5,89.5]; mask still remapped to poles; no latitude extrapolation",
            "status": "Proposed comparison only; no simulation rerun; ERA5 mask and baseline H unchanged; not a drop-in runtime surface product",
            "code_revision": subprocess.run(
                ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
            ).stdout.strip(),
            "implementation_sha256": json.dumps(
                {str(Path(__file__)): checksum(Path(__file__))}, sort_keys=True
            ),
            "versions": json.dumps(
                {
                    "python": platform.python_version(),
                    "numpy": np.__version__,
                    "xarray": xr.__version__,
                }
            ),
        }
        coords = {name: target[name].copy() for name in SPATIAL}
        proposed = xr.Dataset(
            {
                "H": (SPATIAL, depth, {"units": "m"}),
                "contributing_month_count_min": (SPATIAL, coverage, {"units": "1"}),
                "valid_corner_weight": (SPATIAL, weight, {"units": "1"}),
                "mld_ocean": (SPATIAL, old.astype("i1"), {"units": "1"}),
            },
            coords=coords,
            attrs=attrs,
        )
        # Four categories retain both disagreement directions, not a preferred mask.
        category = era5.astype("i1") + 2 * old.astype("i1")
        masks = xr.Dataset(
            {
                "era5_ocean": (SPATIAL, era5.astype("i1")),
                "mld_ocean": (SPATIAL, old.astype("i1")),
                "mld_ocean_fraction": (SPATIAL, fraction),
                "agreement": (SPATIAL, (era5 == old).astype("i1")),
                "disagreement": (SPATIAL, (era5 != old).astype("i1")),
                "mask_category": (
                    SPATIAL,
                    category,
                    {
                        "flag_values": np.arange(4, dtype="i1"),
                        "flag_meanings": "both_land era5_only mld_only both_ocean",
                    },
                ),
                "cell_area": (SPATIAL, area, {"units": "m2"}),
            },
            coords=coords,
            attrs=attrs,
        )
        for variable in masks.data_vars.values():
            variable.attrs.setdefault("units", "1")
        baseline = []
        for h in ("north", "south"):
            with xr.open_dataset(processed / f"{h}_surface.nc") as ds:
                same_grid(ds, extratropics(proposed, h))
                baseline.append(ds.H.load())
        report = {
            "provenance": attrs,
            "source_ocean_cells": int(ocean.sum()),
            "source_supported_H_cells": int(np.isfinite(fixed).sum()),
            "mask_statistics": {},
            "H_comparison": {},
        }
        for label, selection in {
            "global": np.ones(old.shape, bool),
            "north_hemisphere": np.broadcast_to(lat[:, None] >= 0, old.shape),
            "south_hemisphere": np.broadcast_to(lat[:, None] < 0, old.shape),
            "north_extratropics": np.broadcast_to(lat[:, None] >= 20, old.shape),
            "south_extratropics": np.broadcast_to(lat[:, None] <= -20, old.shape),
            "high_latitudes_abs_ge_60": np.broadcast_to(
                abs(lat[:, None]) >= 60, old.shape
            ),
        }.items():
            report["mask_statistics"][label] = mask_statistics(
                era5, old, area, selection
            )
        diagnostics.mkdir(parents=True)
        output.mkdir(parents=True, exist_ok=True)
        for h, path, current in zip(("north", "south"), outputs, baseline):
            product = extratropics(proposed, h)
            product.attrs = {
                **attrs,
                "hemisphere": h,
                "baseline_file": str(processed / f"{h}_surface.nc"),
            }
            report["H_comparison"][h] = compare_depths(
                current, product.H, extratropics(masks, h).cell_area
            )
            save_product(product, path)
        save_product(masks, mask_path)
        plot_comparison(baseline, proposed, masks, diagnostics)
    for path, digest in before.items():
        require(checksum(Path(path)) == digest, f"Preserved input changed: {path}")
    report["preserved_sha256"] = before
    report["products"] = {str(p): checksum(p) for p in [*outputs, mask_path]}
    (diagnostics / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
    write_report(report, diagnostics)
    return report


def save_product(dataset, path):
    """Write a new compressed product and verify exact decoded values/coordinates."""
    require(not path.exists(), f"Refusing to overwrite {path}")
    encoding = {
        name: {"zlib": True, "complevel": 4, "shuffle": True, "_FillValue": None}
        for name in dataset.data_vars
    }
    dataset.to_netcdf(path, engine="netcdf4", encoding=encoding)
    with xr.open_dataset(path) as restored:
        xr.testing.assert_equal(dataset, restored)
