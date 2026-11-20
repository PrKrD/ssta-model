"""Display aggregation and calendar checks on tiny saved-state fixtures."""

import json

import numpy as np
import pytest
import xarray as xr

from ssta_model.data.visualization import aggregate, export_visualization, tile_indices


def test_weighted_ocean_mean_missing_and_closed_boundary_membership():
    latitude = [25, 20]
    longitude = [0, 4.75, 5, 180, 359.75]
    bins = tile_indices(latitude, longitude)
    values = np.array([[2.0, 10, 4, -3, np.nan], [99, 0, -2, 1, np.nan]])
    valid = np.ones(values.shape, bool)
    valid[1, 0] = False  # Land: must not enter the partial-ocean mean.
    areas = np.ones(values.shape)
    areas[0, 1] = 3
    means, weight = aggregate(values, areas, valid, bins)
    assert means[bins[0, 0]] == 8  # (2*1 + 10*3)/4, not the unweighted 6.
    assert means[bins[1, 0]] == 0  # Valid zero survives; land 99 excluded.
    assert means[bins[0, 3]] == -3
    assert np.isnan(means[bins[0, 4]]) and weight[bins[0, 4]] == 0
    assert bins[0, 0] != bins[0, 2] and bins[0, 0] != bins[1, 0]
    np.testing.assert_array_equal(
        tile_indices([-20, -25], [180]), [[13 * 72], [13 * 72]]
    )
    np.testing.assert_array_equal(
        tile_indices([90, 85, -90], [180, -180, 175]),
        [
            [35 * 72, 35 * 72, 35 * 72 + 71],
            [35 * 72, 35 * 72, 35 * 72 + 71],
            [0, 0, 71],
        ],
    )
    assert tile_indices([20], [360])[0, 0] == tile_indices([20], [0])[0, 0]
    with pytest.raises(ValueError, match="Tropical"):
        tile_indices([19.75], [0])
    with pytest.raises(ValueError, match="area"):
        aggregate(values, areas * 0, valid, bins)


@pytest.fixture
def saved_run(tmp_path):
    months = np.arange("1979-01", "1981-01", dtype="datetime64[M]")
    times = (months + 1).astype("datetime64[ns]")
    products = {}
    for h, lat, sign in (
        ("north", [90.0, 85.0, 25.0, 20.0], 1),
        ("south", [-20.0, -25.0, -85.0, -90.0], -1),
    ):
        lon = np.array([0.0, 4.75, 5.0, 175.0, 179.75, 180.0, 185.0, 355.0, 359.75])
        shape = (len(lat), len(lon))
        mask = np.ones(shape, dtype="i1")
        mask[2, 0] = 0
        mask[2, 2] = 0  # An entire display tile has no active model cells.
        area = np.arange(1, np.prod(shape) + 1, dtype=float).reshape(shape)
        values = np.stack(
            [
                sign * np.arange(np.prod(shape), dtype=float).reshape(shape) / 10
                + i / 20
                for i in range(24)
            ]
        )
        values[:, mask == 0] = np.nan
        values[1, :2, :2] = np.nan  # Both native rows in this tile become missing.
        ds = xr.Dataset(
            {
                "sst_anomaly": (("time", "latitude", "longitude"), values),
                "input_valid": (("latitude", "longitude"), mask),
                "cell_area": (("latitude", "longitude"), area),
                "forcing_month": ("time", months.astype(str)),
                "time_bounds": (
                    ("time", "bounds"),
                    np.column_stack((months.astype("datetime64[ns]"), times)),
                ),
            },
            coords={"time": times, "latitude": lat, "longitude": lon, "bounds": [0, 1]},
            attrs={
                "configuration_json": '{"fixture":true}',
                "provenance_json": '{"historical_raw_path":"/deliberately/absent"}',
            },
        )
        ds.sst_anomaly.attrs["units"] = "K"
        ds.cell_area.attrs["units"] = "m2"
        ds.latitude.attrs["units"] = "degrees_north"
        ds.longitude.attrs["units"] = "degrees_east"
        ds.time.encoding = {
            "units": "seconds since 1970-01-01",
            "calendar": "proleptic_gregorian",
        }
        ds.time_bounds.encoding = ds.time.encoding.copy()
        ds.to_netcdf(tmp_path / f"{h}_sst.nc", engine="netcdf4")
        products[h] = ds
    return tmp_path, products


