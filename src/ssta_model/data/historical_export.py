"""Compact primary-model/ERA5 display assets from saved outputs; no integration."""

import hashlib
import json
from contextlib import ExitStack
from pathlib import Path

import numpy as np
import xarray as xr

from ssta_model.analysis.era5_comparison import aligned_months
from ssta_model.data.comparison_export import (
    aggregate_fields,
    aggregate_pair,
    comparison_bins,
)
from ssta_model.data.model_inputs import require, same_grid
from ssta_model.data.prepare import checksum


def export_historical(run_dir, processed_dir, destination):
    """Two float32 arrays/month and static H, preserving the existing display grid.

    Original processed H participates only in the stable geometry's coastal-tile
    union, so existing interactive exports remain compatible. Neither retired
    historical run nor any previous display manifest is needed.
    """
    run_dir, processed_dir, destination = map(
        Path, (run_dir, processed_dir, destination)
    )
    require(
        not destination.exists(),
        "Choose a new display destination; existing assets are protected",
    )
    destination.mkdir(parents=True)
    (destination / "frames").mkdir()
    sources = {}
    with ExitStack() as stack:
        data, bins = {}, {}
        reference = None
        counts = np.zeros(259200, dtype=int)
        depth = np.full(259200, np.nan)
        for h in ("north", "south"):
            paths = [
                run_dir / f"{h}_sst.nc",
                processed_dir / f"{h}_era5_ssta.nc",
                processed_dir / f"{h}_surface_h_era5_bilinear.nc",
                processed_dir / f"{h}_surface.nc",
            ]
            d, e, c, original = [stack.enter_context(xr.open_dataset(p)) for p in paths]
            for other in (e, c, original):
                same_grid(d, other)
            config = json.loads(d.attrs["configuration_json"])
            require(
                config["mixed_layer_depth"]["variant"] == "era5_bilinear"
                and config["physics"]["horizontal_diffusion"],
                "Expected primary bilinear-H diffusion model",
            )
            require(
                d.sst_anomaly.attrs.get("units")
                == e.sst_anomaly.attrs.get("units")
                == "K",
                "SSTA must be kelvin",
            )
            require(
                c.H.attrs.get("units") == original.H.attrs.get("units") == "m",
                "H must be metres",
            )
            require(
                np.array_equal(c.H, d.H, equal_nan=True),
                "Display H differs from integrated H",
            )
            aligned = aligned_months(d, e)
            months = [d.attrs["initial_month"], *[m for _, _, m in aligned]]
            require(
                reference is None or months == reference, "Hemisphere months differ"
            )
            if reference is not None:
                require(
                    np.array_equal(d.time, data["north"][0].time)
                    and d.attrs["initial_time"]
                    == data["north"][0].attrs["initial_time"],
                    "Hemisphere state times differ",
                )
            reference = months
            bins[h] = comparison_bins(d.latitude.values, d.longitude.values)
            valid = d.input_valid.values == 1
            h_valid = np.isfinite(c.H.values) & (c.H.values > 0)
            union = h_valid | (np.isfinite(original.H.values) & (original.H.values > 0))
            require(np.all(union[valid]), "Display geometry omits active cells")
            counts += np.bincount(bins[h][union], minlength=259200)
            means = aggregate_fields(
                [c.H.values.astype(float)], d.cell_area.values, h_valid, bins[h]
            )[0]
            depth[np.isfinite(means)] = means[np.isfinite(means)]
            data[h] = d, e, aligned, valid
            sources.update({str(p): checksum(p) for p in paths})
        occupied = np.flatnonzero(counts)
        cells = [
            {
                "id": f"comparison-{int(k)}",
                "west": float(-180 + (k % 720) / 2),
                "east": float(-180 + (k % 720 + 1) / 2),
                "south": float(-90 + (k // 720) / 2),
                "north": float(-90 + (k // 720 + 1) / 2),
                "nativeCellCount": int(counts[k]),
            }
            for k in occupied
        ]
        depth_values = depth[occupied].astype("<f4")
        depth_content = depth_values.tobytes()
        (destination / "depth.bin").write_bytes(depth_content)
        groups = {"sst": [], "difference": []}
        extrema = {k: [np.inf, -np.inf] for k in groups}
        frames, times, labels = [], [], []
        max_storage_error = max_aggregation_error = 0.0
        checks = 0
        for index, month in enumerate(reference):
            combined = np.full((2, 259200), np.nan)
            for h, (d, e, aligned, valid) in data.items():
                if index == 0:
                    model = d.initial_sst_anomaly.values
                    positions = np.flatnonzero(
                        e.time.values.astype("datetime64[M]") == np.datetime64(month)
                    )
                    require(len(positions) == 1, "Missing/duplicate initial ERA5 month")
                    j = int(positions[0])
                else:
                    i, j, _ = aligned[index - 1]
                    model = d.sst_anomaly.isel(time=i).values.astype(float)
                era = e.sst_anomaly.isel(time=j).values.astype(float)
                area = d.cell_area.values
                means = aggregate_pair(model, era, area, valid, bins[h])[:2]
                use = np.isfinite(means[0])
                combined[:, use] = means[:, use]
                if index in (0, 1, 16, len(reference) - 1):
                    keys = np.flatnonzero(use)
                    for key in keys[
                        np.linspace(0, len(keys) - 1, min(12, len(keys)), dtype=int)
                    ]:
                        select = (
                            valid
                            & (bins[h] == key)
                            & np.isfinite(model)
                            & np.isfinite(era)
                        )
                        for field, value in zip((model, era), means[:, key]):
                            error = float(
                                abs(
                                    np.average(field[select], weights=area[select])
                                    - value
                                )
                            )
                            max_aggregation_error = max(max_aggregation_error, error)
                            checks += 1
                            require(
                                error < 1e-10,
                                "Independent display aggregation mismatch",
                            )
            display = combined[:, occupied]
            saved = display.astype("<f4")
            finite = np.isfinite(display)
            error = float(np.max(abs(saved[finite] - display[finite]), initial=0))
            max_storage_error = max(max_storage_error, error)
            require(
                error
                <= np.finfo("f4").eps
                * max(1, float(np.max(abs(display[finite]), initial=0))),
                "Display precision loss",
            )
            # Difference population follows subtraction of the actual stored values.
            rounded = saved.astype(float)
            for name, values in zip(groups, (rounded.ravel(), rounded[0] - rounded[1])):
                finite_values = values[np.isfinite(values)]
                if finite_values.size:
                    extrema[name][0] = min(extrema[name][0], float(finite_values.min()))
                    extrema[name][1] = max(extrema[name][1], float(finite_values.max()))
                    groups[name].extend(
                        finite_values[(index * 37) % 1024 :: 1024].tolist()
                    )
            filename = f"frames/{index:04d}.bin"
            content = saved.tobytes()
            (destination / filename).write_bytes(content)
            frames.append(
                {"file": filename, "sha256": hashlib.sha256(content).hexdigest()}
            )
            d = data["north"][0]
            times.append(
                d.attrs["initial_time"]
                if index == 0
                else str(d.time.values[index - 1].astype("datetime64[s]")) + "Z"
            )
            labels.append(
                f"{month} · ERA5 initial state"
                if index == 0
                else f"{month} · model interval-end / ERA5 monthly mean"
            )
            if index % 120 == 0:
                print(
                    f"Exported primary historical viewer {index + 1}/{len(reference)}",
                    flush=True,
                )
        populations = {
            k: sorted([*values, *extrema[k]]) for k, values in groups.items()
        }
        populations["depth"] = sorted(
            depth_values[np.isfinite(depth_values)].astype(float).tolist()
        )
        manifest = {
            "format": "sst-comparison-f32-v4",
            "grid": {"id": "diffusion-comparison-0.5deg", "cells": cells},
            "months": reference,
            "timestamps": times,
            "frameLabels": labels,
            "frames": frames,
            "staticDepth": {
                "file": "depth.bin",
                "sha256": hashlib.sha256(depth_content).hexdigest(),
            },
            "populations": populations,
            "description": "Historical SST anomaly model · bilinear fixed H, diffusion κ=1000 m²/s, historical 12-PC forcing and unchanged damping. 0.5° common-ocean-area aggregates. Retrospective ERA5 comparison.",
            "depthDescription": "Fixed H (m) · de Boyer Montégut (2023) maximum monthly 1° climatology; periodic mask-aware bilinear interpolation on ERA5 ocean. Original H retained beyond ±89.5° only at baseline active cells. Displayed as 0.5° ocean-area means; not animated.",
            "encoding": "Little-endian float32; two layer-major arrays: model, ERA5. NaN missing. Model minus ERA5 is calculated in the browser. Separate static depth.bin.",
            "source_sha256": sources,
            "percentile_sampling": "Fixed SST/difference samples every 1024 finite values with rotating monthly offset plus extrema; static H uses every finite tile. Display colours only.",
            "depth_source_doi": "https://doi.org/10.17882/91774",
        }
        (destination / "manifest.json").write_text(
            json.dumps(manifest, separators=(",", ":"), allow_nan=False) + "\n"
        )
    for p, digest in sources.items():
        require(checksum(p) == digest, "Scientific source changed during export")
    report = {
        "cells": len(cells),
        "months": len(frames),
        "monthly_binary_bytes": sum(
            (destination / f["file"]).stat().st_size for f in frames
        ),
        "manifest_bytes": (destination / "manifest.json").stat().st_size,
        "static_depth_bytes": len(depth_content),
        "independent_aggregation_checks": checks,
        "maximum_aggregation_error_k": max_aggregation_error,
        "maximum_float32_storage_error_k": max_storage_error,
        "source_sha256": sources,
    }
    (destination / "export_report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report
