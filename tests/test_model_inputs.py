"""Controlled scientific contracts; no observational data required in CI."""

import json

import numpy as np
import pytest
import xarray as xr

from ssta_model.data.model_inputs import (
    QUALITY_FLAGS,
    extratropics,
    fixed_depth,
    monthly_pc,
    same_grid,
    selected_damping,
    static_ocean_mask,
    year_round_coefficients,
)
from ssta_model.data.prepare import (
    forcing_audit,
    organize_raw,
    source_paths,
    spatial_damping_coverage,
    write_product,
)


@pytest.fixture
def pcs():
    # Synthetic test predictors only; source data are never fitted or rescaled.
    values = np.random.default_rng(71).normal(size=(24, 12))
    values = (values - values.mean(0)) / values.std(0, ddof=1)
    dates = np.arange("2000-01", "2002-01", dtype="datetime64[M]").astype(
        "datetime64[ns]"
    )
    ds = xr.Dataset(
        {"standardized_pc": (("time", "mode"), values)},
        coords={"time": dates, "mode": np.arange(1, 13)},
        attrs={
            "hemisphere": "north",
            "first_month": "2000-01",
            "last_month": "2001-12",
            "n_samples": 24,
        },
    )
    ds.standardized_pc.attrs = {"units": "1", "ddof": 1}
    return ds


@pytest.fixture
def regression(pcs):
    values = pcs.standardized_pc.values
    ds = xr.Dataset(
        {
            "coefficient": (
                ("mode", "latitude", "longitude"),
                np.arange(240, dtype=float).reshape(12, 5, 4) / 100,
            ),
            "intercept": (("latitude", "longitude"), np.full((5, 4), 0.125)),
        },
        coords={
            "mode": np.arange(1, 13),
            "latitude": [30.0, 20.0, 0.0, -20.0, -30.0],
            "longitude": [0.0, 90.0, 180.0, 270.0],
        },
        attrs={
            **pcs.attrs,
            "target": "turbulent",
            "method": "joint",
            "heat_positive": "downward",
            "pc_scaling": "original EOF-training sample SD; regression-sample centring only",
            "predictor_diagnostics": json.dumps(
                {
                    "north": {
                        "means": values.mean(0).tolist(),
                        "sample_variance": values.var(0, ddof=1).tolist(),
                        "correlation": np.corrcoef(values.T).tolist(),
                    }
                }
            ),
        },
    )
    ds.coefficient.attrs["units"] = "W m-2 per EOF-training PC SD"
    return ds


def test_pc_values_signs_order_and_continuous_dates_are_preserved(pcs):
    reduced = monthly_pc(pcs, "north")
    np.testing.assert_array_equal(reduced.standardized_pc, pcs.standardized_pc)
    np.testing.assert_array_equal(reduced.time, pcs.time)
    assert set(reduced.variables) == {"standardized_pc", "time", "mode"}
    with pytest.raises(ValueError, match="monthly"):
        monthly_pc(pcs.isel(time=[0, 2, 3]), "north")
    with pytest.raises(ValueError, match="mode order"):
        monthly_pc(pcs.isel(mode=slice(None, None, -1)), "north")
    with pytest.raises(ValueError, match="hemisphere"):
        monthly_pc(pcs, "south")
    bad = pcs.copy(deep=True)
    bad.standardized_pc.values[0, 0] = np.nan
    with pytest.raises(ValueError, match="non-finite"):
        monthly_pc(bad, "north")


def test_year_round_raw_coefficients_no_intercept_and_inclusive_domain(pcs, regression):
    reduced = year_round_coefficients(regression, pcs, "north")
    np.testing.assert_array_equal(reduced.latitude, [30, 20])
    np.testing.assert_array_equal(
        reduced.coefficient, regression.coefficient.isel(latitude=[0, 1])
    )
    assert set(reduced.data_vars) == {"coefficient"}
    assert reduced.attrs["sst_feedback_adjustment"] == "none"
    np.testing.assert_array_equal(
        extratropics(regression, "south").latitude, [-20, -30]
    )
    audit = forcing_audit(regression, reduced, pcs, "north")
    assert audit["intercept"]["median"] == 0.125
    assert audit["sample_reconstruction_max_error"] == 0
    assert audit["without_intercept_temporal_mean"]["abs_p95"] < 1e-14
    assert audit["fitted_temporal_mean"]["median"] == pytest.approx(0.125)
    bad = regression.assign_coords(mode=np.arange(12))
    with pytest.raises(ValueError, match="modes differ"):
        year_round_coefficients(bad, pcs, "north")


