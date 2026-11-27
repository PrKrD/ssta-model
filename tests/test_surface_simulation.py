"""Controlled analytical and end-to-end cases; no local scientific datasets needed."""

import json
from pathlib import Path

import netCDF4
import numpy as np
import pytest
import xarray as xr

from ssta_model.core.configuration import load_configuration
from ssta_model.core.integration import backward_euler
from ssta_model.core.simulation import month_intervals, run_experiment
from ssta_model.data.model_inputs import extratropics, simulation_mask
from ssta_model.data.prepare import checksum
from ssta_model.data.runtime import validate_inputs
from ssta_model.forcing.historical import reconstruct_month
from ssta_model.physics.surface_flux import heat_capacity, surface_tendency


def advance(t, f, h, gamma, dt=86400):
    return backward_euler(
        np.array(t),
        np.array(f),
        np.array(h),
        np.ones(np.shape(t), bool),
        dt,
        1025,
        3990,
        gamma,
    )


def test_disabled_identity_and_signed_damping_recurrence():
    initial = np.array([2.0, -3.0, 0.0])
    depth = np.array([10.0, 50.0, 100.0])
    state = initial.copy()
    durations = month_intervals("1979-01", "1980-12")[3]
    expected = initial.copy()
    for dt in durations:
        np.testing.assert_array_equal(
            advance(initial, np.zeros(3), depth, 0, dt), initial
        )
        state = advance(state, np.zeros(3), depth, 16, dt)
        expected /= 1 + dt * 16 / (1025 * 3990 * depth)
    np.testing.assert_allclose(state, expected, atol=1e-15)
    assert 0 < state[0] < initial[0] and initial[1] < state[1] < 0
    assert state.dtype == np.float64


def test_constant_forcing_equilibrium_and_undamped_signs():
    state = np.zeros(2)
    forcing = np.array([40.0, -20.0])
    for _ in range(500):
        state = advance(state, forcing, [10, 20], 10, dt=31 * 86400)
    np.testing.assert_allclose(state, forcing / 10, atol=1e-14)
    actual = advance([1, -1], forcing, [10, 20], 0)
    np.testing.assert_allclose(
        actual, np.array([1, -1]) + 86400 * forcing / (1025 * 3990 * np.array([10, 20]))
    )
    assert actual[0] > 1 and actual[1] < -1


def test_masked_depths_never_divide_and_budget_is_discretely_closed():
    valid = np.array([[True, False, True, False]])
    depth = np.array([[10, 0, 50, np.nan]])
    old = np.array([[1, np.nan, -2, 5]])
    forcing = np.array([[100, np.nan, -40, np.inf]])
    with np.errstate(all="raise"):
        new = backward_euler(old, forcing, depth, valid, 29 * 86400, 1025, 3990, 16)
    assert np.isnan(new[~valid]).all()
    capacity = heat_capacity(depth[valid], 1025, 3990)
    lhs = capacity * (new[valid] - old[valid]) / (29 * 86400)
    rhs = forcing[valid] - 16 * new[valid]
    np.testing.assert_allclose(lhs, rhs, atol=1e-12)
    np.testing.assert_allclose(
        (new[valid] - old[valid]) / (29 * 86400),
        surface_tendency(new[valid], forcing[valid], capacity, 16),
    )
    for bad_depth in (0, -1, np.nan, np.inf):
        with pytest.raises(ValueError, match="depth"):
            advance([0], [1], [bad_depth], 1)
    for gamma in (-1, np.nan, np.inf, [1]):
        with pytest.raises(ValueError, match="Damping"):
            advance([0], [1], [10], gamma)
    with pytest.raises(ValueError, match="shapes"):
        advance([0, 1], [1], [10, 10], 1)
    with pytest.raises(ValueError, match="Non-finite"):
        advance([np.nan], [1], [10], 1)
    with pytest.raises(ValueError, match="Timestep"):
        advance([0], [1], [10], 1, dt=0)