def test_export_24_frames_geometry_order_and_independent_values(saved_run):
    run, products = saved_run
    dest = run / "display.json"
    report = export_visualization(run, dest)
    raw = json.loads(dest.read_text())
    grid, seq = raw["grid"], raw["sequence"]
    assert (
        len(seq["frames"]) == 24
        and seq["units"] == "K"
        and seq["colorScale"] == "diverging"
    )
    assert seq["timestamps"][0] == "1979-02-01T00:00:00Z"
    assert seq["timestamps"][-1] == "1981-01-01T00:00:00Z"
    assert seq["frameLabels"][0] == "January 1979 — end-of-month model state"
    assert seq["frameLabels"][-1] == "December 1980 — end-of-month model state"
    assert report["maximum_sample_error_k"] < 1e-12
    cells = grid["cells"]
    assert [(c["south"], c["west"]) for c in cells] == sorted(
        (c["south"], c["west"]) for c in cells
    )
    assert all(
        c["east"] - c["west"] == 5 and c["north"] - c["south"] == 5 for c in cells
    )
    assert all(c["north"] <= -20 or c["south"] >= 20 for c in cells)
    assert not any(c["south"] == 25 and c["west"] == 5 for c in cells)
    assert all(-180 <= c["west"] < c["east"] <= 180 for c in cells)
    for i, c in enumerate(cells):
        h = "north" if c["south"] >= 20 else "south"
        ds = products[h]
        lat, lon = np.meshgrid(
            ds.latitude.values, (ds.longitude.values + 180) % 360 - 180, indexing="ij"
        )
        membership = (
            (lat >= c["south"])
            & (lat < c["north"])
            & (lon >= c["west"])
            & (lon < c["east"])
        )
        if c["north"] == 90:
            membership |= (lat == 90) & (lon >= c["west"]) & (lon < c["east"])
        if c["north"] == -20:
            membership |= (lat == -20) & (lon >= c["west"]) & (lon < c["east"])
        membership &= ds.input_valid.values == 1
        assert membership.sum() == c["nativeCellCount"]
        for month in (0, 1, 16, 23):
            values = ds.sst_anomaly.values[month]
            select = membership & np.isfinite(values)
            expected = (
                np.average(values[select], weights=ds.cell_area.values[select])
                if select.any()
                else None
            )
            assert (
                seq["frames"][month][i] == pytest.approx(expected)
                if expected is not None
                else seq["frames"][month][i] is None
            )
    assert any(v is None for v in seq["frames"][1])
    assert (
        raw["provenance"]["simulation"]["historical_raw_path"] == "/deliberately/absent"
    )
    assert "NaN" not in dest.read_text() and "Infinity" not in dest.read_text()


@pytest.mark.parametrize(
    "change", ["timestamp", "bounds", "units", "mask", "orientation", "hemisphere"]
)
def test_invalid_scientific_output_rejected(saved_run, change):
    run, products = saved_run
    ds = products["north"].copy(deep=True)
    if change == "timestamp":
        ds = ds.assign_coords(time=ds.time + np.timedelta64(1, "D"))
    if change == "bounds":
        ds.time_bounds.values[0, 0] += np.timedelta64(1, "D")
    if change == "units":
        ds.sst_anomaly.attrs["units"] = "C"
    if change == "mask":
        ds.sst_anomaly.values[0, 2, 0] = 1
    if change == "orientation":
        ds = ds.isel(latitude=slice(None, None, -1))
    if change == "hemisphere":
        ds = ds.assign_coords(latitude=[90, 85, 25, 19.75])
    ds.to_netcdf(run / "north_sst.nc", engine="netcdf4")
    with pytest.raises(ValueError):
        export_visualization(run, run / "bad.json")
