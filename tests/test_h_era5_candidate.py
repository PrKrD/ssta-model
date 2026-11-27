"""ERA5 target support, restricted polar retention and unchanged-domain audits."""

import numpy as np
import pytest
import xarray as xr

from ssta_model.analysis.h_candidate import candidate_statistics
from ssta_model.data.era5_h_candidate import retain_baseline_poles
from ssta_model.data.mld_rebuild import bilinear_depth


def test_era5_target_recomputes_support_that_old_target_excluded():
    depth = np.array([[10.0, np.nan, 30.0, 40.0], [50.0, 60.0, 70.0, 80.0]])
    counts = np.where(np.isfinite(depth), 12, 0)
    lat, lon = [-45.0, 45.0], [-135.0, -45.0, 45.0, 135.0]
    target_lat, target_lon = [-22.5, 22.5], [-180.0, -90.0, 0.0, 90.0]
    ocean = np.ones((2, 4), bool)
    old_target = ocean.copy()
    old_target[:, 1] = False
    old, _, _ = bilinear_depth(
        depth, counts, lat, lon, target_lat, target_lon, old_target
    )
    candidate, coverage, weights = bilinear_depth(
        depth, counts, lat, lon, target_lat, target_lon, ocean
    )
    assert np.isnan(np.where(ocean, old, np.nan)[:, 1]).all()
    assert np.isfinite(candidate[:, 1]).all()
    assert np.all(weights[:, 1] < 1) and np.all(coverage[:, 1] == 12)
    # Three valid corners: the missing source corner is excluded and renormalised.
    assert candidate[0, 1] == pytest.approx(
        (10 * 0.375 + 50 * 0.125 + 60 * 0.125) / 0.625
    )
    missing, _, _ = bilinear_depth(
        np.full((2, 4), np.nan),
        np.zeros((2, 4)),
        lat,
        lon,
        target_lat,
        target_lon,
        ocean,
    )
    assert np.isnan(missing).all()


def test_polar_exception_only_retains_already_active_ocean_and_never_coastal_fills():
    lat = np.array([90.0, 89.75, 89.5, 89.25])
    baseline = np.full((4, 4), 40.0)
    baseline[0] = [30, 40, 50, 60]
    ocean = np.ones((4, 4), bool)
    ocean[0, 3] = False
    active = ocean.copy()
    active[1, 0] = False
    interpolated = np.full((4, 4), 80.0)
    interpolated[:2] = np.nan
    interpolated[3, 1] = np.nan
    result, retained = retain_baseline_poles(interpolated, lat, ocean, baseline, active)
    np.testing.assert_array_equal(result[0, :3], baseline[0, :3])
    assert np.isnan(result[0, 3]) and np.isnan(result[1, 0])
    assert not retained[2:].any()
    assert result[2, 0] == 80  # 89.5 itself remains interpolated
    assert np.isnan(result[3, 1])  # no fallback at an unsupported coastal cell
    assert active[3, 1]  # unsupported active gap must remain visible to the audit
    assert np.isnan(interpolated[:2]).all()  # original input not mutated
    with pytest.raises(ValueError, match="active cells outside"):
        retain_baseline_poles(interpolated, lat, ocean, baseline, np.ones((4, 4), bool))
    southern, flag = retain_baseline_poles(interpolated, -lat, ocean, baseline, active)
    np.testing.assert_array_equal(southern, result)
    np.testing.assert_array_equal(flag, retained)


def test_coverage_audit_exposes_active_gaps_gains_and_polar_flags():
    dims = ("latitude", "longitude")
    coords = {"latitude": [90.0, 89.75, 89.5], "longitude": [0.0, 90.0, 180.0, 270.0]}
    old = np.full((3, 4), 50.0)
    old[2, 3] = np.nan
    new = old.copy()
    new[2, 3] = 60.0
    new[2, 1] = np.nan
    new[1, 2] = 55.0
    active = np.isfinite(old)
    baseline = xr.Dataset({"H": (dims, old)}, coords=coords)
    flags = np.ones((3, 4), dtype="i1")
    flags[:2] = 2
    flags[2, 1] = 0
    candidate = xr.Dataset(
        {
            "H": (dims, new),
            "era5_ocean": (dims, np.ones((3, 4), dtype="i1")),
            "baseline_input_valid": (dims, active.astype("i1")),
            "support_method": (dims, flags),
            "valid_corner_weight": (dims, (flags == 1).astype(float)),
        },
        coords=coords,
    )
    area = xr.DataArray(np.ones((3, 4)), dims=dims, coords=coords)
    result = candidate_statistics(baseline, candidate, area)
    assert result["newly_valid_H_cells"] == result["lost_valid_H_cells"] == 1
    assert result["baseline_active_cells_without_H"] == 1
    assert result["era5_ocean_without_candidate_H"] == 1
    assert result["polar_baseline_retained_cells"] == 8
    assert result["maximum_absolute_difference_m"] == 5
    assert np.isfinite(result["candidate_rms_adjacent_gradient_m_per_km"])