def test_documented_year_round_fit_selected_and_seasonal_only_rejected(pcs, regression):
    mixed = regression.copy()
    mixed["coefficient"] = regression.coefficient.expand_dims(
        fit=[10, 20, 30, 40, 50]
    ).copy()
    mixed.attrs["fit_labels"] = json.dumps(["DJF", "year_round", "MAM", "JJA", "SON"])
    mixed.coefficient.loc[{"fit": 10}] = 999
    reduced = year_round_coefficients(mixed, pcs, "north")
    np.testing.assert_array_equal(
        reduced.coefficient, regression.coefficient.isel(latitude=[0, 1])
    )
    seasonal = regression.copy()
    seasonal["coefficient"] = regression.coefficient.expand_dims(
        season=["DJF", "MAM", "JJA", "SON"]
    )
    with pytest.raises(ValueError, match="seasonal fits are not averaged"):
        year_round_coefficients(seasonal, pcs, "north")
    adjusted = regression.copy()
    adjusted.attrs["target"] = "adjusted_turbulent"
    with pytest.raises(ValueError, match="target=turbulent"):
        year_round_coefficients(adjusted, pcs, "north")


def test_static_mask_checks_every_classification_and_preserves_fraction_snapshot():
    values = np.array(
        [[[0.0, 0.49, 0.5, 1.0]], [[0.0, 0.49000001, 0.5, 1.0]]], dtype="f8"
    )
    ds = xr.Dataset(
        {"lsm": (("valid_time", "latitude", "longitude"), values)},
        coords={
            "valid_time": [0, 1],
            "latitude": [20.0],
            "longitude": [0.0, 1.0, 2.0, 3.0],
        },
    )
    output = static_ocean_mask(ds)
    np.testing.assert_array_equal(output.ocean, [[1, 1, 0, 0]])
    np.testing.assert_array_equal(output.land_fraction, values[0])
    changed = ds.copy(deep=True)
    changed.lsm.values[1, 0, 1] = 0.5
    with pytest.raises(ValueError, match="classification changes"):
        static_ocean_mask(changed)
    changed.lsm.values[1, 0, 1] = np.nan
    with pytest.raises(ValueError, match="missing fractions"):
        static_ocean_mask(changed)


def test_grid_mismatch_is_rejected_instead_of_silently_aligned(regression):
    with pytest.raises(ValueError, match="longitude coordinates differ"):
        same_grid(
            regression, regression.assign_coords(longitude=regression.longitude + 0.25)
        )


def test_depth_maximum_containing_cells_masks_missing_and_periodic_longitude():
    values = np.broadcast_to(
        np.arange(1, 13, dtype="f4")[:, None, None], (12, 180, 360)
    ).copy()
    source = xr.Dataset(
        {
            "mld_dr003": (("time", "lat", "lon"), values),
            "mask": (("lat", "lon"), np.ones((180, 360), dtype="i2")),
            "n_obs": (("time", "lat", "lon"), np.ones_like(values, dtype="i4")),
        },
        coords={
            "time": np.arange(12),
            "lat": np.arange(-89.5, 90),
            "lon": np.arange(-179.5, 180),
        },
    )
    source.mld_dr003.attrs["unit"] = "m"
    source.time.attrs["climatology"] = "monthly climatology for controlled test"
    source["mask"].values[110, 180] = 0  # ERA5 20N, 0E has a land donor.
    source.mld_dr003.values[:, 110, 181] = np.nan  # Adjacent missing donor.
    source.mld_dr003.values[11, 110, 182] = -1  # A bad month must not become H.
    source.mld_dr003.values[10, 110, 182] = np.inf
    source.mld_dr003.values[:, 110, 0] = 7  # Dateline donor.
    target = xr.Dataset(
        {"ocean": (("latitude", "longitude"), np.array([[1, 1, 1, 0, 1]], dtype="i1"))},
        coords={"latitude": [20.0], "longitude": [0.0, 1.0, 2.0, 3.0, 180.0]},
    )
    output = fixed_depth(source, target, target)
    np.testing.assert_array_equal(output.H, [[np.nan, np.nan, 10, np.nan, 7]])
    np.testing.assert_array_equal(output.valid_month_count, [[0, 0, 10, 12, 12]])
    assert output.H.dtype == np.float32
    assert output.source_longitude.values[-1] == -179.5
    assert output.source_n_obs_total.values[0, -1] == 12


@pytest.fixture
def damping(regression):
    shape = (4, 3, 3, 5, 4)
    ds = xr.Dataset(
        {
            "gamma": (
                ("case", "lag", "target", "latitude", "longitude"),
                np.arange(np.prod(shape), dtype=float).reshape(shape),
            )
        },
        coords={
            "case": [3, 7, 1, 9],
            "lag": [3, 1, 2],
            "target": [11, 14, 23],
            "latitude": regression.latitude,
            "longitude": regression.longitude,
        },
        attrs={
            "case_labels": json.dumps(
                ["enso_removed", "primary", "detrended", "enso_control"]
            ),
            "sample_counts": json.dumps([20, 21, 22, 23]),
            "target_labels": json.dumps(["net", "radiation", "turbulent"]),
            "convention": "SST leads flux at positive lag; gamma=-cov(Tlead,Q)/cov(Tlead,T)",
        },
    )
    ds.gamma.attrs["units"] = "W m-2 K-1"
    ds.gamma.loc[
        {"case": 7, "lag": 1, "target": 23, "latitude": 30, "longitude": 0}
    ] = -5
    for name in QUALITY_FLAGS:
        ds[name] = (("latitude", "longitude"), np.ones((5, 4)))
    ds.reliable.values[0, 1] = 0
    ds.gamma.loc[
        {"case": 7, "lag": 1, "target": 23, "latitude": 20, "longitude": 0}
    ] = np.nan
    return ds


