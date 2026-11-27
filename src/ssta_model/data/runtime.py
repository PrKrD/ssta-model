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


def load_hemisphere(directory, hemisphere, ocean, depth_variant="baseline"):
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
    require(depth_variant in ("baseline", "era5_bilinear"), "Unknown H variant")
    if depth_variant == "era5_bilinear":
        from .prepare import checksum

        path = directory / f"{hemisphere}_surface_h_era5_bilinear.nc"
        with xr.open_dataset(path) as candidate:
            baseline = products["surface"]
            same_grid(baseline, candidate)
            require(
                candidate.H.dims == SPATIAL and candidate.H.attrs.get("units") == "m",
                "Candidate H dimensions/units",
            )
            require(
                candidate.attrs.get("prepared_by")
                == "ssta_model.data.era5_h_candidate",
                "Unknown H candidate provenance",
            )
            require(
                candidate.attrs.get("baseline_sha256")
                == checksum(directory / f"{hemisphere}_surface.nc"),
                "Candidate baseline checksum mismatch",
            )
            require(
                candidate.attrs.get("target_mask_sha256")
                == checksum(directory / "era5_ocean_mask.nc"),
                "Candidate ERA5 mask checksum mismatch",
            )
            require(
                candidate.baseline_input_valid.dims == SPATIAL
                and np.array_equal(
                    candidate.baseline_input_valid, baseline.input_valid
                ),
                "Candidate baseline mask differs",
            )
            wet = extratropics(ocean, hemisphere).ocean.values == 1
            require(
                candidate.era5_ocean.dims == SPATIAL
                and np.array_equal(candidate.era5_ocean.values == 1, wet),
                "Candidate ERA5 ocean mask differs",
            )
            active = baseline.input_valid.values == 1
            values = candidate.H.values
            require(
                np.all(np.isfinite(values[active]) & (values[active] > 0)),
                "Candidate H missing/nonpositive at authorised cells",
            )
            require(np.isnan(values[~wet]).all(), "Candidate H over ERA5 land")
            polar = (
                np.broadcast_to(
                    abs(baseline.latitude.values[:, None]) > 89.5, active.shape
                )
                & active
            )
            require(
                np.array_equal(values[polar], baseline.H.values[polar]),
                "Candidate polar H differs from baseline",
            )
            require(
                candidate.support_method.dims == SPATIAL, "Candidate support dimensions"
            )
            support = candidate.support_method.values
            require(
                np.isin(support, [0, 1, 2]).all()
                and np.array_equal(support == 2, polar),
                "Candidate polar support flags differ",
            )
            require(
                np.all(support[active & ~polar] == 1),
                "Unsupported candidate active cell",
            )
            baseline["H"] = candidate.H.load()
            baseline.attrs["mixed_layer_depth_variant"] = depth_variant
            # baseline.input_valid has already passed the original complete-mask check.
            # Extra finite candidate depths do not participate in domain construction.
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
