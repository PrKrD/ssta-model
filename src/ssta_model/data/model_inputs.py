"""Scientific selections for the supplied inputs; no model integration or fitting."""

import json

import numpy as np
import xarray as xr

SPATIAL = ("latitude", "longitude")
MODES = np.arange(1, 13)
QUALITY_FLAGS = (
    "original_ocean",
    "open_water",
    "reliable",
    "lag_stable",
    "weak_sst",
    "weak_or_nonpositive_covariance",
    "negative",
    "large",
    "lag_sensitive",
)


def require(condition, message):
    """Raise a descriptive input error rather than silently substituting data."""
    if not condition:
        raise ValueError(message)


def same_grid(left, right):
    """Reject implicit xarray alignment, truncation or regridding of ERA5 fields."""
    for name in SPATIAL:
        require(name in left.coords and name in right.coords, f"Missing {name}")
        require(
            left[name].dims == right[name].dims == (name,)
            and np.array_equal(left[name].values, right[name].values),
            f"Native ERA5 {name} coordinates differ",
        )


def extratropics(dataset, hemisphere):
    """Inclusive ±20° boundaries, preserving the supplied coordinate ordering."""
    require(hemisphere in ("north", "south"), "Unknown hemisphere")
    lat = dataset.latitude
    return dataset.isel(
        latitude=np.flatnonzero(lat >= 20 if hemisphere == "north" else lat <= -20)
    )


def monthly_pc(dataset, hemisphere):
    """Extract the original 12 standardized PCs without numerical modification."""
    require(dataset.attrs.get("hemisphere") == hemisphere, "PC hemisphere mismatch")
    pc = dataset.standardized_pc
    require(pc.dims == ("time", "mode"), "Expected standardized_pc(time, mode)")
    require(np.array_equal(pc.mode, MODES), "PC mode order must be exactly 1–12")
    require(np.isfinite(pc.values).all(), "PCs contain missing/non-finite values")
    dates = pc.time.values
    require(np.issubdtype(dates.dtype, np.datetime64), "Expected decoded PC dates")
    require(len(dates) > 1 and not np.isnat(dates).any(), "Missing PC dates")
    months = dates.astype("datetime64[M]").astype(np.int64)
    require(
        np.all(np.diff(months) == 1), "PC dates must be monthly, ordered and continuous"
    )
    require(pc.attrs.get("units") == "1", "PCs must be dimensionless")
    require(pc.attrs.get("ddof") == 1, "Expected original sample-SD normalization")
    metadata = {
        key: value
        for key, value in dataset.attrs.items()
        if key
        in {
            "hemisphere",
            "source_variable",
            "first_month",
            "last_month",
            "n_samples",
            "detrended",
            "anomalies",
            "weighting",
            "solver",
        }
        or "sign" in key
    }
    metadata["normalization"] = "Original EOF-training sample SD, ddof=1; unchanged"
    return xr.Dataset(
        {"standardized_pc": pc.variable},
        coords={name: pc[name].variable for name in ("time", "mode")},
        attrs=metadata,
    )


def labelled_coordinate(dataset, dimension, label):
    """Resolve actual coordinate labels, including numeric axes with label metadata."""
    coordinate = dataset[dimension]
    if coordinate.dtype.kind in "OUS":
        labels = coordinate.values.tolist()
    elif f"{dimension}_labels" in dataset.attrs:
        labels = json.loads(dataset.attrs[f"{dimension}_labels"])
    else:
        labels = coordinate.attrs.get("labels", "").split()
    require(len(labels) == coordinate.size, f"Missing or ambiguous {dimension} labels")
    require(
        labels.count(label) == 1, f"Required {dimension} label {label!r} unavailable"
    )
    return coordinate.values[labels.index(label)]


def year_round_array(dataset, name):
    """Select a documented year-round slice, or accept an already annual field."""
    variable = dataset[name]
    for dimension in set(variable.dims) - {"mode", *SPATIAL}:
        try:
            coordinate = labelled_coordinate(dataset, dimension, "year_round")
        except ValueError as error:
            raise ValueError(
                "Year-round coefficients unavailable; seasonal fits are not averaged"
            ) from error
        variable = variable.sel({dimension: coordinate}, drop=True)
    return variable


