"""Reproducible, lossless preparation and audit of the seven local NetCDF inputs."""

import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import tempfile
from contextlib import ExitStack
from pathlib import Path

import netCDF4
import numpy as np
import xarray as xr

from .model_inputs import (
    QUALITY_FLAGS,
    SPATIAL,
    extratropics,
    fixed_depth,
    monthly_pc,
    require,
    same_grid,
    selected_damping,
    static_ocean_mask,
    year_round_array,
    year_round_coefficients,
)

FILES = {
    "mask": "ERA5 land–sea mask.nc",
    "depth": "Mixed-layer depth.nc",
    "north_regression": "NH heat-flux regression.nc",
    "north_pc": "Northern Hemisphere PCs.nc",
    "south_regression": "SH heat-flux regression.nc",
    "south_pc": "Southern Hemisphere PCs.nc",
    "damping": "SST damping.nc",
}
PIPELINE = "ssta_model.data.prepare"
BINARY = {*QUALITY_FLAGS, "ocean", "source_ocean", "input_valid"}


def checksum(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def json_value(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    return str(value)


def inventory(path):
    """Metadata only: never load spatial diagnostics just to inventory them."""
    with xr.open_dataset(path, engine="netcdf4") as dataset:
        coordinates = {}
        for name, variable in dataset.coords.items():
            values = variable.values.ravel()
            item = {
                "dimensions": list(variable.dims),
                "dtype": str(variable.dtype),
                "attributes": variable.attrs,
                "first": str(values[0]),
                "last": str(values[-1]),
            }
            if variable.ndim == 1 and variable.dtype.kind in "iufM":
                differences = np.diff(values)
                zero = np.timedelta64(0, "ns") if variable.dtype.kind == "M" else 0
                item["ordering"] = (
                    "increasing"
                    if np.all(differences > zero)
                    else "decreasing"
                    if np.all(differences < zero)
                    else "unordered"
                )
                item["minimum"], item["maximum"] = str(values.min()), str(values.max())
                if variable.dtype.kind in "iuf" and len(differences):
                    item["spacing"] = (
                        float(differences[0])
                        if np.all(differences == differences[0])
                        else None
                    )
            coordinates[name] = item
        return {
            "original_filename": Path(path).name,
            "bytes": Path(path).stat().st_size,
            "sha256": checksum(path),
            "dimensions": dict(dataset.sizes),
            "variables": {
                name: {
                    "dimensions": list(var.dims),
                    "dtype": str(var.dtype),
                    "attributes": var.attrs,
                }
                for name, var in dataset.data_vars.items()
            },
            "coordinates": coordinates,
            "attributes": dataset.attrs,
        }


def source_paths(data_dir):
    """Preflight all names before any move; refuse ambiguous duplicate sources."""
    paths = {}
    for key, name in FILES.items():
        candidates = [data_dir / name, data_dir / "raw" / name]
        found = [path for path in candidates if path.exists()]
        require(len(found) == 1, f"Expected exactly one original file: {name}")
        require(
            found[0].is_file() and not found[0].is_symlink(),
            f"Expected regular file: {name}",
        )
        paths[key] = found[0]
    return paths


def organize_raw(data_dir, paths):
    """Same-filesystem renames, without copying or overwriting any original file."""
    raw = data_dir / "raw"
    raw.mkdir(exist_ok=True)
    for key, source in list(paths.items()):
        destination = raw / source.name
        if source != destination:
            require(not destination.exists(), f"Refusing to overwrite {destination}")
            source.rename(destination)
            paths[key] = destination


def numeric_summary(values):
    values = np.asarray(values)
    finite = values[np.isfinite(values)]
    result = {"finite": int(finite.size), "missing": int(values.size - finite.size)}
    if finite.size:
        result.update(
            {
                "minimum": float(finite.min()),
                "median": float(np.median(finite)),
                "maximum": float(finite.max()),
                "abs_p95": float(np.quantile(abs(finite), 0.95)),
            }
        )
    return result


def encoding_for(dataset):
    encoding = {}
    for name, variable in dataset.variables.items():
        if name in dataset.coords:
            encoding[name] = {"_FillValue": None}
            continue
        sizes = {
            "mode": 12 if "time" in variable.dims else 1,
            "latitude": 64,
            "longitude": 240,
            "time": 120,
        }
        options = {
            "zlib": True,
            "complevel": 4,
            "shuffle": True,
            "chunksizes": tuple(
                min(variable.sizes[dim], sizes.get(dim, 12)) for dim in variable.dims
            ),
        }
        if name in BINARY:
            # Binary flags and NaN have an exact, reversible integer representation.
            options.update(dtype="i1", _FillValue=np.int8(-127))
        elif variable.dtype.kind == "f":
            options["_FillValue"] = np.nan
        else:
            options["_FillValue"] = None
        encoding[name] = options
    return encoding


def write_product(dataset, path, sources):
    """Write atomically and prove lossless decoded-value and missing-mask round trips."""
    if path.exists():
        with xr.open_dataset(path, engine="netcdf4") as previous:
            require(
                previous.attrs.get("prepared_by") == PIPELINE,
                f"Refusing to overwrite unrelated file {path}",
            )
    dataset = dataset.load().copy(deep=False)
    dataset.attrs = {
        **dataset.attrs,
        "prepared_by": PIPELINE,
        "source_sha256": json.dumps(sources, sort_keys=True),
        "precision_policy": "Original scientific float dtypes; no rounding or float64-to-float32 conversion",
    }
    for variable in dataset.variables.values():
        variable.encoding = {}
    handle, temporary = tempfile.mkstemp(dir=path.parent, suffix=".nc")
    os.close(handle)
    try:
        dataset.to_netcdf(
            temporary,
            engine="netcdf4",
            format="NETCDF4",
            encoding=encoding_for(dataset),
        )
        with xr.open_dataset(temporary, engine="netcdf4") as saved:
            require(
                set(saved.variables) == set(dataset.variables),
                "Round-trip variables differ",
            )
            for name, original in dataset.variables.items():
                restored = saved[name]
                require(
                    restored.dims == original.dims,
                    f"Round-trip dimensions differ: {name}",
                )
                np.testing.assert_array_equal(original.values, restored.values)
                if original.dtype.kind == "f" and name not in BINARY:
                    require(
                        original.dtype == restored.dtype,
                        f"Scientific dtype changed: {name}",
                    )
            for name in dataset.data_vars:
                require(
                    saved[name].encoding.get("zlib")
                    and saved[name].encoding.get("shuffle"),
                    "Missing compression filters",
                )
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return {
        "filename": path.name,
        "bytes": path.stat().st_size,
        "sha256": checksum(path),
        "dimensions": dict(dataset.sizes),
        "variables": list(dataset.data_vars),
        "sources": sources,
        "compression": "NetCDF4 zlib level 4, shuffle; spatial chunks 64×240, one mode per chunk; PCs 120×12",
        "precision": "Lossless original scientific floats; binary flags encoded as int8 with -127 missing",
        "maximum_roundtrip_absolute_error": 0.0,
        "maximum_roundtrip_relative_error": 0.0,
        "selection": dataset.attrs,
        "coordinates": {
            name: {
                "first": str(dataset[name].values[0]),
                "last": str(dataset[name].values[-1]),
            }
            for name in dataset.dims
        },
    }


def forcing_audit(raw, coefficients, pcs, hemisphere):
    """Evaluate means analytically and small reconstructions, never a global time cube."""
    beta = coefficients.coefficient.values
    valid = np.isfinite(beta).all(axis=0)
    means = pcs.standardized_pc.values.mean(0)
    temporal_mean = np.sum(beta * means[:, None, None], axis=0)
    intercept = extratropics(year_round_array(raw, "intercept"), hemisphere).values
    indices = np.flatnonzero(valid.ravel())
    sample = (
        indices[np.linspace(0, len(indices) - 1, min(32, len(indices)), dtype=int)]
        if len(indices)
        else []
    )
    if len(sample):
        raw_beta = extratropics(year_round_array(raw, "coefficient"), hemisphere)
        raw_values = raw_beta.values.reshape(12, -1)[:, sample]
        original = pcs.standardized_pc.values @ raw_values
        compact = pcs.standardized_pc.values @ beta.reshape(12, -1)[:, sample]
        np.testing.assert_array_equal(original, compact)
        mean_error = float(np.max(abs(compact.mean(0) - temporal_mean.ravel()[sample])))
    else:
        mean_error = 0.0
    return {
        "units": "W m-2",
        "positive": "downward",
        "intercept": numeric_summary(intercept[valid]),
        "without_intercept_temporal_mean": numeric_summary(temporal_mean[valid]),
        "fitted_temporal_mean": numeric_summary((temporal_mean + intercept)[valid]),
        "sample_reconstruction_max_error": 0.0,
        "sample_temporal_mean_roundoff": mean_error,
        "sample_cells": len(sample),
        "offset_policy": "Model minus fitted reconstruction = -original intercept at every time; no new intercept or PC centring applied",
    }


def coverage(surface, coefficients, ocean):
    """Independent counts plus explicitly distinguished support intersections."""
    wet = ocean.ocean.values == 1
    h = np.isfinite(surface.H.values) & (surface.H.values > 0)
    gamma = surface.gamma.values
    finite = np.isfinite(gamma)
    regression = np.isfinite(coefficients.coefficient.values).all(0)
    reliable = surface.reliable.values == 1
    open_water = surface.open_water.values == 1
    available = wet & h & finite & regression & open_water
    result = {
        "domain_cells": wet.size,
        "ocean_cells": int(wet.sum()),
        "H_valid_ocean": int((wet & h).sum()),
        "H_partial_month_coverage_ocean": int(
            (wet & h & (surface.valid_month_count.values < 12)).sum()
        ),
        "coefficient_valid_ocean": int((wet & regression).sum()),
        "damping_finite_ocean": int((wet & finite).sum()),
        "damping_positive_ocean": int((wet & finite & (gamma > 0)).sum()),
        "damping_nonpositive_ocean": int((wet & finite & (gamma <= 0)).sum()),
        "damping_missing_ocean": int((wet & ~finite).sum()),
        "damping_finite_unreliable_ocean": int((wet & finite & ~reliable).sum()),
        "available_intersection": int(available.sum()),
        "reliable_intersection": int((available & reliable).sum()),
        "positive_reliable_intersection": int(
            (available & reliable & (gamma > 0)).sum()
        ),
        "damping_distribution_ocean": numeric_summary(gamma[wet]),
        "H_distribution_ocean": numeric_summary(surface.H.values[wet]),
        "source_flags_ocean": {
            name: {
                "true": int((wet & (surface[name].values == 1)).sum()),
                "missing": int((wet & ~np.isfinite(surface[name].values)).sum()),
            }
            for name in QUALITY_FLAGS
        },
    }
    surface["input_valid"] = (SPATIAL, available.astype("i1"))
    surface.input_valid.attrs = {
        "units": "1",
        "definition": "ERA5 ocean AND positive finite H AND all 12 finite coefficients AND finite gamma AND source open_water; reliability/sign flags remain separate",
    }
    return result


def write_report(manifest, path):
    """Human-readable evidence, backed by the complete machine-readable inventory."""
    pc_inventory = manifest["originals"]["north_pc"]
    pc_first = pc_inventory["coordinates"]["time"]["first"][:7]
    pc_last = pc_inventory["coordinates"]["time"]["last"][:7]
    mask_coordinates = manifest["originals"]["mask"]["coordinates"]
    lines = [
        "# Prepared model input report",
        "",
        "No model integration, fitting, stochastic forcing or frontend output was performed.",
        "Original files remain unchanged under raw/. Sizes below are logical file bytes, not disk blocks.",
        "",
        "## Original inventory",
        "",
        "| File | Bytes | Dimensions | Variables |",
        "| --- | ---: | --- | --- |",
    ]
    for item in manifest["originals"].values():
        dimensions = ", ".join(f"{k}={v}" for k, v in item["dimensions"].items())
        lines.append(
            f"| {item['original_filename']} | {item['bytes']:,} | {dimensions} | {', '.join(item['variables'])} |"
        )
    lines += [
        "",
        "Full attributes, coordinate bounds/order, original checksums and every selection are in manifest.json.",
        "",
        "## Compact products",
        "",
        "| Product | Bytes | Variables |",
        "| --- | ---: | --- |",
    ]
    for item in manifest["products"]:
        lines.append(
            f"| {item['filename']} | {item['bytes']:,} | {', '.join(item['variables'])} |"
        )
    totals = manifest["totals"]
    lines += [
        "",
        f"Original: **{totals['original_bytes']:,} bytes**; compact NetCDF working set: **{totals['processed_netcdf_bytes']:,} bytes**; reduction **{totals['working_set_reduction_percent']:.2f}%**.",
        "Originals are retained: this is working-set reduction, **not actual disk space freed**. Processed files occupy additional disk space.",
        "",
        "## Scientific policy and numerical validation",
        "",
        "- F' = sum(beta_k PC_k), separately for north and south, modes 1–12. Raw year-round joint latent-plus-sensible coefficients; W m⁻², positive downward. No intercept, feedback adjustment, EOF refitting or PC rescaling.",
        f"- PC dates are identical continuous monthly coordinates, {pc_first}–{pc_last} ({pc_inventory['dimensions']['time']} months). Their original means and sample SDs are recorded below, not changed.",
        f"- Spatial outputs use native ERA5 coordinates: latitude {mask_coordinates['latitude']['first']} to {mask_coordinates['latitude']['last']}°, spacing {mask_coordinates['latitude']['spacing']}°; longitude {mask_coordinates['longitude']['first']} to {mask_coordinates['longitude']['last']}°, spacing {mask_coordinates['longitude']['spacing']}°. North includes +20°; south includes −20°; tropics are absent from hemispheric products.",
        f"- All {manifest['mask']['classification_months_verified']} mask classifications match lsm < 0.5. First fractional field retained; maximum monthly fractional difference {manifest['mask']['maximum_fraction_change']:.9g}.",
        "- H uses the maximum positive finite monthly source climatology in source ocean cells. Containing 1° cell transfer, periodic longitude, N/E edge ties, both source and ERA5 ocean masks. No interpolation, smoothing or valid-neighbour filling. Missing H stays missing; coverage counts and donor coordinates are preserved.",
        "- H is a maximum-of-monthly-climatologies approximation, not independently verified late-winter depth. n_obs describes source profile coverage, not an additional depth validity threshold.",
        "- Damping: primary, lag 1 (SST leads flux), turbulent; W m⁻² K⁻¹. Original quality masks retained losslessly. Negative/missing/unreliable values are not clipped, replaced or filled. Source negative/large/lag-sensitivity flags aggregate multiple targets/lags, not just the selected gamma.",
        "- zlib level 4 + shuffle; original scientific floating-point precision. No float64→float32 conversion, so conversion error is zero. Binary flags use exact int8 encoding with an explicit missing sentinel.",
        "- Every output variable, coordinate and missing mask passed exact decoded-value round-trip checks. PCs and cropped coefficients match source values exactly. Sample forcing reconstructions match exactly; global temporal means are evaluated analytically without storing forcing cubes.",
        "",
        "## Extratropical coverage",
        "",
        "Counts are cells, not area fractions. Component counts are independent; intersections are explicitly separate.",
        "",
    ]
    for hemisphere, audit in manifest["hemispheres"].items():
        lines += [
            f"### {hemisphere.title()}",
            "",
            "| Check | Count |",
            "| --- | ---: |",
        ]
        for key, value in audit["coverage"].items():
            if isinstance(value, int):
                lines.append(f"| {key} | {value:,} |")
        forcing = audit["forcing"]
        lines += [
            "",
            f"PC maximum absolute mean: {audit['pc_max_abs_mean']:.6g}; sample SD range: {audit['pc_sample_sd_min']:.12g}–{audit['pc_sample_sd_max']:.12g}.",
            f"Original intercept: {json.dumps(forcing['intercept'])} W m⁻².",
            f"No-intercept temporal mean: {json.dumps(forcing['without_intercept_temporal_mean'])} W m⁻².",
            f"Fitted temporal mean including intercept: {json.dumps(forcing['fitted_temporal_mean'])} W m⁻².",
            "Omission shifts the fitted reconstruction by minus the raw intercept. The reported values quantify any nonzero mean or offset; no PC or coefficient recentering is performed.",
            f"Selected damping distribution: {json.dumps(audit['coverage']['damping_distribution_ocean'])} W m⁻² K⁻¹.",
            "",
        ]
    lines += [
        "## Limitations",
        "",
        "Damping remains provisional. The available, reliable and positive-reliable intersections differ; no future model acceptance policy is silently imposed. Unreliable and nonpositive values remain inspectable. Native source masks and missing data limit H coverage, especially near coasts/poles; no filling increases coverage. Raw provenance comes from supplied files plus an inspection of the previous workflow definitions; the old repository is not a runtime dependency.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def prepare_inputs(data_dir):
    """Inspect, organize, prepare, losslessly validate, and report local inputs."""
    data_dir = Path(data_dir).resolve()
    paths = source_paths(data_dir)
    print(
        "Inventorying all original files before moving or processing them", flush=True
    )
    originals = {key: inventory(path) for key, path in paths.items()}
    output = data_dir / "processed"
    output.mkdir(exist_ok=True)
    if (output / "manifest.json").exists():
        previous = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
        require(
            previous.get("pipeline") == PIPELINE,
            "Refusing to overwrite unrelated manifest",
        )
    elif (output / "report.md").exists():
        raise ValueError("Refusing to overwrite a report without our pipeline manifest")
    organize_raw(data_dir, paths)
    manifest = {
        "schema_version": 1,
        "pipeline": PIPELINE,
        "originals": originals,
        "products": [],
        "hemispheres": {},
        "environment": {
            "python": platform.python_version(),
            "netcdf_c": netCDF4.__netcdf4libversion__,
            "hdf5": netCDF4.__hdf5libversion__,
            **{
                name: importlib.metadata.version(name)
                for name in ("numpy", "xarray", "netCDF4")
            },
        },
        "pipeline_source_sha256": {
            name: checksum(Path(__file__).with_name(name))
            for name in ("model_inputs.py", "prepare.py")
        },
    }
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False
    )
    manifest["git_revision_at_preparation"] = revision.stdout.strip()
    status = subprocess.run(
        ["git", "status", "--porcelain"], capture_output=True, text=True, check=False
    )
    manifest["git_working_tree_dirty"] = bool(status.stdout.strip())

    def save(dataset, filename, keys):
        sources = {FILES[key]: originals[key]["sha256"] for key in keys}
        manifest["products"].append(write_product(dataset, output / filename, sources))

    with ExitStack() as stack:
        raw = {
            key: stack.enter_context(xr.open_dataset(path, engine="netcdf4"))
            for key, path in paths.items()
        }
        for key in ("north_regression", "south_regression", "damping"):
            same_grid(raw["mask"], raw[key])
        pcs = {
            hemisphere: monthly_pc(raw[f"{hemisphere}_pc"], hemisphere)
            for hemisphere in ("north", "south")
        }
        np.testing.assert_array_equal(pcs["north"].time, pcs["south"].time)
        mask = static_ocean_mask(raw["mask"])
        manifest["mask"] = mask.attrs
        save(mask, "era5_ocean_mask.nc", ["mask"])
        damping = selected_damping(raw["damping"])
        np.testing.assert_array_equal(mask.ocean.values, damping.original_ocean.values)
        depth = fixed_depth(raw["depth"], mask, mask)
        for hemisphere in ("north", "south"):
            print(f"Preparing {hemisphere} inputs", flush=True)
            regression = raw[f"{hemisphere}_regression"]
            np.testing.assert_array_equal(
                regression.ocean_mask.values, mask.ocean.values
            )
            coefficients = year_round_coefficients(
                regression, pcs[hemisphere], hemisphere
            )
            surface = xr.merge(
                [extratropics(depth, hemisphere), extratropics(damping, hemisphere)],
                join="exact",
            )
            surface.attrs = {**depth.attrs, **damping.attrs, "hemisphere": hemisphere}
            domain_mask = extratropics(mask, hemisphere)
            same_grid(surface, coefficients)
            counts = coverage(surface, coefficients, domain_mask)
            pc_values = pcs[hemisphere].standardized_pc.values
            manifest["hemispheres"][hemisphere] = {
                "coverage": counts,
                "forcing": forcing_audit(
                    regression, coefficients, pcs[hemisphere], hemisphere
                ),
                "pc_max_abs_mean": float(abs(pc_values.mean(0)).max()),
                "pc_sample_sd_min": float(pc_values.std(0, ddof=1).min()),
                "pc_sample_sd_max": float(pc_values.std(0, ddof=1).max()),
            }
            save(pcs[hemisphere], f"{hemisphere}_pcs.nc", [f"{hemisphere}_pc"])
            save(
                coefficients,
                f"{hemisphere}_regression.nc",
                [f"{hemisphere}_regression"],
            )
            save(
                surface,
                f"{hemisphere}_surface.nc",
                ["mask", "depth", "damping", f"{hemisphere}_regression"],
            )
    # Hash originals after all reads/moves, proving scientific bytes were untouched.
    for key, path in paths.items():
        require(
            checksum(path) == originals[key]["sha256"], f"Raw source changed: {path}"
        )
    original_bytes = sum(item["bytes"] for item in originals.values())
    processed_bytes = sum(item["bytes"] for item in manifest["products"])
    manifest["totals"] = {
        "original_bytes": original_bytes,
        "processed_netcdf_bytes": processed_bytes,
        "working_set_reduction_percent": 100 * (1 - processed_bytes / original_bytes),
        "raw_bytes_deleted": 0,
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, default=json_value, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    write_report(manifest, output / "report.md")
    print(json.dumps(manifest["totals"], indent=2), flush=True)
    return manifest
