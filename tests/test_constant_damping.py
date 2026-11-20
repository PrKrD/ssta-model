"""Geometry, calibration and the gamma-independent runtime mask on controlled grids."""

import tomllib

import numpy as np
import pytest
import xarray as xr

from ssta_model.data.model_inputs import (
    constant_damping_statistics,
    extratropics,
    simulation_mask,
    spherical_cell_areas,
)
from ssta_model.data.prepare import checksum, runtime_coverage, write_damping_config


def grid(latitude, longitude):
    return xr.Dataset(coords={"latitude": latitude, "longitude": longitude})


def test_spherical_areas_integrate_to_whole_sphere_and_polar_caps():
    source = grid([-90.0, 0.0, 90.0], [0.0, 90.0, 180.0, 270.0])
    radius = 2.0
    areas = spherical_cell_areas(source, radius)
    assert areas.attrs["units"] == "m2"
    assert float(areas.sum()) == pytest.approx(4 * np.pi * radius**2)
    assert areas.values[1, 0] == pytest.approx(radius**2 * np.pi / np.sqrt(2))
    assert areas.values[0, 0] == pytest.approx(
        radius**2 * np.pi / 2 * (1 - np.sin(np.pi / 4))
    )
    assert np.all(areas.values > 0)
    np.testing.assert_allclose(areas.values[0], areas.values[-1])
    reversed_grid = source.isel(latitude=slice(None, None, -1))
    np.testing.assert_allclose(
        spherical_cell_areas(reversed_grid, radius),
        areas.isel(latitude=slice(None, None, -1)),
    )


def test_periodic_nonuniform_longitudes_use_both_neighbours_and_reject_bad_grids():
    source = grid([-45.0, 45.0], [0.0, 60.0, 180.0])
    areas = spherical_cell_areas(source, 1)
    # Periodic gaps are 60°, 120°, 180°: widths are 120°, 90°, 150°.
    np.testing.assert_allclose(areas.values[0], np.deg2rad([120.0, 90.0, 150.0]))
    assert float(areas.sum()) == pytest.approx(4 * np.pi)
    for invalid in [
        grid([-45.0, 45.0], [0.0, 360.0]),
        grid([0.0, 0.0], [0.0, 180.0]),
        grid([-91.0, 45.0], [0.0, 180.0]),
    ]:
        with pytest.raises(ValueError):
            spherical_cell_areas(invalid)
    with pytest.raises(ValueError, match="radius"):
        spherical_cell_areas(source, 0)


@pytest.fixture
def sample():
    ocean = grid([90.0, 60.0, 20.0, 0.0, -20.0, -60.0, -90.0], [0.0, 180.0])
    ocean["ocean"] = (("latitude", "longitude"), np.ones((7, 2), dtype="i1"))
    fields = {}
    for hemisphere in ("north", "south"):
        domain = extratropics(ocean, hemisphere)
        ds = domain.drop_vars("ocean").copy()
        ds["gamma"] = (("latitude", "longitude"), np.full((3, 2), np.nan))
        ds["reliable"] = (("latitude", "longitude"), np.zeros((3, 2)))
        ds.gamma.attrs["units"] = "W m-2 K-1"
        ds.attrs.update(
            selected_case="primary", selected_lag_months=1, selected_target="turbulent"
        )
        fields[hemisphere] = ds
    for hemisphere, lat, value in [
        ("north", 20, 10),
        ("south", -20, 30),
        ("south", -60, 50),
    ]:
        fields[hemisphere].gamma.loc[{"latitude": lat, "longitude": 0}] = value
        fields[hemisphere].reliable.loc[{"latitude": lat, "longitude": 0}] = 1
    # These must never enter the estimate: unreliable, negative, zero, nonfinite.
    fields["north"].gamma.loc[{"latitude": 20, "longitude": 180}] = 999
    fields["north"].gamma.loc[{"latitude": 60, "longitude": 0}] = -4
    fields["north"].reliable.loc[{"latitude": 60, "longitude": 0}] = 1
    fields["south"].gamma.loc[{"latitude": -60, "longitude": 180}] = 0
    fields["south"].reliable.loc[{"latitude": -60, "longitude": 180}] = 1
    fields["south"].gamma.loc[{"latitude": -90, "longitude": 0}] = np.inf
    fields["south"].reliable.loc[{"latitude": -90, "longitude": 0}] = 1
    return fields, ocean