def test_ordered_forcing_no_broadcasting_and_cell_local_missingness():
    pc = np.arange(1, 13, dtype=float)
    beta = np.arange(12 * 2 * 3, dtype=float).reshape(12, 2, 3)
    expected = sum(beta[k] * pc[k] for k in range(12))
    np.testing.assert_array_equal(reconstruct_month(pc, beta), expected)
    beta[:, 0, 0] = np.nan
    result = reconstruct_month(pc, beta)
    assert np.isnan(result[0, 0])
    np.testing.assert_array_equal(result[1], expected[1])
    for bad_pc, bad_beta in ((pc[:, None], beta), (pc, beta[0]), (pc[:-1], beta)):
        with pytest.raises(ValueError, match="shape"):
            reconstruct_month(bad_pc, bad_beta)
    with pytest.raises(ValueError, match="finite"):
        reconstruct_month(pc * np.nan, beta)


def test_calendar_durations_leap_year_and_exact_end_boundaries():
    months, starts, ends, durations = month_intervals("1979-01", "1980-12")
    assert len(months) == 24
    np.testing.assert_array_equal(durations[:4] / 86400, [31, 28, 31, 30])
    assert durations[13] == 29 * 86400
    assert str(starts[0]) == "1979-01-01T00:00:00"
    assert str(ends[0]) == "1979-02-01T00:00:00"
    assert str(ends[-1]) == "1981-01-01T00:00:00"
    np.testing.assert_array_equal(starts[1:], ends[:-1])
    assert month_intervals("1979-01", "2026-10")[0].size == 574
    assert month_intervals("2000-02", "2000-02")[3][0] == 29 * 86400
    assert month_intervals("2100-02", "2100-02")[3][0] == 28 * 86400


@pytest.fixture
def experiment(tmp_path):
    directory = tmp_path / "data/processed"
    directory.mkdir(parents=True)
    (tmp_path / "configs").mkdir()
    (tmp_path / "configs/surface_damping.toml").write_text(
        '[surface_damping]\nmode="constant"\ngamma_w_m2_k=16.0\n'
    )
    ocean = xr.Dataset(
        {
            "ocean": (("latitude", "longitude"), np.ones((5, 4), dtype="i1")),
            "land_fraction": (("latitude", "longitude"), np.zeros((5, 4))),
        },
        coords={
            "latitude": [40.0, 20.0, 0.0, -20.0, -40.0],
            "longitude": [0.0, 90.0, 180.0, 270.0],
        },
    )
    ocean.ocean.values[0, 0] = 0
    ocean.land_fraction.values[0, 0] = 1
    ocean.to_netcdf(directory / "era5_ocean_mask.nc", engine="netcdf4")
    products = {}
    for hemisphere, sign in (("north", 1), ("south", -1)):
        grid = extratropics(ocean, hemisphere)
        pcs = xr.Dataset(
            {
                "standardized_pc": (
                    ("time", "mode"),
                    sign * np.arange(1, 37, dtype=float).reshape(3, 12),
                )
            },
            coords={
                "time": np.arange("1980-01", "1980-04", dtype="datetime64[M]").astype(
                    "datetime64[ns]"
                ),
                "mode": np.arange(1, 13),
            },
            attrs={
                "hemisphere": hemisphere,
                "first_month": "1980-01",
                "last_month": "1980-03",
            },
        )
        pcs.standardized_pc.attrs = {"units": "1", "ddof": 1}
        regression = xr.Dataset(
            {"coefficient": (("mode", "latitude", "longitude"), np.ones((12, 2, 4)))},
            coords={
                "mode": pcs.mode,
                "latitude": grid.latitude,
                "longitude": grid.longitude,
            },
            attrs={
                "hemisphere": hemisphere,
                "heat_positive": "downward",
                "method": "joint year-round regression",
                "sst_feedback_adjustment": "none",
                "first_month": "1980-01",
                "last_month": "1980-03",
            },
        )
        regression.coefficient.attrs["units"] = "W m-2 per EOF-training PC SD"
        surface = xr.Dataset(
            {"H": (("latitude", "longitude"), np.full((2, 4), 50.0))},
            coords={k: grid[k] for k in ("latitude", "longitude")},
        )
        surface.H.attrs["units"] = "m"
        surface.H.values[1, 0] = np.nan
        regression.coefficient.values[0, 0, 1] = np.nan
        surface["input_valid"] = simulation_mask(surface, regression, grid, hemisphere)
        for kind, ds in (
            ("pcs", pcs),
            ("regression", regression),
            ("surface", surface),
        ):
            ds.to_netcdf(directory / f"{hemisphere}_{kind}.nc", engine="netcdf4")
        products[hemisphere] = (pcs, regression, surface)
    manifest = {
        "products": [
            {"filename": p.name, "sha256": checksum(p)}
            for p in sorted(directory.glob("*.nc"))
        ],
        "fixture": "Controlled inputs, not observations",
    }
    (directory / "manifest.json").write_text(json.dumps(manifest))
    config = tmp_path / "configs/pilot.toml"
    config.write_text("""[experiment]
name="controlled"
start_month="1980-01"
end_month="1980-03"
[physics]
surface_forcing=true
surface_damping=true
[parameters]
rho_kg_m3=1025.0
cp_j_kg_k=3990.0
[initial_conditions]
temperature_anomaly_k=0.0
[output]
directory="runs/test"
""")
    return tmp_path, config, ocean, products