def test_damping_resolves_labels_and_retains_negative_missing_and_quality(damping):
    selected = selected_damping(damping)
    np.testing.assert_array_equal(
        selected.gamma, damping.gamma.sel(case=7, lag=1, target=23)
    )
    assert selected.gamma.values[0, 0] == -5
    assert np.isnan(selected.gamma.values[1, 0])
    np.testing.assert_array_equal(selected.reliable, damping.reliable)
    assert selected.attrs["selected_case"] == "primary"
    assert selected.attrs["parameter_sample_count"] == 21
    bad = damping.copy()
    bad.attrs["case_labels"] = json.dumps(["a", "b", "c", "d"])
    with pytest.raises(ValueError, match="primary"):
        selected_damping(bad)


def test_independent_coverage_and_intersections_preserve_sign_policy(
    damping, regression
):
    selected = selected_damping(damping)
    selected["H"] = (("latitude", "longitude"), np.ones((5, 4), dtype="f4"))
    selected["valid_month_count"] = (("latitude", "longitude"), np.full((5, 4), 12))
    mask = xr.Dataset(
        {"ocean": (("latitude", "longitude"), np.ones((5, 4)))},
        coords={name: selected[name] for name in ("latitude", "longitude")},
    )
    result = spatial_damping_coverage(selected, regression, mask)
    assert result["damping_nonpositive_ocean"] == 1
    assert result["damping_missing_ocean"] == 1
    assert result["available_intersection"] == 19
    assert result["reliable_intersection"] == 18
    assert result["positive_reliable_intersection"] == 17
    assert (
        "input_valid" not in selected
    )  # Legacy diagnostics cannot set runtime policy.
    assert selected.gamma.values[0, 0] == -5
    assert np.isnan(selected.gamma.values[1, 0])


def test_compression_roundtrip_preserves_physical_precision_and_missing_flags(
    tmp_path, damping, pcs
):
    selected = selected_damping(damping)
    selected.reliable.values[1, 0] = np.nan
    info = write_product(selected, tmp_path / "surface.nc", {"fixture": "test"})
    assert info["maximum_roundtrip_absolute_error"] == 0
    with xr.open_dataset(tmp_path / "surface.nc", engine="netcdf4") as saved:
        np.testing.assert_array_equal(saved.gamma, selected.gamma)
        np.testing.assert_array_equal(saved.reliable, selected.reliable)
        assert saved.gamma.dtype == np.float64
        assert saved.reliable.encoding["dtype"] == np.int8
        assert saved.gamma.encoding["shuffle"] and saved.gamma.encoding["zlib"]
    write_product(monthly_pc(pcs, "north"), tmp_path / "pcs.nc", {"fixture": "test"})
    with xr.open_dataset(tmp_path / "pcs.nc", engine="netcdf4") as saved:
        np.testing.assert_array_equal(saved.standardized_pc, pcs.standardized_pc)
        np.testing.assert_array_equal(saved.time, pcs.time)
        assert saved.standardized_pc.encoding["chunksizes"] == (24, 12)
    unrelated = tmp_path / "unrelated.nc"
    xr.Dataset({"value": ("x", [1])}).to_netcdf(unrelated, engine="netcdf4")
    with pytest.raises(ValueError, match="unrelated"):
        write_product(selected, unrelated, {})


def test_organization_uses_rename_and_does_not_overwrite_or_touch_other_files(tmp_path):
    from ssta_model.data.prepare import FILES

    for name in FILES.values():
        (tmp_path / name).write_bytes(b"unchanged source bytes")
    extra = tmp_path / "other.txt"
    extra.write_text("preserve me")
    before = {key: path.stat().st_ino for key, path in source_paths(tmp_path).items()}
    paths = source_paths(tmp_path)
    organize_raw(tmp_path, paths)
    for key, path in paths.items():
        assert path.stat().st_ino == before[key]
        assert path.read_bytes() == b"unchanged source bytes"
    assert extra.read_text() == "preserve me"
    (tmp_path / FILES["mask"]).write_bytes(b"ambiguous duplicate")
    with pytest.raises(ValueError, match="exactly one"):
        source_paths(tmp_path)
