"""Primary-only display export, with controlled weighted values and missing support."""

import json

import numpy as np
import pytest
import xarray as xr

from ssta_model.data.historical_export import export_historical
from ssta_model.data.prepare import checksum


@pytest.fixture
def saved_primary(tmp_path):
    run, processed = tmp_path / "primary", tmp_path / "processed"
    run.mkdir()
    processed.mkdir()
    for h, latitude in (("north", 20.25), ("south", -20.25)):
        coords = {"latitude": [latitude], "longitude": [0, 0.25, 1, 2]}
        depth = np.array([[50.0, 100, np.nan, 150]])
        d = xr.Dataset(
            {
                "H": (("latitude", "longitude"), depth),
                "cell_area": (("latitude", "longitude"), [[1.0, 3, 2, 4]]),
                "input_valid": (("latitude", "longitude"), [[1, 1, 0, 0]]),
                "initial_sst_anomaly": (
                    ("latitude", "longitude"),
                    [[1.0, 5, np.nan, np.nan]],
                ),
                "sst_anomaly": (
                    ("time", "latitude", "longitude"),
                    [[[2.0, 6, np.nan, np.nan]]],
                ),
                "forcing_month": ("time", ["1979-02"]),
            },
            coords={**coords, "time": np.array(["1979-03-01"], dtype="datetime64[ns]")},
            attrs={
                "initial_month": "1979-01",
                "initial_time": "1979-02-01T00:00:00Z",
                "configuration_json": json.dumps(
                    {
                        "mixed_layer_depth": {"variant": "era5_bilinear"},
                        "physics": {"horizontal_diffusion": True},
                    }
                ),
            },
        )
        d.H.attrs["units"] = "m"
        d.sst_anomaly.attrs["units"] = "K"
        d.to_netcdf(run / f"{h}_sst.nc")
        c = d[["H"]]
        c.to_netcdf(processed / f"{h}_surface_h_era5_bilinear.nc")
        original = c.copy(deep=True)
        original.H.values[:] = [[40, 80, 60, 150]]
        original.to_netcdf(processed / f"{h}_surface.nc")
        era = xr.Dataset(
            {
                "sst_anomaly": (
                    ("time", "latitude", "longitude"),
                    [[[0.0, 2, np.nan, 10]], [[1.0, np.nan, np.nan, 10]]],
                )
            },
            coords={
                **coords,
                "time": np.array(["1979-01-01", "1979-02-01"], dtype="datetime64[ns]"),
            },
        )
        era.sst_anomaly.attrs["units"] = "K"
        era.to_netcdf(processed / f"{h}_era5_ssta.nc")
    return run, processed


def test_primary_export_needs_no_retired_runs_or_previous_manifest(
    saved_primary, tmp_path
):
    run, processed = saved_primary
    hashes = {
        p: checksum(p) for folder in (run, processed) for p in folder.glob("*.nc")
    }
    destination = tmp_path / "display"
    report = export_historical(run, processed, destination)
    manifest = json.loads((destination / "manifest.json").read_text())
    assert manifest["format"] == "sst-comparison-f32-v4"
    assert manifest["months"] == ["1979-01", "1979-02"]
    assert manifest["timestamps"] == ["1979-02-01T00:00:00Z", "1979-03-01T00:00:00Z"]
    assert report["months"] == 2 and report["cells"] == 6
    assert report["monthly_binary_bytes"] == 2 * 6 * 2 * 4
    assert set(manifest["populations"]) == {"sst", "difference", "depth"}
    first = np.fromfile(
        destination / manifest["frames"][0]["file"], dtype="<f4"
    ).reshape(2, 6)
    second = np.fromfile(
        destination / manifest["frames"][1]["file"], dtype="<f4"
    ).reshape(2, 6)
    # One shared finite area mask; ERA5's second-corner gap also excludes model there.
    np.testing.assert_array_equal(first[:, [0, 3]], [[4, 4], [1.5, 1.5]])
    np.testing.assert_array_equal(second[:, [0, 3]], [[2, 2], [1, 1]])
    assert np.isnan(first[:, [1, 2, 4, 5]]).all()
    np.testing.assert_array_equal(first[0, [0, 3]] - first[1, [0, 3]], [2.5, 2.5])
    depth = np.fromfile(destination / "depth.bin", dtype="<f4")
    np.testing.assert_array_equal(depth[[0, 2, 3, 5]], [87.5, 150, 87.5, 150])
    assert np.isnan(
        depth[[1, 4]]
    ).all()  # Stable legacy geometry does not fill missing H.
    assert report["maximum_aggregation_error_k"] == 0
    assert not (destination / "depth_original.bin").exists()
    assert all(checksum(p) == digest for p, digest in hashes.items())
    assert set(manifest["source_sha256"]) == {str(p) for p in hashes}
    with pytest.raises(ValueError, match="existing assets are protected"):
        export_historical(run, processed, destination)


def test_export_rejects_depth_inconsistent_with_integrated_model(
    saved_primary, tmp_path
):
    run, processed = saved_primary
    path = processed / "north_surface_h_era5_bilinear.nc"
    with xr.open_dataset(path) as data:
        bad = data.load()
    bad.H.values[0, 0] += 1
    bad.to_netcdf(path, mode="w")
    with pytest.raises(ValueError, match="differs from integrated H"):
        export_historical(run, processed, tmp_path / "bad")