def test_boundary_rejects_grid_modes_units_and_mask_changes(experiment):
    _, _, ocean, products = experiment
    pcs, regression, surface = products["north"]
    validate_inputs(pcs, regression, surface, ocean, "north")
    for changed in (
        regression.assign_coords(mode=np.arange(12)),
        regression.assign_coords(longitude=regression.longitude + 0.25),
    ):
        with pytest.raises(ValueError):
            validate_inputs(pcs, changed, surface, ocean, "north")
    bad = surface.copy(deep=True)
    bad.input_valid.values[0, 0] = 1  # Land cannot be enabled.
    with pytest.raises(ValueError, match="input_valid"):
        validate_inputs(pcs, regression, bad, ocean, "north")
    bad = regression.copy(deep=True)
    bad.coefficient.attrs["units"] = "K"
    with pytest.raises(ValueError, match="units"):
        validate_inputs(pcs, bad, surface, ocean, "north")


@pytest.mark.parametrize(
    "forcing,damping", [(True, True), (False, True), (True, False), (False, False)]
)
def test_streamed_output_alignment_switches_reproducibility_and_independence(
    experiment, forcing, damping
):
    root, config_path, _, products = experiment
    text = (
        config_path.read_text()
        .replace("temperature_anomaly_k=0.0", "temperature_anomaly_k=1.25")
        .replace("surface_forcing=true", f"surface_forcing={str(forcing).lower()}")
        .replace("surface_damping=true", f"surface_damping={str(damping).lower()}")
    )
    config_path.write_text(text)
    first = run_experiment(config_path, root)
    config_path.write_text(
        text.replace('directory="runs/test"', 'directory="runs/repeat"')
    )
    second = run_experiment(config_path, root)
    for hemisphere, (pcs, _, surface) in products.items():
        result = first["hemispheres"][hemisphere]
        valid = surface.input_valid.values == 1
        assert result["active_cells"] == int(valid.sum())
        assert result["maximum_budget_residual_w_m2"] < 1e-10
        assert result["active_nonfinite"] == 0
        assert result["monthly"] == second["hemispheres"][hemisphere]["monthly"]
        with xr.open_dataset(
            root / f"runs/test/{hemisphere}_sst.nc", engine="netcdf4"
        ) as ds:
            assert ds.sst_anomaly.dtype == np.float32
            assert ds.sst_anomaly.encoding["zlib"]
            assert ds.sst_anomaly.encoding["chunksizes"][0] == 1
            np.testing.assert_array_equal(
                ds.forcing_month, ["1980-01", "1980-02", "1980-03"]
            )
            assert str(ds.time.values[0])[:10] == "1980-02-01"
            assert str(ds.time_bounds.values[0, 0])[:10] == "1980-01-01"
            assert np.isnan(ds.sst_anomaly.values[:, ~valid]).all()
            expected = np.full(valid.sum(), 1.25)
            for index, dt in enumerate([31 * 86400, 29 * 86400, 31 * 86400]):
                f = float(pcs.standardized_pc.values[index].sum()) if forcing else 0
                g = 16 if damping else 0
                expected = (expected + dt * f / (1025 * 3990 * 50)) / (
                    1 + dt * g / (1025 * 3990 * 50)
                )
                np.testing.assert_array_equal(
                    ds.sst_anomaly.values[index][valid], expected.astype("f4")
                )
            assert (
                np.all(ds.latitude >= 20)
                if hemisphere == "north"
                else np.all(ds.latitude <= -20)
            )
    with pytest.raises(FileExistsError):
        run_experiment(config_path, root)


