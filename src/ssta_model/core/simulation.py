"""Historical monthly time loop and incremental scientific output, one hemisphere at a time."""

import csv
import importlib.metadata
import json
import platform
import subprocess
import time
from pathlib import Path

import netCDF4
import numpy as np
import xarray as xr

from ssta_model.core.configuration import load_configuration
from ssta_model.core.integration import backward_euler
from ssta_model.data.model_inputs import extratropics, require, spherical_cell_areas
from ssta_model.data.prepare import checksum
from ssta_model.data.runtime import initial_temperature, load_hemisphere
from ssta_model.forcing.historical import reconstruct_month
from ssta_model.physics.surface_flux import heat_capacity, surface_tendency


def month_intervals(start, end):
    """Inclusive forcing months, exact Gregorian boundaries and durations in seconds."""
    first, last = np.datetime64(start, "M"), np.datetime64(end, "M")
    require(not (np.isnat(first) or np.isnat(last)) and first <= last, "Invalid period")
    months = np.arange(first, last + 1, dtype="datetime64[M]")
    starts = months.astype("datetime64[s]")
    ends = (months + 1).astype("datetime64[s]")
    seconds = (ends - starts).astype("timedelta64[s]").astype(np.float64)
    return months, starts, ends, seconds


def provenance(config_path, config):
    """Identify every compact input and preserve the preprocessing manifest verbatim."""
    directory = Path(config["inputs"]["directory"])
    manifest_path = directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    files = ["era5_ocean_mask.nc"] + [
        f"{h}_{kind}.nc"
        for h in ("north", "south")
        for kind in ("pcs", "regression", "surface")
    ]
    recorded = {item["filename"]: item["sha256"] for item in manifest["products"]}
    inputs = {}
    for name in files:
        path = directory / name
        digest = checksum(path)
        require(
            recorded.get(name) == digest, f"Preprocessing checksum mismatch: {name}"
        )
        inputs[name] = {"sha256": digest, "bytes": path.stat().st_size}

    code_root = Path(__file__).resolve().parents[3]

    def git(*args):
        return subprocess.check_output(["git", *args], cwd=code_root, text=True).strip()

    try:
        revision, dirty = git("rev-parse", "HEAD"), bool(git("status", "--porcelain"))
    except (OSError, subprocess.CalledProcessError):
        revision, dirty = "unavailable", None
    sources = sorted(Path(__file__).resolve().parents[1].rglob("*.py"))
    script = code_root / "experiments/run_historical_surface_flux.py"
    if script.exists():
        sources.append(script)
    return {
        "configuration": config,
        "experiment_config_sha256": checksum(config_path),
        "damping_config_sha256": checksum(config["surface_damping"]["configuration"]),
        "inputs": inputs,
        "initialization_inputs": {
            f"{h}_era5_ssta.nc": checksum(
                Path(config["initial_conditions"]["directory"]) / f"{h}_era5_ssta.nc"
            )
            for h in ("north", "south")
        }
        if config["initial_conditions"].get("kind") == "era5"
        else {},
        "preprocessing_manifest_sha256": checksum(manifest_path),
        "code_revision": revision,
        "working_tree_dirty": dirty,
        "source_sha256": {str(p.relative_to(code_root)): checksum(p) for p in sources},
        "environment": {
            "python": platform.python_version(),
            **{
                name: importlib.metadata.version(name)
                for name in ("numpy", "xarray", "netCDF4")
            },
        },
        "method": "Backward Euler; monthly piecewise-constant prescribed forcing; float64 state",
        "time_convention": "UTC interval-end state, not monthly mean; forcing_month and time_bounds identify forcing interval",
        "limitations": "Raw turbulent regression proxy, not observed net heat flux; provisional uniform damping; no feedback correction, sea-ice physics or observed SST validation; fixed maximum-monthly-climatology H",
    }, manifest_path


