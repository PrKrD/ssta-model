"""Controlled H-only comparisons and layer difference signs on small fixtures."""

import copy
import json

import numpy as np
import pytest
import xarray as xr

from ssta_model.analysis.h_sensitivity import effect_fields, validate_h_pair
from ssta_model.data.diffusion_export import h_comparison_layers


def pair():
    config = {
        "physics": {"horizontal_diffusion": True},
        "parameters": {"kappa_m2_s": 1000.0},
        "initial_conditions": {"kind": "era5"},
        "inputs": {},
        "solver": {"rtol": 1e-12},
        "surface_damping": {"gamma_w_m2_k": 16.0},
        "experiment": {"start_month": "1979-01", "end_month": "1979-03"},
    }
    provenance = {
        "inputs": {"pcs": {"sha256": "same"}},
        "initialization_inputs": {"era5": "same"},
    }
    ds = xr.Dataset(
        {
            "H": (("latitude", "longitude"), [[50.0, 100.0]]),
            "cell_area": (("latitude", "longitude"), [[1.0, 2.0]]),
            "input_valid": (("latitude", "longitude"), [[1, 1]]),
            "initial_sst_anomaly": (("latitude", "longitude"), [[1.0, 2.0]]),
            "forcing_month": ("time", ["1979-02", "1979-03"]),
            "time_bounds": (
                ("time", "bounds"),
                np.array(
                    [["1979-02-01", "1979-03-01"], ["1979-03-01", "1979-04-01"]],
                    dtype="datetime64[ns]",
                ),
            ),
        },
        coords={
            "latitude": [30.0],
            "longitude": [0.0, 180.0],
            "time": np.array(["1979-03-01", "1979-04-01"], dtype="datetime64[ns]"),
        },
        attrs={
            "configuration_json": json.dumps(config),
            "provenance_json": json.dumps(provenance),
        },
    )
    current = ds.copy(deep=True)
    current.H.values[:] = [[60.0, 90.0]]
    config = copy.deepcopy(config)
    config["mixed_layer_depth"] = {"variant": "era5_bilinear"}
    current.attrs["configuration_json"] = json.dumps(config)
    return current, ds


def test_controlled_pair_allows_only_H_change_and_rejects_domain_initial_parameter_changes():
    c, b = pair()
    validate_h_pair(c, b)
    for key in ["initial_sst_anomaly", "input_valid", "time_bounds", "cell_area"]:
        bad = c.copy(deep=True)
        if key == "time_bounds":
            bad[key].values[0, 0] += np.timedelta64(1, "D")
        else:
            bad[key].values[0, 0] += 1
        with pytest.raises(ValueError):
            validate_h_pair(bad, b)
    bad = c.copy(deep=True)
    conf = json.loads(bad.attrs["configuration_json"])
    conf["parameters"]["kappa_m2_s"] = 2000
    bad.attrs["configuration_json"] = json.dumps(conf)
    with pytest.raises(ValueError, match="parameters"):
        validate_h_pair(bad, b)
    bad = c.copy(deep=True)
    prov = json.loads(bad.attrs["provenance_json"])
    prov["inputs"]["pcs"]["sha256"] = "changed"
    bad.attrs["provenance_json"] = json.dumps(prov)
    with pytest.raises(ValueError, match="input differs"):
        validate_h_pair(bad, b)


def test_difference_sign_and_six_export_layers_remain_physical():
    c = np.array([1.0, -2.0])
    b = np.array([0.5, -1.0])
    e = np.array([2.0, -3.0])
    a = np.array([4.0, 5.0])
    np.testing.assert_array_equal(effect_fields(c, b), [0.5, -1.0])
    result = h_comparison_layers(np.stack([c, b, e, a]))
    np.testing.assert_array_equal(result, np.stack([c, b, e, c - e, c - b, a]))