def test_configuration_overrides_invalid_values_and_input_checksums(experiment):
    root, path, _, _ = experiment
    baseline = path.read_text()
    path.write_text(baseline + "\n[surface_damping]\ngamma_w_m2_k=0.0\n")
    assert load_configuration(path, root)["surface_damping"]["gamma_w_m2_k"] == 0
    for invalid in ("-1.0", "nan", "inf", "[1.0]", "true"):
        path.write_text(baseline + f"\n[surface_damping]\ngamma_w_m2_k={invalid}\n")
        with pytest.raises(ValueError, match="Damping"):
            load_configuration(path, root)
    path.write_text(baseline.replace('"1980-01"', '"1980-1"'))
    with pytest.raises(ValueError, match="YYYY-MM"):
        load_configuration(path, root)
    path.write_text(
        baseline.replace('directory="runs/test"', 'directory="data/processed/new"')
    )
    with pytest.raises(ValueError, match="under runs"):
        load_configuration(path, root)
    path.write_text(baseline.replace('"1980-03"', '"1981-01"'))
    with pytest.raises(ValueError, match="PC record"):
        run_experiment(path, root)
    assert (
        json.loads((root / "runs/test/summary.json").read_text())["status"] == "failed"
    )
    path.write_text(baseline)
    target = root / "data/processed/north_pcs.nc"
    with netCDF4.Dataset(target, "a") as ds:
        ds["standardized_pc"][0, 0] = 999
    with pytest.raises(ValueError, match="checksum mismatch"):
        run_experiment(path, root)


