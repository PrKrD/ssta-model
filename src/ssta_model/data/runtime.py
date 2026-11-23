"""Validate compact scientific inputs at the simulation boundary; never prepare them."""

import numpy as np
import xarray as xr

from .model_inputs import (
    MODES,
    SPATIAL,
    extratropics,
    monthly_pc,
    require,
    same_grid,
    simulation_mask,
)


def validate_inputs(pcs, regression, surface, ocean, hemisphere):
    """Reject shifted grids, modes, units, masks or altered forcing semantics."""
    pcs = monthly_pc(pcs, hemisphere)
    require(regression.coefficient.dims == ("mode", *SPATIAL), "Coefficient dimensions")
    require(
        np.array_equal(regression.mode, MODES), "Coefficient mode order must be 1–12"
    )
    require(surface.H.dims == SPATIAL, "H dimensions")
    require(surface.input_valid.dims == SPATIAL, "Mask dimensions")
    require(surface.H.attrs.get("units") == "m", "H units must be m")
    require(
        regression.coefficient.attrs.get("units") == "W m-2 per EOF-training PC SD",
        "Unexpected coefficient units",
    )
    for key, expected in {
        "hemisphere": hemisphere,
        "heat_positive": "downward",
        "method": "joint year-round regression",
        "sst_feedback_adjustment": "none",
    }.items():
        require(
            regression.attrs.get(key) == expected,
            f"Regression requires {key}={expected}",
        )
    for key, index in (("first_month", 0), ("last_month", -1)):
        require(regression.attrs.get(key) == pcs.attrs.get(key), f"PC/regression {key}")
        require(
            pcs.attrs.get(key) == str(pcs.time.values[index].astype("datetime64[M]")),
            f"PC {key} differs from dates",
        )
    require(ocean.ocean.dims == SPATIAL, "Ocean mask dimensions")
    require(ocean.land_fraction.dims == SPATIAL, "Land fraction dimensions")
    require(np.isin(ocean.ocean.values, [0, 1]).all(), "Invalid ocean classification")
    require(np.isfinite(ocean.land_fraction.values).all(), "Missing land fractions")
    require(
        np.all((ocean.land_fraction.values >= 0) & (ocean.land_fraction.values <= 1)),
        "Invalid land fractions",
    )
    require(
        np.array_equal(ocean.ocean.values == 1, ocean.land_fraction.values < 0.5),
        "Ocean classification differs from lsm < 0.5",
    )
    same_grid(surface, regression)
    same_grid(surface, extratropics(ocean, hemisphere))
    require(np.isin(surface.input_valid.values, [0, 1]).all(), "Invalid input_valid")
    expected = simulation_mask(
        surface, regression, extratropics(ocean, hemisphere), hemisphere
    )
    require(
        np.array_equal(surface.input_valid, expected), "input_valid differs from inputs"
    )
    require(bool(expected.any()), "No active model cells")
    return pcs


def load_hemisphere(directory, hemisphere, ocean):
    """Load only one hemisphere's fixed fields and small historical PC array."""
    products = {}
    for kind in ("pcs", "regression", "surface"):
        with xr.open_dataset(
            directory / f"{hemisphere}_{kind}.nc", engine="netcdf4"
        ) as ds:
            # Retain only runtime variables; H donor diagnostics are not integration inputs.
            names = {
                "pcs": ["standardized_pc"],
                "regression": ["coefficient"],
                "surface": ["H", "input_valid"],
            }[kind]
            products[kind] = ds[names].load()
    products["pcs"] = validate_inputs(
        products["pcs"], products["regression"], products["surface"], ocean, hemisphere
    )
    return products


def initial_temperature(surface, config, hemisphere):
    """Load only the configured first observed month; no later observations enter the loop."""
    valid = surface.input_valid.values == 1
    if config.get("kind", "scalar") == "scalar":
        return np.where(valid, config["temperature_anomaly_k"], np.nan).astype(
            "f8"
        ), valid
    from pathlib import Path

    with xr.open_dataset(
        Path(config["directory"]) / f"{hemisphere}_era5_ssta.nc", engine="netcdf4"
    ) as ds:
        same_grid(ds, surface)
        require(ds.sst_anomaly.attrs.get("units") == "K", "Initial SST anomaly units")
        months = ds.time.values.astype("datetime64[M]")
        indices = np.flatnonzero(months == np.datetime64(config["month"], "M"))
        require(len(indices) == 1, "Initial ERA5 month missing or duplicated")
        values = ds.sst_anomaly.isel(time=int(indices[0])).values.astype("f8")
    valid = valid & np.isfinite(values)
    require(valid.any(), "No observed initial cells")
    return np.where(valid, values, np.nan), valid
