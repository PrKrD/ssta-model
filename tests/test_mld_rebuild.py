"""Small analytical references for the controlled H alternative; no SST runs."""

import numpy as np
import pytest
import xarray as xr

from ssta_model.data.mld_rebuild import (
    bilinear_depth,
    mask_statistics,
    overlap_ocean_mask,
    save_product,
    source_fixed_depth,
)


def source_dataset():
    dataset = xr.Dataset(
        {
            "mld_dr003": (("time", "lat", "lon"), np.full((12, 180, 360), 20.0)),
            "mask": (("lat", "lon"), np.ones((180, 360), dtype="i2")),
        },
        coords={
            "time": np.arange(12),
            "lat": np.arange(-89.5, 90),
            "lon": np.arange(-179.5, 180),
        },
    )
    dataset.lat.attrs["unit"] = "degrees_north"
    dataset.lon.attrs["unit"] = "degrees_east"
    dataset.mld_dr003.attrs["unit"] = "m"
    return dataset


def test_source_mask_maximum_partial_months_and_decoded_fill_values(tmp_path):
    source = source_dataset()
    source["mask"].values[0, :3] = [0, 2, -1]
    source.mld_dr003.values[:, 1, 0] = np.nan
    source.mld_dr003.values[:3, 1, 1] = [30, 40, -1]
    source.mld_dr003.values[3:, 1, 1] = np.nan
    path = tmp_path / "source.nc"
    source.to_netcdf(path, encoding={"mld_dr003": {"_FillValue": 999999.0}})
    with xr.open_dataset(path) as decoded:
        ocean, depth, count = source_fixed_depth(decoded)
    assert not ocean[0, :3].any() and np.isnan(depth[0, :3]).all()
    assert np.isnan(depth[1, 0]) and count[1, 0] == 0
    assert depth[1, 1] == 40 and count[1, 1] == 2
    assert depth[2, 2] == 20 and count[2, 2] == 12
    with pytest.raises(ValueError, match="twelve"):
        source_fixed_depth(source.isel(time=slice(0, 11)))


def test_spherical_overlap_ties_periodic_seam_and_polar_footprints():
    slat = [-45, 45]
    slon = [-135, -45, 45, 135]
    source = np.array([[True, False, False, False]] * 2)
    tlat = np.array([90, 45, 0, -45, -90])
    tlon = np.arange(-180, 180, 45)
    fraction, ocean = overlap_ocean_mask(source, slat, slon, tlat, tlon)
    assert np.all(fraction[:, tlon == -135] == 1)
    np.testing.assert_allclose(fraction[:, tlon == -90], 0.5)
    assert ocean[:, tlon == -90].all() and ocean[:, tlon == -180].all()
    assert not ocean[:, tlon == -45].any()
    # A target straddling the equator equally in sine(latitude) has half coverage.
    fraction, _ = overlap_ocean_mask(
        np.array([[True] * 4, [False] * 4]), slat, slon, tlat, tlon
    )
    np.testing.assert_allclose(fraction[2], 0.5)
    assert np.all(fraction[0] == 0) and np.all(fraction[-1] == 1)
    # Off-equator overlap must use sine differences, not flat latitude fractions.
    fraction, _ = overlap_ocean_mask(
        np.array([[True] * 4, [False] * 4]), slat, slon, [-5, 10, 25], tlon
    )
    expected = (np.sin(np.deg2rad(2.5)) - np.sin(0)) / (
        np.sin(np.deg2rad(2.5)) - np.sin(np.deg2rad(-12.5))
    )
    np.testing.assert_allclose(fraction[0], 1 - expected)


def test_bilinear_known_field_centres_and_longitude_periodicity():
    sy = np.array([-45.0, 45.0])
    sx = np.array([-135.0, -45.0, 45.0, 135.0])
    source = 1000 + sy[:, None] + sx[None, :]
    counts = np.full(source.shape, 12)
    ty, tx = np.array([-22.5, 22.5]), np.arange(-180.0, 180, 45)
    mask = np.ones((2, 8), bool)
    result, coverage, weight = bilinear_depth(source, counts, sy, sx, ty, tx, mask)
    np.testing.assert_allclose(result[:, 1:], 1000 + ty[:, None] + tx[None, 1:])
    np.testing.assert_allclose(result[:, 0], 1000 + ty)
    assert np.all(coverage == 12) and np.all(weight == 1)
    equivalent, _, _ = bilinear_depth(source, counts, sy, sx, ty, tx + 360, mask)
    np.testing.assert_array_equal(result, equivalent)
    exact, _, _ = bilinear_depth(
        source, counts, sy, sx, sy, sx, np.ones(source.shape, bool)
    )
    np.testing.assert_array_equal(exact, source)