def test_observed_january_initialization_february_first_no_later_assimilation(
    experiment,
):
    from ssta_model.analysis.era5_comparison import aligned_months

    root, path, _, products = experiment
    directory = root / "data/processed"
    dates = np.arange("1979-01", "1979-04", dtype="datetime64[M]").astype(
        "datetime64[ns]"
    )
    for h, (pcs, regression, surface) in products.items():
        pcs = pcs.assign_coords(time=dates)
        pcs.attrs.update(first_month="1979-01", last_month="1979-03")
        regression.attrs.update(first_month="1979-01", last_month="1979-03")
        pcs.to_netcdf(directory / f"{h}_pcs.nc", engine="netcdf4")
        regression.to_netcdf(directory / f"{h}_regression.nc", engine="netcdf4")
        values = np.full((3, 2, 4), 999.0)
        values[0] = 2.0
        flat = np.flatnonzero(surface.input_valid.values.ravel() == 1)[0]
        values[0].flat[flat] = np.nan
        era = xr.Dataset(
            {"sst_anomaly": (("time", "latitude", "longitude"), values)},
            coords={
                "time": dates,
                "latitude": surface.latitude,
                "longitude": surface.longitude,
            },
        )
        era.sst_anomaly.attrs["units"] = "K"
        era.to_netcdf(directory / f"{h}_era5_ssta.nc", engine="netcdf4")
    manifest = json.loads((directory / "manifest.json").read_text())
    for record in manifest["products"]:
        record["sha256"] = checksum(directory / record["filename"])
    (directory / "manifest.json").write_text(json.dumps(manifest))
    text = (
        path.read_text()
        .replace("1980-", "1979-")
        .replace(
            "temperature_anomaly_k=0.0",
            'temperature_anomaly_k=0.0\nkind="era5"\nmonth="1979-01"',
        )
    )
    path.write_text(text)
    run_experiment(path, root)
    for h, (pcs, _, surface) in products.items():
        with (
            xr.open_dataset(root / f"runs/test/{h}_sst.nc") as model,
            xr.open_dataset(directory / f"{h}_era5_ssta.nc") as era,
        ):
            np.testing.assert_array_equal(model.forcing_month, ["1979-02", "1979-03"])
            assert aligned_months(model, era) == [(0, 1, "1979-02"), (1, 2, "1979-03")]
            assert model.sizes["time"] == 2
            assert model.initial_time == "1979-02-01T00:00:00Z"
            valid = model.input_valid.values == 1
            assert valid.sum() == (surface.input_valid.values == 1).sum() - 1
            np.testing.assert_array_equal(model.initial_sst_anomaly.values[valid], 2.0)
            forcing = pcs.standardized_pc.values[1].sum()
            expected = (2 + 28 * 86400 * forcing / (1025 * 3990 * 50)) / (
                1 + 28 * 86400 * 16 / (1025 * 3990 * 50)
            )
            np.testing.assert_array_equal(
                model.sst_anomaly.values[0][valid],
                np.full(valid.sum(), expected).astype("f4"),
            )
            assert np.isnan(model.sst_anomaly.values[:, ~valid]).all()
        with netCDF4.Dataset(directory / f"{h}_era5_ssta.nc", "a") as era:
            era["sst_anomaly"][1:] = -99999
    path.write_text(
        text.replace('directory="runs/test"', 'directory="runs/observed_repeat"')
    )
    run_experiment(path, root)
    for h in products:
        with (
            xr.open_dataset(root / f"runs/test/{h}_sst.nc") as first,
            xr.open_dataset(root / f"runs/observed_repeat/{h}_sst.nc") as second,
        ):
            np.testing.assert_array_equal(first.sst_anomaly, second.sst_anomaly)


def test_diffusion_off_and_zero_kappa_reproduce_independent_cell_runner(experiment):
    root, path, _, _ = experiment
    text = path.read_text()
    baseline = run_experiment(path, root)
    for enabled, kappa, name in ((False, 1000.0, "off"), (True, 0.0, "zero")):
        configured = (
            text.replace(
                "surface_damping=true",
                f"surface_damping=true\nhorizontal_diffusion={str(enabled).lower()}",
            )
            .replace("rho_kg_m3=1025.0", f"rho_kg_m3=1025.0\nkappa_m2_s={kappa}")
            .replace('directory="runs/test"', f'directory="runs/{name}"')
        )
        path.write_text(configured)
        current = run_experiment(path, root)
        for h in ("north", "south"):
            assert (
                current["hemispheres"][h]["monthly"]
                == baseline["hemispheres"][h]["monthly"]
            )
            with (
                xr.open_dataset(root / f"runs/test/{h}_sst.nc") as original,
                xr.open_dataset(root / f"runs/{name}/{h}_sst.nc") as new,
            ):
                np.testing.assert_array_equal(original.sst_anomaly, new.sst_anomaly)