def test_area_weighted_pool_uses_both_hemispheres_without_equal_hemi_weight(sample):
    fields, ocean = sample
    result = constant_damping_statistics(fields, ocean, radius_m=1)
    a20 = np.pi * (np.sin(np.deg2rad(40)) - np.sin(np.deg2rad(10)))
    a60 = np.pi * (np.sin(np.deg2rad(75)) - np.sin(np.deg2rad(40)))
    expected = (10 * a20 + 30 * a20 + 50 * a60) / (2 * a20 + a60)
    assert result["global"]["area_weighted_mean"] == pytest.approx(expected)
    assert result["hemispheres"]["north"]["area_weighted_mean"] == 10
    assert result["hemispheres"]["south"]["area_weighted_mean"] == pytest.approx(
        (30 * a20 + 50 * a60) / (a20 + a60)
    )
    assert result["global"]["area_weighted_mean"] != pytest.approx(
        np.mean([v["area_weighted_mean"] for v in result["hemispheres"].values()])
    )
    assert result["global"]["sample_cells"] == 3
    assert result["global"]["unweighted_mean"] == 30
    assert result["global"]["unweighted_median"] == 30
    assert result["global"]["minimum"] == 10 and result["global"]["maximum"] == 50
    assert result["global"]["sample_area_m2"] == pytest.approx(2 * a20 + a60)
    assert result["global"]["sample_ocean_area_fraction"] == pytest.approx(
        (2 * a20 + a60) / (4 * np.pi * (1 - np.sin(np.deg2rad(10))))
    )
    assert result["global"]["units"] == "W m-2 K-1"
    assert constant_damping_statistics(fields, ocean, 1) == result
    bigger = constant_damping_statistics(fields, ocean, 2)
    assert bigger["global"]["area_weighted_mean"] == pytest.approx(expected)
    assert bigger["global"]["sample_area_m2"] == pytest.approx(
        4 * result["global"]["sample_area_m2"]
    )


def test_ocean_selection_units_reliability_and_empty_samples_are_explicit(sample):
    fields, ocean = sample
    ocean.ocean.loc[{"latitude": -60, "longitude": 0}] = 0
    result = constant_damping_statistics(fields, ocean, 1)
    assert result["global"]["sample_cells"] == 2
    assert result["global"]["area_weighted_mean"] == pytest.approx(20)
    fields["north"].gamma.attrs["units"] = "unknown"
    with pytest.raises(ValueError, match="units"):
        constant_damping_statistics(fields, ocean)
    fields["north"].gamma.attrs["units"] = "W m-2 K-1"
    fields["north"].reliable[:] = np.nan
    with pytest.raises(ValueError, match="No reliable positive"):
        constant_damping_statistics(fields, ocean)
    with pytest.raises(ValueError, match="Both hemispheres"):
        constant_damping_statistics({"north": fields["north"]}, ocean)


def test_active_mask_ignores_local_gamma_and_includes_exact_20_degree_boundaries():
    source = grid([20.0, 19.75, -19.75, -20.0], [0.0, 180.0])
    depth = source.copy()
    depth["H"] = (("latitude", "longitude"), np.full((4, 2), 10.0, dtype="f4"))
    depth["gamma"] = (("latitude", "longitude"), np.full((4, 2), np.nan))
    depth["open_water"] = depth["reliable"] = xr.zeros_like(depth.H)
    coefficients = source.assign_coords(mode=np.arange(1, 13))
    coefficients["coefficient"] = (
        ("mode", "latitude", "longitude"),
        np.ones((12, 4, 2)),
    )
    ocean = source.copy()
    ocean["ocean"] = xr.ones_like(depth.H)
    original_h = depth.H.values.copy()
    np.testing.assert_array_equal(
        simulation_mask(depth, coefficients, ocean, "north"),
        [[1, 1], [0, 0], [0, 0], [0, 0]],
    )
    np.testing.assert_array_equal(
        simulation_mask(depth, coefficients, ocean, "south"),
        [[0, 0], [0, 0], [0, 0], [1, 1]],
    )
    np.testing.assert_array_equal(depth.H, original_h)
    assert np.isnan(depth.gamma).all()
    # Land, nonpositive/missing H and any bad coefficient exclude cells, never fill.
    ocean.ocean.values[0, 0] = 0
    depth.H.values[0, 1] = 0
    coefficients.coefficient.values[11, -1, 0] = np.inf
    depth.H.values[-1, 1] = np.nan
    assert not simulation_mask(depth, coefficients, ocean, "north").any()
    assert not simulation_mask(depth, coefficients, ocean, "south").any()
    assert np.isnan(depth.H.values[-1, 1])


def test_runtime_coverage_reports_areas_and_config_is_small_reproducible(
    tmp_path, sample
):
    fields, ocean = sample
    domain = extratropics(ocean, "north")
    depth = domain.drop_vars("ocean").copy()
    depth["H"] = (("latitude", "longitude"), np.full((3, 2), 10.0, dtype="f4"))
    beta = domain.assign_coords(mode=np.arange(1, 13)).drop_vars("ocean")
    beta["coefficient"] = (("mode", "latitude", "longitude"), np.ones((12, 3, 2)))
    stats = runtime_coverage(
        depth, beta, domain, "north", extratropics(spherical_cell_areas(ocean), "north")
    )
    assert stats["active_cells"] == 6 and stats["active_ocean_area_fraction"] == 1
    assert "gamma" not in depth
    coefficient = constant_damping_statistics(fields, ocean)["global"][
        "area_weighted_mean"
    ]
    path = tmp_path / "damping.toml"
    first = write_damping_config(path, coefficient)
    assert first["sha256"] == checksum(path)
    assert write_damping_config(path, coefficient) == first
    assert first["bytes"] < 1024
    assert tomllib.loads(path.read_text())["surface_damping"] == {
        "mode": "constant",
        "gamma_w_m2_k": coefficient,
    }
    with pytest.raises(ValueError, match="positive"):
        write_damping_config(path, 0)
    other = tmp_path / "user.toml"
    other.write_text("# unrelated experiment\n")
    with pytest.raises(ValueError, match="unrelated"):
        write_damping_config(other, coefficient)
