"""Monthly SST reference anomalies, preserving the supplied grid and warming signal."""

import json
from pathlib import Path

import netCDF4
import numpy as np
import xarray as xr

from .model_inputs import extratropics, require, same_grid
from .prepare import checksum


def monthly_anomalies(values, months, reference, ocean):
    """Float64 calendar-month climatology/anomalies; missing samples never become zero."""
    values = np.asarray(values, dtype="f8")
    require(values.shape[0] == len(months) == len(reference), "Time lengths differ")
    require(values.shape[1:] == ocean.shape, "Ocean/grid shapes differ")
    values = np.where(ocean[None] & np.isfinite(values), values, np.nan)
    climatology = np.full((12, *ocean.shape), np.nan)
    counts = np.zeros(climatology.shape, dtype="i2")
    month_numbers = months.astype(int) % 12
    for m in range(12):
        block = values[reference & (month_numbers == m)]
        counts[m] = np.isfinite(block).sum(axis=0)
        np.divide(
            np.nansum(block, axis=0), counts[m], out=climatology[m], where=counts[m] > 0
        )
    return values - climatology[month_numbers], climatology, counts


def inspect_sst(dataset, mask):
    """Identify SST by metadata, then require the actually supplied native grid."""
    candidates = [
        name
        for name, v in dataset.data_vars.items()
        if v.attrs.get("long_name", "").lower() == "sea surface temperature"
        or v.attrs.get("standard_name") == "sea_surface_temperature"
    ]
    require(len(candidates) == 1, "Expected one metadata-identified SST variable")
    sst = dataset[candidates[0]]
    time_dims = [
        d
        for d in sst.dims
        if d in dataset.coords and np.issubdtype(dataset[d].dtype, np.datetime64)
    ]
    require(len(time_dims) == 1, "Expected one decoded monthly time dimension")
    require(
        sst.dims == (time_dims[0], "latitude", "longitude"), "Unexpected SST dimensions"
    )
    same_grid(dataset, mask)
    require(
        sst.attrs.get("units") in ("K", "degC", "degree_Celsius"), "Unknown SST units"
    )
    months = dataset[time_dims[0]].values.astype("datetime64[M]")
    require(
        not np.isnat(months).any() and np.all(np.diff(months.astype(int)) == 1),
        "SST must be continuous ordered months",
    )
    return sst, time_dims[0], months