def candidate_fixture(root, ocean):
    directory = root / "data/processed"
    for h in ("north", "south"):
        with xr.open_dataset(directory / f"{h}_surface.nc") as b:
            hfield = (
                b.H.where(extratropics(ocean, h).ocean == 1)
                .fillna(80.0)
                .where(extratropics(ocean, h).ocean == 1)
            )
            hfield = hfield * 1.5
            candidate = xr.Dataset(
                {
                    "H": hfield,
                    "baseline_input_valid": b.input_valid.load(),
                    "era5_ocean": extratropics(ocean, h).ocean,
                    "support_method": xr.where(np.isfinite(hfield), 1, 0),
                },
                attrs={
                    "prepared_by": "ssta_model.data.era5_h_candidate",
                    "baseline_sha256": checksum(directory / f"{h}_surface.nc"),
                    "target_mask_sha256": checksum(directory / "era5_ocean_mask.nc"),
                },
            )
            candidate.H.attrs["units"] = "m"
            candidate.to_netcdf(directory / f"{h}_surface_h_era5_bilinear.nc")


def test_depth_variant_selection_preserves_authorised_mask_and_rejects_bad_candidate(
    experiment,
):
    from ssta_model.data.runtime import load_hemisphere

    root, path, ocean, _ = experiment
    candidate_fixture(root, ocean)
    directory = root / "data/processed"
    config = load_configuration(path, root)
    assert config["mixed_layer_depth"]["variant"] == "baseline"
    path.write_text(
        path.read_text() + '\n[mixed_layer_depth]\nvariant="era5_bilinear"\n'
    )
    assert (
        load_configuration(path, root)["mixed_layer_depth"]["variant"]
        == "era5_bilinear"
    )
    baseline = load_hemisphere(directory, "north", ocean)
    selected = load_hemisphere(directory, "north", ocean, "era5_bilinear")
    np.testing.assert_array_equal(
        baseline["surface"].input_valid, selected["surface"].input_valid
    )
    assert (
        np.isfinite(selected["surface"].H.values[1, 0])
        and selected["surface"].input_valid.values[1, 0] == 0
    )
    assert np.isnan(baseline["surface"].H.values[1, 0])
    assert selected["surface"].H.values[1, 1] == 75
    filename = directory / "north_surface_h_era5_bilinear.nc"
    with xr.open_dataset(filename) as ds:
        good = ds.load()
    for change in ("units", "coordinates", "missing", "zero", "mask", "checksum"):
        bad = good.copy(deep=True)
        if change == "units":
            bad.H.attrs["units"] = "K"
        elif change == "coordinates":
            bad = bad.assign_coords(longitude=bad.longitude + 0.25)
        elif change == "missing":
            bad.H.values[1, 1] = np.nan
        elif change == "zero":
            bad.H.values[1, 1] = 0
        elif change == "mask":
            bad.baseline_input_valid.values[1, 1] = 0
        else:
            bad.attrs["baseline_sha256"] = "invalid"
        bad.to_netcdf(filename, mode="w")
        with pytest.raises(ValueError):
            load_hemisphere(directory, "north", ocean, "era5_bilinear")