def year_round_coefficients(dataset, pcs, hemisphere):
    """Select raw joint turbulent coefficients; never average seasonal fits."""
    for key, value in {
        "hemisphere": hemisphere,
        "target": "turbulent",
        "method": "joint",
        "heat_positive": "downward",
    }.items():
        require(dataset.attrs.get(key) == value, f"Regression requires {key}={value}")
    coefficient = year_round_array(dataset, "coefficient")
    require(coefficient.dims == ("mode", *SPATIAL), "Unexpected coefficient dimensions")
    require(np.array_equal(coefficient.mode, pcs.mode), "Regression/PC modes differ")
    require(
        coefficient.attrs.get("units") == "W m-2 per EOF-training PC SD",
        "Unexpected coefficient units",
    )
    require(
        "original EOF-training sample SD" in dataset.attrs.get("pc_scaling", ""),
        "Unknown PC scaling",
    )
    for key in ("first_month", "last_month", "n_samples"):
        require(
            dataset.attrs.get(key) == pcs.attrs.get(key), f"Regression/PC {key} differs"
        )
    require(
        dataset.attrs["n_samples"] == pcs.sizes["time"], "Regression time count differs"
    )
    # The supplied files embed diagnostics from the actual predictor design.
    diagnostics = json.loads(dataset.attrs["predictor_diagnostics"])[hemisphere]
    values = pcs.standardized_pc.values
    np.testing.assert_allclose(values.mean(0), diagnostics["means"], rtol=0, atol=1e-12)
    np.testing.assert_allclose(
        values.var(0, ddof=1), diagnostics["sample_variance"], rtol=0, atol=1e-12
    )
    np.testing.assert_allclose(
        np.corrcoef(values.T), diagnostics["correlation"], rtol=0, atol=1e-12
    )
    output = extratropics(coefficient.to_dataset(), hemisphere)
    output.attrs = {
        "hemisphere": hemisphere,
        "target": "raw latent-plus-sensible turbulent anomalies",
        "method": "joint year-round regression",
        "heat_positive": "downward",
        "forcing_units": "W m-2",
        "forcing": "sum(coefficient * standardized_pc, mode)",
        "intercept_policy": "Omitted intentionally; retained only in untouched raw source",
        "sst_feedback_adjustment": "none",
        "pc_scaling": dataset.attrs["pc_scaling"],
        "first_month": dataset.attrs["first_month"],
        "last_month": dataset.attrs["last_month"],
    }
    return output


def static_ocean_mask(dataset):
    """Check every month in source-aligned spatial tiles, then retain the first field."""
    require(
        dataset.lsm.dims == ("valid_time", *SPATIAL), "Unexpected ERA5 mask dimensions"
    )
    first = dataset.lsm.isel(valid_time=0, drop=True).load()
    maximum_change = 0.0
    # Source chunks span many times; spatial tiles avoid repeated decompression.
    chunks = dataset.lsm.encoding.get("chunksizes")
    dy, dx = chunks[-2:] if chunks else (64, 240)
    for y in range(0, dataset.sizes["latitude"], dy):
        for x in range(0, dataset.sizes["longitude"], dx):
            block = dataset.lsm.isel(
                latitude=slice(y, y + dy), longitude=slice(x, x + dx)
            ).values
            reference = first.isel(
                latitude=slice(y, y + dy), longitude=slice(x, x + dx)
            ).values
            require(np.isfinite(block).all(), "ERA5 mask contains missing fractions")
            require(
                np.all((block >= 0) & (block <= 1)), "ERA5 mask is not a land fraction"
            )
            require(
                np.all((block < 0.5) == (reference < 0.5)),
                "ERA5 ocean classification changes in time",
            )
            maximum_change = max(maximum_change, float(np.max(abs(block - reference))))
    output = xr.Dataset(
        {"land_fraction": first.variable, "ocean": (first < 0.5).astype("i1").variable},
        coords={name: first[name].variable for name in SPATIAL},
    )
    output.ocean.attrs = {"units": "1", "definition": "ERA5 lsm < 0.5; 1=ocean, 0=land"}
    output.attrs = {
        "classification_months_verified": dataset.sizes["valid_time"],
        "snapshot_time": str(dataset.valid_time.values[0]),
        "maximum_fraction_change": maximum_change,
        "policy": "First native fraction snapshot; all monthly classifications verified identical",
    }
    return output


