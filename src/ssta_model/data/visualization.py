"""Offline 5-degree display export from saved SST states; no model/raw-data dependency."""

import calendar
import json
from contextlib import ExitStack
from pathlib import Path

import netCDF4  # Load the backend before NumPy (older supported macOS wheel).
import numpy as np
import xarray as xr

from .model_inputs import SPATIAL, require
from .prepare import checksum


def tile_indices(latitude, longitude):
    """5° half-open centre bins; ±90 and southern −20 belong to the last domain bin.

    Longitude wraps to [-180,180); 180 belongs at -180. Exact internal edges go
    north/east. The southern domain's closed -20 edge stays in [-25,-20]. Native
    cell areas are retained whole, even if their footprints cross a display edge.
    """
    lat = np.asarray(latitude, dtype=float)
    lon = (np.asarray(longitude, dtype=float) + 180) % 360 - 180
    require(np.isfinite(lat).all() and np.all(abs(lat) <= 90), "Invalid latitude")
    require(np.isfinite(lon).all(), "Invalid longitude")
    require(np.all(abs(lat) >= 20), "Tropical source centres are outside the model")
    rows = np.minimum(np.floor((lat + 90) / 5).astype(int), 35)
    rows[lat == -20] = 13
    columns = np.floor((lon + 180) / 5).astype(int)
    return rows[:, None] * 72 + columns[None, :]


def aggregate(values, areas, valid, bins):
    """Return weighted means and finite contributor areas; never fill NaN with zero."""
    values, areas, valid, bins = map(np.asarray, (values, areas, valid, bins))
    require(
        values.shape == areas.shape == valid.shape == bins.shape,
        "Aggregation shapes differ",
    )
    require(valid.dtype == np.bool_, "Validity must be boolean")
    require(
        np.all(np.isfinite(areas[valid]) & (areas[valid] > 0)),
        "Invalid active cell area",
    )
    selected = valid & np.isfinite(values)
    weight = np.bincount(bins[selected], weights=areas[selected], minlength=2592)
    total = np.bincount(
        bins[selected], weights=areas[selected] * values[selected], minlength=2592
    )
    means = np.full(2592, np.nan)
    np.divide(total, weight, out=means, where=weight > 0)
    return means, weight


def validate_output(dataset, hemisphere):
    """Validate saved state geometry, units, masks and Gregorian forcing alignment."""
    require(dataset.sst_anomaly.dims == ("time", *SPATIAL), "SST dimensions")
    require(dataset.sst_anomaly.attrs.get("units") == "K", "SST units must be K")
    for name in ("input_valid", "cell_area"):
        require(dataset[name].dims == SPATIAL, f"Unexpected {name} dimensions")
    require(dataset.cell_area.attrs.get("units") == "m2", "Area units must be m2")
    require(np.isin(dataset.input_valid, [0, 1]).all(), "Invalid model mask")
    for name, units in (("latitude", "degrees_north"), ("longitude", "degrees_east")):
        require(
            dataset[name].dims == (name,), f"Unexpected {name} coordinate dimensions"
        )
        require(dataset[name].attrs.get("units") == units, f"Unexpected {name} units")
    lat, lon = dataset.latitude.values, dataset.longitude.values
    require(
        lat.ndim == lon.ndim == 1 and lat.size > 1 and lon.size > 1,
        "Expected coordinate vectors",
    )
    require(np.all(np.diff(lat) < 0), "Latitude must descend")
    require(
        np.all(np.diff(lon) > 0) and lon[0] >= 0 and lon[-1] < 360,
        "Expected increasing 0–360 longitude",
    )
    require(
        np.all(lat >= 20) if hemisphere == "north" else np.all(lat <= -20),
        "Wrong hemisphere boundary",
    )
    valid = dataset.input_valid.values == 1
    require(valid.any(), "No valid model cells")
    require(
        np.all(
            np.isfinite(dataset.cell_area.values[valid])
            & (dataset.cell_area.values[valid] > 0)
        ),
        "Invalid cell areas",
    )
    require(
        np.issubdtype(dataset.time.dtype, np.datetime64),
        "Expected Gregorian decoded dates",
    )
    times = dataset.time.values.astype("datetime64[s]")
    require(
        np.array_equal(dataset.time.values, times),
        "State timestamp has fractional seconds",
    )
    labels = dataset.forcing_month.values.astype(str)
    require(dataset.forcing_month.dims == ("time",), "Forcing month dimensions")
    require(
        dataset.time_bounds.dims == ("time", "bounds") and dataset.sizes["bounds"] == 2,
        "Time bounds dimensions",
    )
    require(len(times) > 0 and not np.isnat(times).any(), "Missing timestamps")
    months = np.array(labels, dtype="datetime64[M]")
    require(
        np.array_equal(labels, months.astype(str)), "Forcing months must be YYYY-MM"
    )
    require(
        np.all(np.diff(months.astype(int)) == 1), "Forcing months must be continuous"
    )
    starts = months.astype("datetime64[s]")
    ends = (months + 1).astype("datetime64[s]")
    require(np.array_equal(times, ends), "State time must end its forcing month")
    require(
        np.array_equal(
            dataset.time_bounds.values,
            np.column_stack((starts, ends)),
        ),
        "Incorrect forcing interval bounds",
    )
    return valid, tile_indices(lat, lon), months


