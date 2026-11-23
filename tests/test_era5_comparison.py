"""Small controlled references for climatology, paired skill and geographic aggregates."""

import json

import numpy as np
import pytest
import xarray as xr

from ssta_model.analysis.era5_comparison import (
    aligned_months,
    correlation,
    paired_statistics,
    region_mask,
)
from ssta_model.data.comparison_export import aggregate_pair, comparison_bins
from ssta_model.data.era5 import inspect_sst, monthly_anomalies, prepare_era5


def test_calendar_climatology_keeps_warming_missing_and_ocean_mask():
    months = np.arange("1979-01", "1981-01", dtype="datetime64[M]")
    values = (
        np.broadcast_to(
            (np.arange(24) % 12 + 2 * (np.arange(24) // 12))[:, None, None], (24, 1, 3)
        )
        .astype(float)
        .copy()
    )
    values[0, 0, 1] = np.nan
    a, c, n = monthly_anomalies(
        values, months, np.ones(24, bool), np.array([[True, True, False]])
    )
    np.testing.assert_array_equal(a[:12, 0, 0], -np.ones(12))
    np.testing.assert_array_equal(a[12:, 0, 0], np.ones(12))
    assert c[0, 0, 0] == 1 and n[0, 0, 0] == 2
    assert np.isnan(a[0, 0, 1]) and a[12, 0, 1] == 0 and n[0, 0, 1] == 1
    assert np.isnan(a[:, :, 2]).all() and np.isnan(c[:, :, 2]).all()


def test_metadata_identification_units_alignment_and_saved_products(tmp_path):
    processed = tmp_path / "processed"
    processed.mkdir()
    months = np.arange("1979-01", "1981-01", dtype="datetime64[M]").astype(
        "datetime64[ns]"
    )
    lat = [40.0, 20.0, 0.0, -20.0, -40.0]
    lon = [0.0, 90.0, 180.0, 270.0]
    mask = xr.Dataset(
        {"ocean": (("latitude", "longitude"), np.ones((5, 4), dtype="i1"))},
        coords={"latitude": lat, "longitude": lon},
    )
    mask.latitude.attrs["units"] = "degrees_north"
    mask.longitude.attrs["units"] = "degrees_east"
    mask.ocean.values[0, 0] = 0
    mask.to_netcdf(processed / "era5_ocean_mask.nc", engine="netcdf4")
    xr.Dataset(coords={"time": months}).to_netcdf(
        processed / "north_pcs.nc", engine="netcdf4"
    )
    values = (
        np.broadcast_to(
            (np.arange(24) % 12 + np.arange(24) // 12)[:, None, None], (24, 5, 4)
        )
        .astype("f4")
        .copy()
    )
    values[:, 4, 3] = np.nan
    source = xr.Dataset(
        {"unusual_temperature_name": (("valid_time", "latitude", "longitude"), values)},
        coords={"valid_time": months, "latitude": lat, "longitude": lon},
    )
    source.unusual_temperature_name.attrs = {
        "standard_name": "sea_surface_temperature",
        "units": "degC",
    }
    path = tmp_path / "sst.nc"
    source.to_netcdf(path, engine="netcdf4")
    metadata = prepare_era5(path, processed)
    assert (
        metadata["climatology_years"] == [1979, 1980]
        and metadata["source_variable"] == "unusual_temperature_name"
    )
    with xr.open_dataset(processed / "north_era5_ssta.nc") as result:
        assert (
            result.sst_anomaly.attrs["units"]
            == result.sst_climatology.attrs["units"]
            == "K"
        )
        assert result.sst_climatology.values[0, 1, 1] == pytest.approx(273.65)
        assert result.sst_anomaly.values[0, 1, 1] == pytest.approx(-0.5)
        assert np.isnan(result.sst_anomaly.values[:, 0, 0]).all()
        np.testing.assert_array_equal(result.latitude, [40, 20])
        assert json.loads(result.attrs["provenance_json"])["regridding"].startswith(
            "none"
        )
    with xr.open_dataset(processed / "south_era5_ssta.nc") as result:
        assert np.isnan(result.sst_anomaly.values[:, 1, 3]).all()
    with pytest.raises(ValueError, match="coordinates differ"):
        inspect_sst(source, mask.assign_coords(longitude=mask.longitude + 0.25))
    with pytest.raises(ValueError, match="continuous"):
        inspect_sst(source.isel(valid_time=[0, 2, 3]), mask)


def test_common_ocean_metrics_and_temporal_correlation():
    m = np.array([1.0, 3, 100, np.nan])
    e = np.array([0.0, 1, np.nan, 4])
    area = np.array([1.0, 3, 10, 100])
    r = paired_statistics(m, e, area, np.array([True, True, True, True]))
    assert r["valid_cells"] == 2 and r["rmse_k"] == pytest.approx(np.sqrt(3.25))
    assert r["bias_k"] == 1.75 and r["model_mean_k"] == 2.5 and r["era5_mean_k"] == 0.75
    assert r["spatial_correlation"] == pytest.approx(1)
    assert r["model_std_k"] == 1 and r["era5_std_k"] == 0.5
    assert r["difference_minimum_k"] == 1
    assert correlation([1, 2, np.nan, 3], [3, 2, 100, 1]) == pytest.approx(-1)
    assert correlation([1, 1], [2, 3]) is None
    assert paired_statistics(m, e, area, np.zeros(4, bool)) == {"valid_cells": 0}


def test_month_labels_not_end_boundaries_and_initial_state_exclusion():
    model = xr.Dataset(
        {"forcing_month": ("time", ["1979-01", "1979-02"])},
        coords={"time": np.array(["1979-02-01", "1979-03-01"], dtype="datetime64[ns]")},
        attrs={"initial_month": "1979-01"},
    )
    era = xr.Dataset(
        coords={"time": np.array(["1979-01-01", "1979-02-01"], dtype="datetime64[ns]")}
    )
    assert aligned_months(model, era) == [(1, 1, "1979-02")]
    with pytest.raises(ValueError, match="boundary"):
        aligned_months(
            model.assign_coords(time=model.time - np.timedelta64(31, "D")), era
        )
    with pytest.raises(ValueError, match="missing"):
        aligned_months(model, era.isel(time=[0]))


def test_half_degree_coordinates_partial_ocean_and_common_support_difference():
    bins = comparison_bins([20.25, 20.0, -20.0, -90.0], [0.0, 0.25, 180.0, 359.75])
    assert bins[0, 0] == bins[1, 0] and bins[0, 0] - 1 == bins[0, 3]
    assert bins[0, 2] % 720 == 0
    assert bins[2, 0] // 720 == 139 and bins[3, 0] // 720 == 0
    m = np.array([[1.0, 5], [3, 100]])
    e = np.array([[0.0, 2], [1, np.nan]])
    a = np.array([[1.0, 3], [2, 100.0]])
    mask = np.array([[True, True], [False, True]])
    pair = aggregate_pair(m, e, a, mask, np.zeros((2, 2), dtype=int))
    np.testing.assert_allclose(pair[:, 0], [4.0, 1.5, 2.5])
    assert np.isnan(pair[:, 1:]).all()
    grid = xr.Dataset(
        coords={
            "latitude": [65.0, 20.0],
            "longitude": [120.0, 179.0, 180.0, 250.0, 260.0],
        }
    )
    region = region_mask(grid, ("north", 20, 65, 120, -100))
    np.testing.assert_array_equal(region, [[True, True, True, True, False]] * 2)