def test_invalid_corner_weights_are_renormalised_no_wholly_invalid_fill():
    sy, sx = [-45, 45], [-135, -45, 45, 135]
    source = np.array([[10, np.nan, np.nan, 40], [50, 60, np.nan, 80]])
    counts = np.array([[12, 0, 0, 12], [9, 11, 0, 12]])
    target_lat, target_lon = [-90, 0, 90], [-180, -90, 0, 90]
    mask = np.ones((3, 4), bool)
    result, coverage, weight = bilinear_depth(
        source, counts, sy, sx, target_lat, target_lon, mask
    )
    assert result[1, 1] == 40 and coverage[1, 1] == 9 and weight[1, 1] == 0.75
    assert np.isnan(result[[0, 2]]).all()  # unsupported polar latitude centres
    assert np.all(coverage[[0, 2]] == 0)
    mask[1] = False
    result, _, _ = bilinear_depth(source, counts, sy, sx, target_lat, target_lon, mask)
    assert np.isnan(result).all()
    source[:] = np.nan
    mask[:] = True
    result, coverage, weight = bilinear_depth(
        source, counts, sy, sx, target_lat, target_lon, mask
    )
    assert np.isnan(result).all() and np.all(coverage == 0) and np.all(weight == 0)


def test_quarter_degree_shape_coordinate_order_and_reproducibility():
    sy, sx = np.arange(-89.5, 90), np.arange(-179.5, 180)
    ty, tx = np.array([20.5, 20.25, 20]), np.arange(0.0, 360, 0.25)
    fraction, mask = overlap_ocean_mask(np.ones((180, 360), bool), sy, sx, ty, tx)
    np.testing.assert_allclose(fraction, 1)
    source = np.broadcast_to(100 + sy[:, None], (180, 360))
    first = bilinear_depth(source, np.full(source.shape, 12), sy, sx, ty, tx, mask)
    second = bilinear_depth(source, np.full(source.shape, 12), sy, sx, ty, tx, mask)
    assert first[0].shape == (3, 1440)
    np.testing.assert_allclose(first[0], np.broadcast_to(100 + ty[:, None], (3, 1440)))
    for a, b in zip(first, second):
        np.testing.assert_array_equal(a, b)
    with pytest.raises(ValueError, match="shapes"):
        bilinear_depth(source, np.ones((2, 2)), sy, sx, ty, tx, mask)


def test_mask_statistics_denominators_and_product_roundtrip(tmp_path):
    era5 = np.array([[True, True], [False, False]])
    mld = np.array([[True, False], [True, False]])
    area = np.array([[1.0, 2.0], [3.0, 4.0]])
    stats = mask_statistics(era5, mld, area, np.ones((2, 2), bool))
    assert stats["era5_ocean_cells"] == stats["mld_ocean_cells"] == 2
    assert (
        stats["disagreement_cells"] == 2 and stats["disagreement_cell_fraction"] == 0.5
    )
    assert stats["disagreement_domain_area_fraction"] == 0.5
    assert stats["disagreement_union_ocean_area_fraction"] == 5 / 6
    assert stats == mask_statistics(era5, mld, area, np.ones((2, 2), bool))
    dataset = xr.Dataset(
        {"H": (("latitude", "longitude"), [[20.0, np.nan], [50.0, 80.0]])},
        coords={"latitude": [20.25, 20], "longitude": [0.0, 0.25]},
    )
    path = tmp_path / "proposed.nc"
    save_product(dataset, path)
    with xr.open_dataset(path) as restored:
        xr.testing.assert_equal(dataset, restored)
    with pytest.raises(ValueError, match="overwrite"):
        save_product(dataset, path)
