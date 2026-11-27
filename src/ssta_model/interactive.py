"""Fixed local damping experiment and display export; no new model physics."""

import json
import math
import os
import subprocess
import sys
from pathlib import Path

DEFAULT_GAMMA = 16.072239642825945


def validate_gamma(value):
    if (
        type(value) not in (int, float)
        or not math.isfinite(value)
        or not 0 <= value <= 40
    ):
        raise ValueError(
            "Surface damping must be a finite number between 0 and 40 W m-2 K-1"
        )
    return float(value)


def request_configuration(root, folder, gamma):
    """Only damping and the unique output path differ from the fixed template."""
    gamma = validate_gamma(gamma)
    template = (root / "configs/interactive_damping.toml").read_text()
    output = (folder / "model").relative_to(root).as_posix()
    return template.replace(
        f"gamma_w_m2_k = {DEFAULT_GAMMA}", f"gamma_w_m2_k = {gamma!r}"
    ).replace("runs/interactive_damping/REQUEST/model", output)


def execute_run(root, folder, gamma):
    """One child process owns all scientific I/O and runs with one BLAS thread."""
    required = ["era5_ocean_mask.nc", "manifest.json"] + [
        f"{h}_{kind}.nc"
        for h in ("north", "south")
        for kind in (
            "pcs",
            "regression",
            "surface",
            "era5_ssta",
            "surface_h_era5_bilinear",
        )
    ]
    missing = [
        str(root / "data/processed" / name)
        for name in required
        if not (root / "data/processed" / name).is_file()
    ]
    for path in (
        root / "configs/interactive_damping.toml",
        root / "configs/surface_damping.toml",
        root / "frontend/public/data/era5_comparison/manifest.json",
    ):
        if not path.is_file():
            missing.append(str(path))
    if missing:
        raise FileNotFoundError("Missing required local inputs: " + ", ".join(missing))
    config = folder / "request.toml"
    config.write_text(request_configuration(root, folder, gamma))
    log = folder / "execution.log"
    environment = {
        **os.environ,
        "OPENBLAS_NUM_THREADS": "1",
        "OMP_NUM_THREADS": "1",
        "VECLIB_MAXIMUM_THREADS": "1",
    }
    with log.open("w") as stream:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "ssta_model.interactive",
                str(root),
                str(config),
                str(folder / "display"),
            ],
            cwd=root,
            env=environment,
            stdout=stream,
            stderr=subprocess.STDOUT,
            check=False,
        )
    if result.returncode:
        raise RuntimeError("Simulation failed: " + log.read_text()[-4000:])


def export_interactive(run_dir, grid_manifest, destination, gamma):
    """Existing half-degree geometry and native ocean-area aggregation, one array/month."""
    from contextlib import ExitStack

    import numpy as np
    import xarray as xr

    from ssta_model.data.comparison_export import comparison_bins
    from ssta_model.data.diffusion_export import aggregate_fields
    from ssta_model.data.model_inputs import require
    from ssta_model.data.prepare import checksum

    grid = json.loads(grid_manifest.read_text())["grid"]
    cells = grid["cells"]
    keys = np.array([int(cell["id"].removeprefix("comparison-")) for cell in cells])
    require(
        len(set(keys)) == len(keys) and np.all((keys >= 0) & (keys < 259200)),
        "Invalid existing display grid",
    )
    for key, cell in zip(keys, cells):
        require(
            cell["west"] == -180 + (key % 720) / 2
            and cell["east"] == cell["west"] + 0.5
            and cell["south"] == -90 + (key // 720) / 2
            and cell["north"] == cell["south"] + 0.5,
            "Existing display cell bounds mismatch",
        )
    destination.mkdir(parents=True, exist_ok=False)
    (destination / "frames").mkdir()
    hashes = {}
    frames = []
    labels = []
    timestamps = []
    maximum_error = 0.0
    with ExitStack() as stack:
        data = {}
        bins = {}
        months = None
        for h in ("north", "south"):
            path = run_dir / f"{h}_sst.nc"
            hashes[str(path)] = checksum(path)
            ds = stack.enter_context(xr.open_dataset(path))
            configuration = json.loads(ds.attrs["configuration_json"])
            require(
                configuration["surface_damping"]["gamma_w_m2_k"] == gamma,
                "Solver damping differs from selected gamma",
            )
            current = [ds.attrs["initial_month"], *ds.forcing_month.values.astype(str)]
            require(
                current
                == list(
                    np.arange("1979-01", "1981-01", dtype="datetime64[M]").astype(str)
                ),
                "Interactive period must have 24 calendar states",
            )
            require(
                months is None or current == months,
                "Interactive hemisphere months differ",
            )
            months = current
            data[h] = ds
            bins[h] = comparison_bins(ds.latitude.values, ds.longitude.values)
            active_keys = np.unique(bins[h][ds.input_valid.values == 1])
            require(
                np.isin(active_keys, keys).all(),
                "Historical display grid omits active model cells",
            )
        for index, month in enumerate(months):
            values = np.full(259200, np.nan)
            for h, ds in data.items():
                field = (
                    ds.initial_sst_anomaly.values
                    if index == 0
                    else ds.sst_anomaly.isel(time=index - 1).values.astype(float)
                )
                means = aggregate_fields(
                    [field], ds.cell_area.values, ds.input_valid.values == 1, bins[h]
                )[0]
                use = np.isfinite(means)
                values[use] = means[use]
            display = values[keys]
            saved = display.astype("<f4")
            finite = np.isfinite(display)
            error = float(np.max(abs(saved[finite] - display[finite]), initial=0))
            require(
                error
                <= np.finfo("f4").eps
                * max(1, float(np.max(abs(display[finite]), initial=0))),
                "Interactive display precision loss",
            )
            maximum_error = max(maximum_error, error)
            filename = f"frames/{index:04d}.bin"
            (destination / filename).write_bytes(saved.tobytes())
            frames.append({"file": filename})
            timestamps.append(
                data["north"].attrs["initial_time"]
                if index == 0
                else str(data["north"].time.values[index - 1].astype("datetime64[s]"))
                + "Z"
            )
            labels.append(
                f"{month} · ERA5 initial state"
                if index == 0
                else f"{month} · model interval-end state"
            )
    manifest = {
        "format": "sst-interactive-f32-v1",
        "grid": grid,
        "months": months,
        "timestamps": timestamps,
        "frameLabels": labels,
        "frames": frames,
        "gamma_w_m2_k": gamma,
        "name": f"Interactive model SSTA — γ = {gamma:g} W m⁻² K⁻¹",
        "description": "January 1979 ERA5 initial state, then February 1979–December 1980 integration · fixed bilinear H, historical forcing and κ=1000 m²/s · original active domain retained.",
        "source_sha256": hashes,
        "grid_manifest_sha256": checksum(grid_manifest),
        "maximum_float32_storage_error_k": maximum_error,
    }
    (destination / "manifest.json").write_text(
        json.dumps(manifest, separators=(",", ":"), allow_nan=False) + "\n"
    )
    for path, digest in hashes.items():
        require(
            checksum(Path(path)) == digest, "Scientific output changed during export"
        )


def main():
    from ssta_model.core.configuration import load_configuration
    from ssta_model.core.simulation import run_experiment

    root, config, destination = map(Path, sys.argv[1:])
    settings = load_configuration(config, root)
    run_experiment(config, root)
    export_interactive(
        Path(settings["output"]["directory"]),
        root / "frontend/public/data/era5_comparison/manifest.json",
        destination,
        settings["surface_damping"]["gamma_w_m2_k"],
    )


if __name__ == "__main__":
    main()