def create_output(path, surface, valid, area, config, metadata, initial=None):
    """Create compressed, monthly chunked output; caller closes even after failure."""
    output = netCDF4.Dataset(path, "w", format="NETCDF4", clobber=False)
    try:
        output.createDimension("time", None)
        output.createDimension("bounds", 2)
        for name in ("latitude", "longitude"):
            output.createDimension(name, surface.sizes[name])
            coordinate = output.createVariable(name, "f8", (name,))
            coordinate[:] = surface[name].values
            coordinate.units = "degrees_north" if name == "latitude" else "degrees_east"
        clock = output.createVariable("time", "i8", ("time",))
        clock.setncatts(
            {
                "units": "seconds since 1970-01-01 00:00:00",
                "calendar": "proleptic_gregorian",
                "standard_name": "time",
                "bounds": "time_bounds",
                "long_name": "Exact integration interval end at 00:00 UTC",
            }
        )
        bounds = output.createVariable("time_bounds", "i8", ("time", "bounds"))
        bounds.setncatts({"units": clock.units, "calendar": clock.calendar})
        output.createVariable(
            "forcing_month", str, ("time",)
        ).long_name = "PC forcing month YYYY-MM"
        dims = ("latitude", "longitude")
        options = dict(zlib=True, complevel=4, shuffle=True)
        output.createVariable("input_valid", "i1", dims, **options)[:] = valid.astype(
            "i1"
        )
        output[
            "input_valid"
        ].definition = (
            "1=active; 0=missing SST throughout run; no local damping or sea-ice gate"
        )
        output.createVariable("H", "f8", dims, fill_value=np.nan, **options)[:] = (
            surface.H.values
        )
        output["H"].setncatts(surface.H.attrs)
        if initial is not None:
            output.createVariable(
                "initial_sst_anomaly", "f8", dims, fill_value=np.nan, **options
            )[:] = initial
            output["initial_sst_anomaly"].units = "K"
        output.createVariable("cell_area", "f8", dims, **options)[:] = area.values
        output["cell_area"].setncatts(area.attrs)
        sst = output.createVariable(
            "sst_anomaly",
            "f4",
            ("time", *dims),
            fill_value=np.nan,
            chunksizes=(1, min(64, valid.shape[0]), min(240, valid.shape[1])),
            **options,
        )
        sst.setncatts(
            {
                "units": "K",
                "long_name": "SST anomaly after integrating forcing_month",
                "cell_methods": "time: point",
                "ancillary_variables": "input_valid",
                "precision": "float32 storage; integration stays float64; per-frame round-trip error recorded in diagnostics",
            }
        )
        output.setncatts(
            {
                "Conventions": "CF-1.10",
                "experiment": config["experiment"]["name"],
                "provenance_json": json.dumps(metadata, sort_keys=True),
                "configuration_json": json.dumps(config, sort_keys=True),
                "equation": "rho*cp*H*dT/dt = F - gamma*T; positive F warms",
                "initial_temperature_anomaly_k": config["initial_conditions"][
                    "temperature_anomaly_k"
                ],
                "initial_time": config["experiment"]["start_month"] + "-01T00:00:00Z",
            }
        )
        output.initial_condition_kind = config["initial_conditions"].get(
            "kind", "scalar"
        )
        if output.initial_condition_kind == "era5":
            output.delncattr("initial_temperature_anomaly_k")
            output.initial_month = config["initial_conditions"]["month"]
            output.initial_time = (
                str(
                    (np.datetime64(output.initial_month, "M") + 1).astype(
                        "datetime64[s]"
                    )
                )
                + "Z"
            )
            output.initialization_definition = "January monthly ERA5 anomaly assigned at the February integration start boundary; initial month excluded from skill"
            output[
                "input_valid"
            ].definition += (
                "; observed-initialised run also requires finite initial ERA5 SSTA"
            )
        return output
    except BaseException:
        output.close()
        raise