def export_visualization(run_dir, destination, report_dir=None):
    """Read one native frame per hemisphere at a time and write one compact sequence."""
    run_dir, destination = Path(run_dir), Path(destination)
    report_dir = (
        Path(report_dir) if report_dir is not None else run_dir / "visualization"
    )
    with ExitStack() as stack:
        datasets, masks, bins, source_records = {}, {}, {}, {}
        reference = None
        for hemisphere in ("north", "south"):
            path = run_dir / f"{hemisphere}_sst.nc"
            dataset = stack.enter_context(xr.open_dataset(path, engine="netcdf4"))
            valid, indices, months = validate_output(dataset, hemisphere)
            if reference is not None:
                require(
                    np.array_equal(months, reference),
                    "Hemisphere forcing months differ",
                )
                require(
                    np.array_equal(dataset.longitude, datasets["north"].longitude),
                    "Hemisphere longitudes differ",
                )
                require(
                    dataset.attrs.get("configuration_json")
                    == datasets["north"].attrs.get("configuration_json"),
                    "Hemisphere configurations differ",
                )
            reference = months
            datasets[hemisphere], masks[hemisphere], bins[hemisphere] = (
                dataset,
                valid,
                indices,
            )
            source_records[path.name] = {
                "sha256": checksum(path),
                "bytes": path.stat().st_size,
            }
        counts = sum(np.bincount(bins[h][masks[h]], minlength=2592) for h in datasets)
        occupied = np.flatnonzero(counts)
        cells = []
        for key in occupied:
            south, west = -90 + 5 * int(key // 72), -180 + 5 * int(key % 72)
            cells.append(
                {
                    "id": f"sst-{south}-{west}",
                    "west": west,
                    "east": west + 5,
                    "south": south,
                    "north": south + 5,
                    "nativeCellCount": int(counts[key]),
                }
            )
        frames, checks = [], []
        max_error = 0.0
        for index, month in enumerate(reference):
            combined = np.full(2592, np.nan)
            for h, dataset in datasets.items():
                values = dataset.sst_anomaly.isel(time=index).values.astype("f8")
                require(
                    not np.isfinite(values[~masks[h]]).any(),
                    "SST exists outside model mask",
                )
                require(not np.isinf(values).any(), "Infinite SST in saved output")
                areas = dataset.cell_area.values
                means, weight = aggregate(values, areas, masks[h], bins[h])
                available = weight > 0
                require(
                    not np.isfinite(combined[available]).any(),
                    "Hemisphere tiles overlap",
                )
                combined[available] = means[available]
                # Independent boolean selection + dot product for sampled tiles/months.
                candidates = np.flatnonzero(available)
                for key in candidates[
                    np.linspace(
                        0, len(candidates) - 1, min(12, len(candidates)), dtype=int
                    )
                ]:
                    select = masks[h] & np.isfinite(values) & (bins[h] == key)
                    independent = float(
                        np.dot(values[select], areas[select]) / areas[select].sum()
                    )
                    error = abs(independent - means[key])
                    require(error < 1e-12, "Independent aggregation mismatch")
                    max_error = max(max_error, error)
                    checks.append(
                        {
                            "hemisphere": h,
                            "forcing_month": str(month),
                            "tile_id": cells[int(np.searchsorted(occupied, key))]["id"],
                            "absolute_error_k": error,
                        }
                    )
            frames.append(
                [float(v) if np.isfinite(v) else None for v in combined[occupied]]
            )
        timestamps = [
            str(t.astype("datetime64[s]")) + "Z" for t in datasets["north"].time.values
        ]
        labels = [
            f"{calendar.month_name[int(str(m)[5:])]} {str(m)[:4]} — end-of-month model state"
            for m in reference
        ]
        configuration = json.loads(
            datasets["north"].attrs.get("configuration_json", "{}")
        )
        experiment_name = configuration.get("experiment", {}).get(
            "name", "historical_surface_flux_pilot"
        )
        title = (
            "historical surface-flux pilot"
            if experiment_name == "historical_surface_flux_pilot"
            else experiment_name.replace("_", " ")
        )
        period = f"{str(reference[0])[:4]}–{str(reference[-1])[:4]}"
        payload = {
            "grid": {"id": "sst-pilot-5deg", "cells": cells},
            "sequence": {
                "gridId": "sst-pilot-5deg",
                "name": f"Modelled SST anomaly — {title} ({period})",
                "units": "K",
                "colorScale": "diverging",
                "description": "5° area-weighted model SST; ocean-only rectangular tiles approximate coastlines. Fixed-depth turbulent-forcing pilot with provisional uniform damping; no sea-ice physics or observed SST validation.",
                "timestamps": timestamps,
                "frameLabels": labels,
                "frames": frames,
            },
            "provenance": {
                "inputs": source_records,
                "configuration": configuration,
                "simulation": json.loads(
                    datasets["north"].attrs.get("provenance_json", "{}")
                ),
                "forcingMonths": [str(m) for m in reference],
                "timeBounds": [
                    [str(t.astype("datetime64[s]")) + "Z" for t in pair]
                    for pair in datasets["north"].time_bounds.values
                ],
                "aggregation": "5 degree centre bins; area-weight finite masked ocean values; half-open edges north/east, +90 and southern -20 included in final domain bins; longitude [-180,180). Whole native cell areas retained; no interpolation.",
            },
        }
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(payload, separators=(",", ":"), allow_nan=False) + "\n"
        )
        for name, record in source_records.items():
            require(
                checksum(run_dir / name) == record["sha256"],
                "Source changed during export",
            )
    report_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "cells": len(cells),
        "possible_extratropical_tiles": 2016,
        "frames": len(frames),
        "json_bytes": destination.stat().st_size,
        "json_sha256": checksum(destination),
        "maximum_sample_error_k": max_error,
        "sample_checks": checks,
        "inputs": source_records,
        "netcdf4_version": netCDF4.__version__,
        "aggregation": payload["provenance"]["aggregation"],
        "null_values": sum(v is None for frame in frames for v in frame),
    }
    (report_dir / "export_report.json").write_text(json.dumps(report, indent=2) + "\n")
    (report_dir / "export_report.md").write_text(
        f"# SST display export\n\n{len(cells)} occupied 5° tiles of 2,016 possible; {len(frames)} monthly states. "
        f"JSON: {report['json_bytes']:,} bytes. {len(checks)} independent sampled aggregates; "
        f"maximum difference {max_error:.3g} K.\n\n"
        "Only north_sst.nc and south_sst.nc are read; no raw data, PCs or regressions are required. "
        "Grid order is south-to-north then west-to-east. No tropical tiles or empty masked tiles are emitted. "
        "Each finite value averages valid ocean cells using saved cell_area; missing values are excluded and an empty frame/tile is null. "
        "Whole native areas follow centre membership; rectangular coastal and boundary footprints are approximate, not an exact coastline. "
        "Exact state times, forcing months, bounds, source hashes and model provenance are retained in the JSON. "
        "Native SST is unchanged. See export_report.json for all numerical checks.\n"
    )
    return report


