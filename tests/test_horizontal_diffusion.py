"""Conservative face fluxes, spherical boundaries and implicit solver checks."""

import numpy as np
import pytest
import xarray as xr

from ssta_model.core.diffusion import DiffusionStepper
from ssta_model.data.model_inputs import spherical_cell_areas
from ssta_model.physics.horizontal_diffusion import build_diffusion


def setup(
    lat=(30, 25, 20), lon=(0, 90, 180, 270), depth=None, valid=None, kappa=1000, gamma=0
):
    grid = xr.Dataset(
        coords={
            "latitude": np.array(lat, dtype=float),
            "longitude": np.array(lon, dtype=float),
        }
    )
    area = spherical_cell_areas(grid).values
    if depth is None:
        depth = np.full(area.shape, 50.0)
    if valid is None:
        valid = np.ones(area.shape, bool)
    geometry = build_diffusion(lat, lon, area, depth, valid, kappa)
    return (
        geometry,
        DiffusionStepper(geometry, depth, area, 1025, 3990, gamma),
        area,
        depth,
        valid,
    )


def test_face_pair_symmetry_nullspace_and_variable_depth_harmonic_mean():
    depth = np.array([[10.0, 40, 80, 160], [30, 50, 100, 150], [50, 100, 150, 200]])
    g, _, _, _, _ = setup(depth=depth)
    np.testing.assert_allclose(g.matrix.toarray(), g.matrix.toarray().T, atol=0, rtol=0)
    np.testing.assert_allclose(g.exchange(np.ones(len(g.mass))), 0, atol=0)
    assert np.all(g.conductance >= 0)
    values = np.arange(len(g.mass), dtype=float)
    assert abs(g.exchange(values).sum()) < 10 * np.finfo(float).eps * np.sum(
        abs(g.exchange(values))
    )
    # Row 30N east face: 5 degrees high / (cos(30) * 90 degrees), harmonic H=16m.
    expected = 1000 * 16 * np.deg2rad(5) / (np.cos(np.deg2rad(30)) * np.deg2rad(90))
    assert g.conductance[0] == pytest.approx(expected)
    expected_ns = 1000 * 15 * np.cos(np.deg2rad(27.5)) * np.deg2rad(90) / np.deg2rad(5)
    assert g.conductance[12] == pytest.approx(expected_ns)


def test_uniform_constant_and_weighted_heat_conservation_no_new_extrema():
    rng = np.random.default_rng(42)
    depth = rng.uniform(10, 500, (3, 4))
    g, stepper, area, depth, valid = setup(depth=depth)
    temperature = rng.uniform(-2, 3, valid.shape)
    initial = np.sum(area * depth * temperature)
    lower, upper = temperature.min(), temperature.max()
    for _ in range(12):
        temperature, diagnostics = stepper.step(
            temperature, np.zeros(valid.shape), 31 * 86400
        )
        assert temperature.min() >= lower - 1e-12 and temperature.max() <= upper + 1e-12
        assert diagnostics["solver_relative_residual"] < 1e-10
    assert np.sum(area * depth * temperature) == pytest.approx(initial, rel=1e-12)
    uniform, _ = stepper.step(
        np.full(valid.shape, -1.5), np.zeros(valid.shape), 28 * 86400
    )
    np.testing.assert_allclose(uniform, -1.5, rtol=0, atol=1e-12)
    assert len(stepper.systems) == 2


def test_warm_anomaly_spreads_across_periodic_seam_but_not_land_barrier():
    valid = np.ones((3, 4), bool)
    valid[:, 1] = False
    valid[:, 3] = False
    g, stepper, _, _, _ = setup(valid=valid)
    initial = np.where(valid, 0.0, np.nan)
    initial[1, 0] = 1
    new, _ = stepper.step(initial, np.zeros(valid.shape), 31 * 86400)
    assert new[0, 0] > 0 and new[2, 0] > 0 and new[1, 0] < 1
    np.testing.assert_allclose(new[:, 2], 0, atol=0)
    assert np.isnan(new[~valid]).all()
    g, stepper, _, _, valid = setup()
    initial = np.zeros(valid.shape)
    initial[1, 0] = 1
    new, _ = stepper.step(initial, np.zeros(valid.shape), 31 * 86400)
    assert new[1, -1] > 0
    assert not any((g.left == 0) & (g.right == len(g.mass) - 1))  # no latitude wrap


def test_polar_cap_preserves_volume_and_heat_without_zero_distance_or_land_links():
    depth = np.arange(1, 13, dtype=float).reshape(3, 4) * 10
    g, stepper, area, _, valid = setup(lat=(90, 89.75, 89.5), depth=depth)
    assert len(g.mass) == 9  # Four co-located polar sectors become one cap.
    assert g.mass.sum() == pytest.approx(np.sum(area * depth))
    initial = np.arange(12, dtype=float).reshape(3, 4)
    old_content = np.sum(initial * area * depth)
    new, d = stepper.step(initial, np.zeros(valid.shape), 31 * 86400)
    np.testing.assert_array_equal(new[0], np.full(4, new[0, 0]))
    assert np.sum(new * area * depth) == pytest.approx(old_content, rel=1e-11)
    assert d["maximum_budget_residual_w_m2"] < 1e-6
    partial = valid.copy()
    partial[0, 1] = False
    with pytest.raises(ValueError, match="polar"):
        setup(lat=(90, 89.75, 89.5), valid=partial)


def test_combined_budget_and_zero_diffusivity_recover_backward_euler():
    from ssta_model.core.integration import backward_euler

    g, stepper, area, depth, valid = setup(kappa=0, gamma=16)
    old = np.arange(12, dtype=float).reshape(3, 4) / 10
    forcing = np.full(valid.shape, 50.0)
    new, _ = stepper.step(old, forcing, 31 * 86400)
    expected = backward_euler(old, forcing, depth, valid, 31 * 86400, 1025, 3990, 16)
    np.testing.assert_allclose(new, expected, rtol=1e-13, atol=1e-13)
    g, stepper, area, depth, valid = setup(gamma=16)
    new, d = stepper.step(old, forcing, 31 * 86400)
    t = new.ravel()
    residual = (
        1025
        * 3990
        * ((area * depth).ravel() * (t - old.ravel()) / (31 * 86400) + g.exchange(t))
        / area.ravel()
        - forcing.ravel()
        + 16 * t
    )
    assert np.max(abs(residual)) < 1e-6 and d["solver_iterations"] > 0


def test_wrong_domain_bad_kappa_and_nonconvergence_are_rejected():
    with pytest.raises(ValueError, match="hemisphere"):
        setup(lat=(30, 20, -20))
    with pytest.raises(ValueError, match="extrap|hemisphere"):
        setup(lat=(30, 20, 19.75))
    with pytest.raises(ValueError, match="Diffusivity"):
        setup(kappa=-1)
    _, stepper, _, _, valid = setup()
    stepper.maxiter = 1
    with pytest.raises(RuntimeError, match="CG failed"):
        stepper.step(
            np.arange(12, dtype=float).reshape(valid.shape),
            np.zeros(valid.shape),
            31 * 86400,
        )