def fixed_depth(source, target, ocean):
    """Piecewise-constant containing-cell transfer; never search for valid neighbours."""
    require(
        source.mld_dr003.dims == ("time", "lat", "lon"), "Unexpected MLD dimensions"
    )
    require(source.sizes["time"] == 12, "Expected 12 monthly climatologies")
    require(
        "monthly climatology" in source.time.attrs.get("climatology", ""),
        "Source must document a monthly climatology",
    )
    require(source.mld_dr003.attrs.get("unit") == "m", "MLD must be in metres")
    require(np.isin(source["mask"], [0, 1]).all(), "Unknown source ocean mask")
    require(np.all(source.n_obs.values >= 0), "Invalid observation counts")
    lat, lon = source.lat.values, source.lon.values
    require(
        np.array_equal(lat, np.arange(-89.5, 90, 1)),
        "Expected supplied 1° MLD latitude centres",
    )
    require(
        np.array_equal(lon, np.arange(-179.5, 180, 1)),
        "Expected supplied 1° MLD longitude centres",
    )
    same_grid(target, ocean)
    require(
        np.all(abs(target.latitude.values) <= 90),
        "Target latitude outside source cells",
    )
    monthly = source.mld_dr003.where(
        (source["mask"] == 1) & np.isfinite(source.mld_dr003) & (source.mld_dr003 > 0)
    )
    depth = monthly.max("time", skipna=True)
    count = monthly.count("time").astype("u1")
    # Source cells cover [-90,90] and [-180,180]; exact edges choose N/E.
    iy = np.minimum(np.floor(target.latitude.values + 90).astype(int), 179)
    ix = np.floor((target.longitude.values + 180) % 360).astype(int)
    take = {
        "lat": xr.DataArray(iy, dims="latitude"),
        "lon": xr.DataArray(ix, dims="longitude"),
    }

    def transfer(array):
        mapped = array.isel(take).drop_vars(["lat", "lon"], errors="ignore")
        return mapped.assign_coords({name: target[name] for name in SPATIAL})

    output = xr.Dataset(
        {
            "H": transfer(depth).where(ocean.ocean == 1),
            "valid_month_count": transfer(count),
            "source_ocean": transfer(source["mask"]),
            "source_n_obs_min": transfer(source.n_obs.min("time")),
            "source_n_obs_total": transfer(source.n_obs.sum("time")),
            "source_latitude": ("latitude", lat[iy]),
            "source_longitude": ("longitude", lon[ix]),
        }
    )
    output.H.attrs = {
        "units": "m",
        "long_name": "Fixed maximum monthly climatological mixed-layer depth",
        "source_variable": "mld_dr003",
        "source_definition": source.mld_dr003.attrs.get("long_name", ""),
        "approximation": "Maximum of valid monthly climatologies; not independently verified late-winter depth",
    }
    for name in (
        "valid_month_count",
        "source_ocean",
        "source_n_obs_min",
        "source_n_obs_total",
    ):
        output[name].attrs = {
            "units": "1",
            "note": "Containing source-cell coverage, independent of ERA5 land classification",
        }
    output.source_latitude.attrs = {
        "units": "degrees_north",
        "long_name": "Donor MLD cell centre",
    }
    output.source_ocean.attrs["definition"] = (
        "Published MLD-source mask: 1=ocean, 0=land; not the ERA5 coastline"
    )
    output.source_longitude.attrs = {
        "units": "degrees_east",
        "long_name": "Donor MLD cell centre",
    }
    output.attrs["depth_regridding"] = (
        "Containing 1° cell; periodic longitude; N/E edge ties; no interpolation, smoothing or valid-neighbour search; source and ERA5 ocean masks required"
    )
    output.attrs.update(
        source_ocean_cells=int((source["mask"] == 1).sum()),
        source_positive_monthly_values=int(monthly.count().item()),
        source_valid_H_cells=int(np.isfinite(depth).sum()),
        source_climatology=source.time.attrs["climatology"],
        source_identity=source.attrs.get("title", ""),
    )
    require(np.all(output.H.values[np.isfinite(output.H.values)] > 0), "Nonpositive H")
    return output


def selected_damping(source):
    """Resolve primary / one-month SST-leading / turbulent by labels and lag value."""
    require(
        "SST leads flux at positive lag" in source.attrs.get("convention", ""),
        "Unknown damping lag convention",
    )
    selection = {
        "case": labelled_coordinate(source, "case", "primary"),
        "target": labelled_coordinate(source, "target", "turbulent"),
        "lag": 1,
    }
    gamma = source.gamma.sel(selection, drop=True)
    require(gamma.dims == SPATIAL, "Unexpected selected damping dimensions")
    require(gamma.attrs.get("units") == "W m-2 K-1", "Unexpected damping units")
    output = xr.Dataset(
        {"gamma": gamma, **{name: source[name] for name in QUALITY_FLAGS}}
    )
    for name in QUALITY_FLAGS:
        values = output[name].values
        require(
            np.isin(values[np.isfinite(values)], [0, 1]).all(), f"Invalid {name} flag"
        )
    output.attrs = {
        "selected_case": "primary",
        "selected_lag_months": 1,
        "selected_target": "turbulent",
        "convention": source.attrs["convention"],
        "damping_status": "Provisional; unchanged, unclipped and unfilled",
        "quality_scope": "Source masks are aggregate primary-case diagnostics; negative spans lag-1 turbulent/net, large and lag_sensitive span multiple lags/targets. They are not redefined for selected gamma.",
    }
    if "sample_counts" in source.attrs:
        counts = json.loads(source.attrs["sample_counts"])
        require(
            len(counts) == source.sizes["case"], "Damping sample-count labels differ"
        )
        index = np.flatnonzero(source.case.values == selection["case"])[0]
        output.attrs["parameter_sample_count"] = int(counts[index])
    return output