def native_diagnostic_map(run_dir, destination, forcing_month="1980-05"):
    """Plot native SST directly, independently of display aggregation (optional Matplotlib)."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import TwoSlopeNorm

    fields = []
    for h in ("north", "south"):
        with xr.open_dataset(Path(run_dir) / f"{h}_sst.nc", engine="netcdf4") as ds:
            validate_output(ds, h)
            matches = np.flatnonzero(
                ds.forcing_month.values.astype(str) == forcing_month
            )
            require(len(matches) == 1, "Diagnostic month unavailable")
            field = (
                ds.sst_anomaly.isel(time=int(matches[0]))
                .where(ds.input_valid == 1)
                .load()
            )
            field = (
                field.assign_coords(longitude=(field.longitude + 180) % 360 - 180)
                .sortby("longitude")
                .sortby("latitude")
            )
            fields.append(field)
    extent = max(float(abs(f).max()) for f in fields)
    norm = TwoSlopeNorm(vmin=-max(extent, 1e-12), vcenter=0, vmax=max(extent, 1e-12))
    fig, ax = plt.subplots(figsize=(12, 5), layout="constrained")
    ax.set_facecolor("#d0d3d8")
    for field in fields:
        image = ax.pcolormesh(
            field.longitude,
            field.latitude,
            field,
            cmap="RdBu_r",
            norm=norm,
            shading="nearest",
            rasterized=True,
        )
    ax.set(
        xlim=(-180, 180),
        ylim=(-90, 90),
        xlabel="Longitude (° east)",
        ylabel="Latitude (° north)",
        title=f"Modelled SST anomaly · {forcing_month} forcing\nNative 0.25° interval-end state at {str(fields[0].time.values)[:10]} UTC · gray = no model value",
    )
    fig.colorbar(image, ax=ax, label="SST anomaly (K)")
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(destination, dpi=180)
    plt.close(fig)