def prepare_era5(source_path, processed_dir):
    """Process source-aligned spatial tiles: the supplied file has 149-month chunks.

    A monthly full-map read repeatedly decompresses large time chunks. Spatial
    tiles keep memory bounded while reading each tile's historical block once.
    No previous raw inputs or preprocessing workflow are accessed.
    """
    source_path, processed_dir = Path(source_path), Path(processed_dir)
    source_hash = checksum(source_path)
    with (
        xr.open_dataset(source_path, engine="netcdf4") as ds,
        xr.open_dataset(processed_dir / "era5_ocean_mask.nc", engine="netcdf4") as mask,
        xr.open_dataset(processed_dir / "north_pcs.nc", engine="netcdf4") as pc,
    ):
        sst, time_dim, source_months = inspect_sst(ds, mask)
        pc_months = pc.time.values.astype("datetime64[M]")
        first = max(np.datetime64("1979-01"), source_months[0], pc_months[0])
        last = min(source_months[-1], pc_months[-1])
        require(
            first == np.datetime64("1979-01"), "January 1979 SST and PCs are required"
        )
        selection = np.flatnonzero((source_months >= first) & (source_months <= last))
        months = source_months[selection]
        # Prefer all requested 47 complete reference years, otherwise all complete common years.
        years = months.astype("datetime64[Y]").astype(int) + 1970
        complete = [
            int(y) for y in np.unique(years) if np.count_nonzero(years == y) == 12
        ]
        require(len(complete) > 0, "No complete reference years")
        ref_first, ref_last = (
            (1979, 2025)
            if all(y in complete for y in range(1979, 2026))
            else (complete[0], complete[-1])
        )
        reference = (years >= ref_first) & (years <= ref_last)
        metadata = {
            "source": str(source_path),
            "source_sha256": source_hash,
            "source_variable": sst.name,
            "source_units": sst.attrs["units"],
            "source_period": [str(source_months[0]), str(source_months[-1])],
            "period": [str(months[0]), str(months[-1])],
            "months": len(months),
            "climatology_years": [ref_first, ref_last],
            "regridding": "none; exact native coordinate equality",
            "definition": "SST minus calendar-month mean; no detrending or smoothing; ERA5 lsm<0.5 and inclusive extratropics",
            "source_attributes": ds.attrs,
            "source_sst_attributes": sst.attrs,
            "maximum_storage_error_k": 0.0,
        }
        chunks = sst.encoding.get("chunksizes") or (1, 64, 240)
        for h in ("north", "south"):
            grid = extratropics(mask, h)
            wet = grid.ocean.values == 1
            lat_indices = np.flatnonzero(
                np.isin(mask.latitude.values, grid.latitude.values)
            )
            path = processed_dir / f"{h}_era5_ssta.nc"
            require(not path.exists(), f"Refusing to overwrite {path}")
            with netCDF4.Dataset(path, "w", format="NETCDF4", clobber=False) as out:
                for name, size in (
                    ("time", len(months)),
                    ("month", 12),
                    ("latitude", len(lat_indices)),
                    ("longitude", grid.sizes["longitude"]),
                ):
                    out.createDimension(name, size)
                for name, values in (
                    ("latitude", grid.latitude.values),
                    ("longitude", grid.longitude.values),
                ):
                    v = out.createVariable(name, "f8", (name,))
                    v[:] = values
                    v.units = grid[name].attrs["units"]
                v = out.createVariable("time", "i8", ("time",))
                v[:] = months.astype("datetime64[s]").astype("i8")
                v.units = "seconds since 1970-01-01 00:00:00"
                v.calendar = "proleptic_gregorian"
                out.createVariable("month", "i1", ("month",))[:] = np.arange(1, 13)
                options = dict(zlib=True, complevel=4, shuffle=True, fill_value=np.nan)
                out.createVariable(
                    "sst_anomaly",
                    "f8",
                    ("time", "latitude", "longitude"),
                    chunksizes=(
                        1,
                        min(64, len(lat_indices)),
                        min(240, grid.sizes["longitude"]),
                    ),
                    **options,
                ).units = "K"
                out.createVariable(
                    "sst_climatology",
                    "f8",
                    ("month", "latitude", "longitude"),
                    **options,
                ).units = "K"
                out.createVariable(
                    "climatology_count",
                    "i2",
                    ("month", "latitude", "longitude"),
                    zlib=True,
                )
                out.createVariable("ocean", "i1", ("latitude", "longitude"), zlib=True)[
                    :
                ] = wet
                out.setncatts(
                    {
                        "prepared_by": "ssta_model.data.era5",
                        "hemisphere": h,
                        "provenance_json": json.dumps(metadata, default=str),
                    }
                )
                active_missing = 0
                for y in range(0, len(lat_indices), chunks[-2]):
                    iy = lat_indices[y : y + chunks[-2]]
                    for x in range(0, grid.sizes["longitude"], chunks[-1]):
                        xs = slice(x, min(x + chunks[-1], grid.sizes["longitude"]))
                        block = sst.isel(
                            {
                                time_dim: slice(selection[0], selection[-1] + 1),
                                "latitude": slice(iy[0], iy[-1] + 1),
                                "longitude": xs,
                            }
                        ).values.astype("f8")
                        if sst.attrs["units"] != "K":
                            block += 273.15
                        a, c, n = monthly_anomalies(
                            block, months, reference, wet[y : y + len(iy), xs]
                        )
                        out["sst_anomaly"][:, y : y + len(iy), xs] = a
                        out["sst_climatology"][:, y : y + len(iy), xs] = c
                        out["climatology_count"][:, y : y + len(iy), xs] = n
                        active_missing += int(
                            np.count_nonzero(
                                ~np.isfinite(a[:, wet[y : y + len(iy), xs]])
                            )
                        )
                out.missing_ocean_samples = active_missing
            print(f"Prepared {h} ERA5 SSTA: {len(months)} months", flush=True)
    require(
        checksum(source_path) == source_hash, "Source SST changed during processing"
    )
    metadata["products"] = {
        f"{h}_era5_ssta.nc": {
            "sha256": checksum(processed_dir / f"{h}_era5_ssta.nc"),
            "bytes": (processed_dir / f"{h}_era5_ssta.nc").stat().st_size,
        }
        for h in ("north", "south")
    }
    (processed_dir / "era5_ssta_manifest.json").write_text(
        json.dumps(metadata, indent=2, default=str) + "\n"
    )
    return metadata