@pytest.mark.parametrize("variant", ["baseline", "era5_bilinear"])
def test_both_depth_variants_recover_original_independent_update_with_zero_diffusion(
    experiment, variant
):
    root, path, ocean, _ = experiment
    candidate_fixture(root, ocean)
    text = (
        path.read_text()
        .replace(
            "surface_damping=true", "surface_damping=true\nhorizontal_diffusion=false"
        )
        .replace("rho_kg_m3=1025.0", "rho_kg_m3=1025.0\nkappa_m2_s=1000.0")
        + f'\n[mixed_layer_depth]\nvariant="{variant}"\n'
    )
    path.write_text(text)
    baseline = run_experiment(path, root)
    path.write_text(
        text.replace("horizontal_diffusion=false", "horizontal_diffusion=true")
        .replace("kappa_m2_s=1000.0", "kappa_m2_s=0.0")
        .replace('directory="runs/test"', 'directory="runs/zero"')
    )
    result = run_experiment(path, root)
    for h in ("north", "south"):
        assert (
            baseline["hemispheres"][h]["monthly"] == result["hemispheres"][h]["monthly"]
        )
    path.write_text(
        text.replace("horizontal_diffusion=false", "horizontal_diffusion=true")
        .replace("surface_forcing=true", "surface_forcing=false")
        .replace("surface_damping=true", "surface_damping=false")
        .replace("temperature_anomaly_k=0.0", "temperature_anomaly_k=2.0")
        .replace('directory="runs/test"', 'directory="runs/uniform"')
    )
    uniform = run_experiment(path, root)
    for h in ("north", "south"):
        assert uniform["hemispheres"][h]["minimum_k"] == pytest.approx(2, abs=1e-12)
        assert uniform["hemispheres"][h]["maximum_k"] == pytest.approx(2, abs=1e-12)


def test_selected_depth_validates_polar_retention(experiment):
    from ssta_model.data.runtime import load_hemisphere

    root, path, ocean, _ = experiment
    directory = root / "data/processed"
    ocean = ocean.assign_coords(latitude=[90.0, 20.0, 0.0, -20.0, -40.0])
    ocean.to_netcdf(directory / "era5_ocean_mask.nc", mode="w")
    for kind in ("surface", "regression"):
        p = directory / f"north_{kind}.nc"
        with xr.open_dataset(p) as ds:
            changed = ds.load().assign_coords(latitude=[90.0, 20.0])
        changed.to_netcdf(p, mode="w")
    # Baseline H must remain exactly unchanged for the limited polar exception.
    candidate_fixture(root, ocean)
    p = directory / "north_surface_h_era5_bilinear.nc"
    with xr.open_dataset(p) as ds:
        candidate = ds.load()
    with xr.open_dataset(directory / "north_surface.nc") as ds:
        baseline = ds.load()
    polar = np.broadcast_to(
        candidate.latitude.values[:, None] > 89.5, candidate.H.shape
    )
    active = candidate.baseline_input_valid.values == 1
    candidate.H.values[polar] = np.where(
        active[polar], baseline.H.values[polar], np.nan
    )
    candidate.support_method.values[polar] = np.where(active[polar], 2, 0)
    candidate.to_netcdf(p, mode="w")
    load_hemisphere(directory, "north", ocean, "era5_bilinear")
    candidate.H.values[0, 2] += 1
    candidate.to_netcdf(p, mode="w")
    with pytest.raises(ValueError, match="polar H"):
        load_hemisphere(directory, "north", ocean, "era5_bilinear")


