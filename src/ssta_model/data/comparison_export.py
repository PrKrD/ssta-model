"""Shared half-degree centre binning and paired numerical aggregation."""

import numpy as np

from .model_inputs import require


def comparison_bins(latitude, longitude):
    """Half-degree centre bins, with closed southern and polar domain edges."""
    lat = np.asarray(latitude)
    lon = (np.asarray(longitude) + 180) % 360 - 180
    require(
        np.all(np.isfinite(lat) & (abs(lat) <= 90) & (abs(lat) >= 20)),
        "Invalid extratropical latitude",
    )
    require(np.isfinite(lon).all(), "Invalid longitude")
    rows = np.minimum(np.floor((lat + 90) * 2).astype(int), 359)
    rows[lat == -20] = 139
    cols = np.floor((lon + 180) * 2).astype(int)
    return rows[:, None] * 720 + cols[None, :]


def aggregate_pair(model, era, area, valid, bins):
    """Both layers and Model−ERA5 use exactly the same finite native ocean support."""
    use = valid & np.isfinite(model) & np.isfinite(era)
    require(np.all(np.isfinite(area[use]) & (area[use] > 0)), "Invalid native areas")
    weights = np.bincount(bins[use], weights=area[use], minlength=259200)
    result = []
    for values in (model, era):
        total = np.bincount(
            bins[use], weights=values[use] * area[use], minlength=259200
        )
        means = np.full(259200, np.nan)
        np.divide(total, weights, out=means, where=weights > 0)
        result.append(means)
    return np.stack([*result, result[0] - result[1]])


def aggregate_fields(fields, area, valid, bins):
    """One common finite support for every supplied field, including difference signs."""
    use = valid & np.logical_and.reduce([np.isfinite(f) for f in fields])
    require(np.all(np.isfinite(area[use]) & (area[use] > 0)), "Invalid display areas")
    weight = np.bincount(bins[use], weights=area[use], minlength=259200)
    result = []
    for field in fields:
        total = np.bincount(bins[use], weights=field[use] * area[use], minlength=259200)
        value = np.full(259200, np.nan)
        np.divide(total, weight, out=value, where=weight > 0)
        result.append(value)
    return np.stack(result)