def run_hemisphere(products, hemisphere, area, config, metadata, output_dir):
    """Keep fixed beta/H plus one forcing/state pair; never retain a time-space cube."""
    months, starts, ends, durations = month_intervals(
        config["experiment"]["start_month"], config["experiment"]["end_month"]
    )
    observed = config["initial_conditions"].get("kind") == "era5"
    if observed:
        months, starts, ends, durations = (
            a[1:] for a in (months, starts, ends, durations)
        )
        require(
            len(months) > 0,
            "Observed initialisation needs a subsequent integrated month",
        )
    pcs, surface = products["pcs"], products["surface"]
    pc_months = pcs.time.values.astype("datetime64[M]")
    positions = np.searchsorted(pc_months, months)
    require(np.all(positions < pc_months.size), "Requested period exceeds PC record")
    require(
        np.array_equal(pc_months[positions], months),
        "Requested forcing months unavailable",
    )
    temperature, valid = initial_temperature(
        surface, config["initial_conditions"], hemisphere
    )
    depth = surface.H.values.astype("f8")
    beta = products["regression"].coefficient.values
    rho, cp = (config["parameters"][k] for k in ("rho_kg_m3", "cp_j_kg_k"))
    gamma = (
        config["surface_damping"]["gamma_w_m2_k"]
        if config["physics"]["surface_damping"]
        else 0.0
    )
    capacity = heat_capacity(depth[valid], rho, cp)
    weights = area.values[valid]
    rows = []
    path = output_dir / f"{hemisphere}_sst.nc"
    with create_output(
        path, surface, valid, area, config, metadata, temperature
    ) as output:
        for index, (month, start, end, dt, position) in enumerate(
            zip(months, starts, ends, durations, positions)
        ):
            forcing = (
                reconstruct_month(pcs.standardized_pc.values[position], beta)
                if config["physics"]["surface_forcing"]
                else np.zeros(valid.shape, dtype="f8")
            )
            new = backward_euler(temperature, forcing, depth, valid, dt, rho, cp, gamma)
            # Check in flux units (W m-2), using the unrounded float64 state.
            residual = capacity * (
                (new[valid] - temperature[valid]) / dt
                - surface_tendency(new[valid], forcing[valid], capacity, gamma)
            )
            maximum_residual = float(np.max(abs(residual)))
            scale = max(
                1.0,
                float(np.max(abs(forcing[valid]))),
                float(np.max(abs(gamma * new[valid]))),
            )
            require(
                maximum_residual <= 1e-10 * scale,
                "Discrete heat-budget residual exceeds tolerance",
            )
            output["time"][index] = end.astype(np.int64)
            output["time_bounds"][index] = [
                start.astype(np.int64),
                end.astype(np.int64),
            ]
            output["forcing_month"][index] = str(month)
            output["sst_anomaly"][index] = new.astype("f4")
            output.sync()
            restored = np.asarray(
                output["sst_anomaly"][index].filled(np.nan), dtype="f8"
            )
            require(
                np.isnan(restored[~valid]).all(), "Inactive output became nonmissing"
            )
            require(np.isfinite(restored[valid]).all(), "Non-finite active output")
            error = float(np.max(abs(restored[valid] - new[valid])))
            require(
                error <= np.finfo("f4").eps * max(1.0, float(np.max(abs(new[valid])))),
                "Output precision loss exceeds float32 tolerance",
            )
            values = new[valid]
            quantiles = np.quantile(values, [0.01, 0.05, 0.5, 0.95, 0.99])
            rows.append(
                {
                    "forcing_month": str(month),
                    "time_end_utc": str(end) + "Z",
                    "dt_seconds": float(dt),
                    "minimum_k": float(values.min()),
                    "maximum_k": float(values.max()),
                    "area_weighted_mean_k": float(
                        np.sum(values * weights) / weights.sum()
                    ),
                    "spatial_std_k": float(values.std(ddof=0)),
                    **{
                        f"p{p}_k": float(q)
                        for p, q in zip((1, 5, 50, 95, 99), quantiles)
                    },
                    "active_nonfinite": int((~np.isfinite(values)).sum()),
                    "maximum_budget_residual_w_m2": maximum_residual,
                    "maximum_output_error_k": error,
                }
            )
            temperature = new
    with (output_dir / f"{hemisphere}_monthly.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return {
        "active_cells": int(valid.sum()),
        "first_integrated_month": str(months[0]),
        "initialization_month": config["initial_conditions"].get("month")
        if observed
        else None,
        "monthly_steps": len(rows),
        "minimum_k": min(r["minimum_k"] for r in rows),
        "maximum_k": max(r["maximum_k"] for r in rows),
        "final_spatial_std_k": rows[-1]["spatial_std_k"],
        "final": rows[-1],
        "maximum_budget_residual_w_m2": max(
            r["maximum_budget_residual_w_m2"] for r in rows
        ),
        "maximum_output_error_k": max(r["maximum_output_error_k"] for r in rows),
        "active_nonfinite": sum(r["active_nonfinite"] for r in rows),
        "output_bytes": path.stat().st_size,
        "output_sha256": checksum(path),
        "monthly": rows,
    }


def run_experiment(config_path, root=Path(".")):
    """Run both independent hemispheres; refuse to overwrite any existing run directory."""
    started = time.perf_counter()
    root, config_path = Path(root).resolve(), Path(config_path).resolve()
    config = load_configuration(config_path, root)
    metadata, manifest_path = provenance(config_path, config)
    output_dir = Path(config["output"]["directory"])
    # Directory existence is an intentional overwrite guard, including partial runs.
    output_dir.mkdir(parents=True, exist_ok=False)
    (output_dir / "configuration.json").write_text(json.dumps(config, indent=2) + "\n")
    (output_dir / "provenance.json").write_text(json.dumps(metadata, indent=2) + "\n")
    (output_dir / "preprocessing_manifest.json").write_bytes(manifest_path.read_bytes())
    summary = {"status": "running", "configuration": config, "hemispheres": {}}
    summary_path = output_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n")
    try:
        directory = Path(config["inputs"]["directory"])
        with xr.open_dataset(
            directory / "era5_ocean_mask.nc", engine="netcdf4"
        ) as source:
            ocean = source[["ocean", "land_fraction"]].load()
        areas = spherical_cell_areas(ocean)
        pc_dates = None
        for hemisphere in ("north", "south"):
            products = load_hemisphere(directory, hemisphere, ocean)
            dates = products["pcs"].time.values
            if pc_dates is not None:
                require(np.array_equal(pc_dates, dates), "Hemisphere PC dates differ")
            pc_dates = dates.copy()
            summary["hemispheres"][hemisphere] = run_hemisphere(
                products,
                hemisphere,
                extratropics(areas, hemisphere),
                config,
                metadata,
                output_dir,
            )
            del products
        # Inputs must not change during execution.
        for name, record in metadata["inputs"].items():
            require(
                checksum(directory / name) == record["sha256"],
                f"Input changed during run: {name}",
            )
        summary["status"] = "complete"
    except BaseException as error:
        summary.update(status="failed", error=f"{type(error).__name__}: {error}")
        raise
    finally:
        summary["runtime_seconds"] = time.perf_counter() - started
        summary_path.write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")
    return summary