def test_interactive_worker_uses_selected_gamma_and_exports_24_states(experiment):
    """Actual child-process solver/export on controlled tiny inputs, without local data."""
    from ssta_model.data.comparison_export import comparison_bins
    from ssta_model.interactive import execute_run

    root, _, ocean, _ = experiment
    directory = root / "data/processed"
    dates = np.arange("1979-01", "1981-01", dtype="datetime64[M]").astype(
        "datetime64[ns]"
    )
    for h, sign in (("north", 1), ("south", -1)):
        path = directory / f"{h}_pcs.nc"
        with xr.open_dataset(path) as ds:
            pcs = ds.load().drop_dims("time").assign_coords(time=dates)
        pcs["standardized_pc"] = (
            ("time", "mode"),
            sign * np.cos(np.arange(24)[:, None] / 5) * np.arange(1, 13)[None, :],
        )
        pcs.standardized_pc.attrs = {"units": "1", "ddof": 1}
        pcs.attrs.update(first_month="1979-01", last_month="1980-12")
        pcs.to_netcdf(path, mode="w")
        path = directory / f"{h}_regression.nc"
        with xr.open_dataset(path) as ds:
            regression = ds.load()
        regression.attrs.update(first_month="1979-01", last_month="1980-12")
        regression.to_netcdf(path, mode="w")
        grid = extratropics(ocean, h)
        era = xr.Dataset(
            {
                "sst_anomaly": (
                    ("time", "latitude", "longitude"),
                    np.full((24, 2, 4), 1.5),
                )
            },
            coords={
                "time": dates,
                "latitude": grid.latitude,
                "longitude": grid.longitude,
            },
        )
        era.sst_anomaly.attrs["units"] = "K"
        era.to_netcdf(directory / f"{h}_era5_ssta.nc")
    candidate_fixture(root, ocean)
    manifest = {
        "products": [
            {"filename": p.name, "sha256": checksum(p)} for p in directory.glob("*.nc")
        ]
    }
    (directory / "manifest.json").write_text(json.dumps(manifest))
    template = Path(__file__).resolve().parents[1] / "configs/interactive_damping.toml"
    (root / "configs/interactive_damping.toml").write_text(template.read_text())
    keys = []
    for h in ("north", "south"):
        with xr.open_dataset(directory / f"{h}_surface_h_era5_bilinear.nc") as ds:
            bins = comparison_bins(ds.latitude.values, ds.longitude.values)
            keys.extend(bins[np.isfinite(ds.H.values)].tolist())
    cells = [
        {
            "id": f"comparison-{k}",
            "west": -180 + (k % 720) / 2,
            "east": -180 + (k % 720 + 1) / 2,
            "south": -90 + (k // 720) / 2,
            "north": -90 + (k // 720 + 1) / 2,
        }
        for k in sorted(set(keys))
    ]
    grid_path = root / "frontend/public/data/era5_comparison"
    grid_path.mkdir(parents=True)
    (grid_path / "manifest.json").write_text(
        json.dumps({"grid": {"id": "controlled-grid", "cells": cells}})
    )
    folders = []
    for gamma in (10.0, 20.0):
        folder = root / f"runs/interactive_damping/test{int(gamma)}"
        folder.mkdir(parents=True)
        execute_run(root, folder, gamma)
        folders.append(folder)
        display = json.loads((folder / "display/manifest.json").read_text())
        assert (
            display["months"]
            == np.arange("1979-01", "1981-01", dtype="datetime64[M]")
            .astype(str)
            .tolist()
        )
        assert len(display["frames"]) == 24 and display["gamma_w_m2_k"] == gamma
        assert display["timestamps"][0] == "1979-02-01T00:00:00Z"
        assert display["timestamps"][-1] == "1981-01-01T00:00:00Z"
        with (
            xr.open_dataset(folder / "model/north_sst.nc") as ds,
            xr.open_dataset(directory / "north_pcs.nc") as pcs,
        ):
            config = json.loads(ds.attrs["configuration_json"])
            assert config["surface_damping"]["gamma_w_m2_k"] == gamma
            assert config["mixed_layer_depth"]["variant"] == "era5_bilinear"
            assert config["parameters"]["kappa_m2_s"] == 1000
            active = ds.input_valid.values == 1
            forcing = np.sum(pcs.standardized_pc.values[1])
            dt = 28 * 86400
            expected = (1025 * 3990 * 75 * 1.5 + dt * forcing) / (
                1025 * 3990 * 75 + dt * gamma
            )
            np.testing.assert_allclose(
                ds.sst_anomaly.values[0][active], expected, atol=1e-6
            )
    with (
        xr.open_dataset(folders[0] / "model/north_sst.nc") as a,
        xr.open_dataset(folders[1] / "model/north_sst.nc") as b,
    ):
        np.testing.assert_array_equal(a.initial_sst_anomaly, b.initial_sst_anomaly)
        np.testing.assert_array_equal(a.input_valid, b.input_valid)
        assert np.nanmax(abs(a.sst_anomaly.values - b.sst_anomaly.values)) > 0.01
