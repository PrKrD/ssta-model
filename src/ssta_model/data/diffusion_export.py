"""Archived multi-experiment display export; active viewer uses historical_export."""

import hashlib
import json
from contextlib import ExitStack
from pathlib import Path

import numpy as np
import xarray as xr

from ssta_model.analysis.diffusion_comparison import validate_controlled_pair
from ssta_model.analysis.era5_comparison import aligned_months
from ssta_model.analysis.h_sensitivity import effect_fields, validate_h_pair
from ssta_model.data.comparison_export import aggregate_fields, comparison_bins
from ssta_model.data.model_inputs import require, same_grid
from ssta_model.data.prepare import checksum


def h_comparison_layers(means):
    """C, B, ERA5, C−ERA5, C−B, A; physical values never rescaled."""
    return np.stack(
        [
            means[0],
            means[1],
            means[2],
            means[0] - means[2],
            effect_fields(means[0], means[1]),
            means[3],
        ]
    )


def export_comparison(
    run_dir, processed_dir, destination, *, baseline_dir, original_h_dir=None
):
    run_dir, processed_dir, destination, baseline_dir = map(
        Path, (run_dir, processed_dir, destination, baseline_dir)
    )
    sensitivity = original_h_dir is not None
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "frames").mkdir(exist_ok=True)
    (run_dir / "comparison").mkdir(exist_ok=True)
    with ExitStack() as stack:
        datasets = {}
        bins = {}
        valid = {}
        h_valid = {}
        original_valid = {}
        source_hashes = {}
        reference = None
        for h in ("north", "south"):
            paths = [
                run_dir / f"{h}_sst.nc",
                baseline_dir / f"{h}_sst.nc",
                processed_dir / f"{h}_era5_ssta.nc",
                processed_dir / f"{h}_surface.nc",
            ]
            d, b, e, s = [stack.enter_context(xr.open_dataset(p)) for p in paths]
            if sensitivity:
                extra_paths = [
                    Path(original_h_dir) / f"{h}_sst.nc",
                    processed_dir / f"{h}_surface_h_era5_bilinear.nc",
                ]
                o, c = [stack.enter_context(xr.open_dataset(p)) for p in extra_paths]
                paths.extend(extra_paths)
                validate_h_pair(d, o)
                validate_controlled_pair(o, b)
                same_grid(d, c)
                require(c.H.attrs.get("units") == "m", "Candidate display H units")
                require(
                    np.array_equal(c.H, d.H, equal_nan=True),
                    "Display H differs from integrated H",
                )
            else:
                validate_controlled_pair(d, b)
                o, c = d, s
            same_grid(d, e)
            same_grid(d, s)
            require(s.H.attrs.get("units") == "m", "H must be metres")
            aligned = aligned_months(d, e)
            months = [d.attrs["initial_month"]] + [m for _, _, m in aligned]
            if reference is not None:
                require(months == reference, "Hemisphere months differ")
            reference = months
            datasets[h] = (d, b, e, s, aligned, o, c)
            bins[h] = comparison_bins(d.latitude.values, d.longitude.values)
            valid[h] = d.input_valid.values == 1
            original_valid[h] = np.isfinite(s.H.values) & (s.H.values > 0)
            h_valid[h] = original_valid[h] | (
                np.isfinite(c.H.values) & (c.H.values > 0)
            )
            for p in paths:
                source_hashes[str(p)] = checksum(p)
        # Include H-only coastal tiles. SST is missing there, never filled from H or ERA5.
        counts = sum(
            np.bincount(bins[h][h_valid[h]], minlength=259200) for h in datasets
        )
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
        depth = np.full(259200, np.nan)
        original_depth = np.full(259200, np.nan)
        for h, (d, b, e, s, aligned, o, c) in datasets.items():
            values = aggregate_fields(
                [c.H.values.astype(float)],
                d.cell_area.values,
                np.isfinite(c.H.values) & (c.H.values > 0),
                bins[h],
            )[0]
            use = np.isfinite(values)
            depth[use] = values[use]
            original = aggregate_fields(
                [s.H.values.astype(float)],
                d.cell_area.values,
                original_valid[h],
                bins[h],
            )[0]
            original_depth[np.isfinite(original)] = original[np.isfinite(original)]
        depth_values = depth[occupied]
        depth_content = depth_values.astype("<f4").tobytes()
        (destination / "depth.bin").write_bytes(depth_content)
        original_content = original_depth[occupied].astype("<f4").tobytes()
        if sensitivity:
            (destination / "depth_original.bin").write_bytes(original_content)
        groups = {name: [] for name in ("sst", "difference", "effect")}
        extrema = {name: [np.inf, -np.inf] for name in groups}
        frames = []
        times = []
        labels = []
        size = 0
        max_error = 0.0
        checks = 0
        max_storage_error = 0.0
        for index, month in enumerate(reference):
            combined = np.full((6 if sensitivity else 5, 259200), np.nan)
            for h, (d, b, e, s, aligned, o, c) in datasets.items():
                if index == 0:
                    dv = d.initial_sst_anomaly.values
                    bv = b.initial_sst_anomaly.values
                    ov = o.initial_sst_anomaly.values
                    j = int(
                        np.flatnonzero(
                            e.time.values.astype("datetime64[M]")
                            == np.datetime64(month)
                        )[0]
                    )
                else:
                    i, j, _ = aligned[index - 1]
                    dv = d.sst_anomaly.isel(time=i).values.astype(float)
                    bv = b.sst_anomaly.isel(time=i).values.astype(float)
                    ov = o.sst_anomaly.isel(time=i).values.astype(float)
                ev = e.sst_anomaly.isel(time=j).values.astype(float)
                area = d.cell_area.values
                means = aggregate_fields(
                    [dv, ov, ev, bv] if sensitivity else [dv, bv, ev],
                    area,
                    valid[h],
                    bins[h],
                )
                values = (
                    h_comparison_layers(means)
                    if sensitivity
                    else np.concatenate(
                        (
                            means,
                            (means[0] - means[2])[None],
                            (means[0] - means[1])[None],
                        )
                    )
                )
                use = np.isfinite(values[0])
                combined[:, use] = values[:, use]
                if index in (0, 1, 16, len(reference) - 1):
                    keys = np.flatnonzero(use)
                    for key in keys[
                        np.linspace(0, len(keys) - 1, min(12, len(keys)), dtype=int)
                    ]:
                        south = -90 + (key // 720) / 2
                        west = -180 + (key % 720) / 2
                        lat = d.latitude.values[:, None]
                        lon = (d.longitude.values[None, :] + 180) % 360 - 180
                        latitude = (lat >= south) & (lat < south + 0.5)
                        if south + 0.5 in (-20, 90):
                            latitude |= lat == south + 0.5
                        select = (
                            valid[h]
                            & latitude
                            & (lon >= west)
                            & (lon < west + 0.5)
                            & np.isfinite(dv)
                            & np.isfinite(bv)
                            & np.isfinite(ev)
                            & np.isfinite(ov)
                        )
                        fields = (
                            (dv, ov, ev, dv - ev, dv - ov, bv)
                            if sensitivity
                            else (dv, bv, ev, dv - ev, dv - bv)
                        )
                        for layer, field in enumerate(fields):
                            error = abs(
                                np.average(field[select], weights=area[select])
                                - values[layer, key]
                            )
                            max_error = max(max_error, float(error))
                            checks += 1
                            require(
                                error < 1e-10,
                                "Independent display aggregation mismatch",
                            )
            display = combined[:, occupied]
            for name, values in zip(
                groups,
                (
                    display[[0, 1, 2, 5]].ravel()
                    if sensitivity
                    else display[:3].ravel(),
                    display[3],
                    display[4],
                ),
            ):
                finite = values[np.isfinite(values)]
                if finite.size:
                    extrema[name][0] = min(extrema[name][0], float(finite.min()))
                    extrema[name][1] = max(extrema[name][1], float(finite.max()))
                    groups[name].extend(finite[(index * 37) % 1024 :: 1024].tolist())
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
            filename = f"frames/{index:04d}.bin"
            content = saved.tobytes()
            (destination / filename).write_bytes(content)
            size += len(content)
            frames.append(
                {"file": filename, "sha256": hashlib.sha256(content).hexdigest()}
            )
            d = datasets["north"][0]
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
                    f"Exported diffusion comparison {index + 1}/{len(reference)}",
                    flush=True,
                )
        populations = {k: sorted([*v, *extrema[k]]) for k, v in groups.items()}
        depth_population = (
            np.r_[depth_values, original_depth[occupied]]
            if sensitivity
            else depth_values
        )
        populations["depth"] = sorted(
            depth_population[np.isfinite(depth_population)].tolist()
        )
        manifest = {
            "format": "sst-comparison-f32-v2",
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
            "description": "0.5° common-ocean-area SST aggregates · κ=1000 m²/s. Fixed H, forcing and damping match the no-diffusion baseline. Retrospective ERA5 comparison; fixed sampled colour limits are shared by both model versions and ERA5.",
            "depthDescription": "Fixed mixed-layer depth H (m) · de Boyer Montégut (2023), density threshold 0.03 kg/m³ from 10 m. Maximum of 12 monthly climatologies; unchanged 1° containing-cell mapping to native 0.25°, displayed as 0.5° ocean-area means. Not animated.",
            "encoding": "Little-endian float32; five layer-major arrays: with diffusion, without diffusion, ERA5, with−ERA5, with−without. NaN missing. Separate depth.bin contains one static H array.",
            "source_sha256": source_hashes,
            "percentile_sampling": "SST/difference samples every 1024 finite values with rotating monthly offset plus extrema; static H uses every occupied tile. Display colours only; values unchanged.",
            "depth_source_doi": "https://doi.org/10.17882/91774",
        }
        if sensitivity:
            manifest.update(
                {
                    "format": "sst-comparison-f32-v3",
                    "staticOriginalDepth": {
                        "file": "depth_original.bin",
                        "sha256": hashlib.sha256(original_content).hexdigest(),
                    },
                    "description": "Controlled H sensitivity · 0.5° common-area aggregates · unchanged active domain, forcing, damping and κ=1000 m²/s. All model and ERA5 SSTA share fixed colour limits. Retrospective comparison.",
                    "depthDescription": "Bilinear fixed H (m) · de Boyer Montégut (2023) maximum monthly 1° climatology, source mask==1, periodic mask-aware bilinear on ERA5 ocean. Original H retained beyond ±89.5° only at baseline active cells. Interpolation adds no observational resolution. Not animated.",
                    "originalDepthDescription": "Original fixed H (m) · de Boyer Montégut (2023) maximum monthly 1° climatology, containing-cell mapping on ERA5 ocean. Not animated. Same colour limits as bilinear H.",
                    "encoding": "Little-endian float32; six layer-major arrays: bilinear H model, original H diffusion model, ERA5, bilinear−ERA5, bilinear−original, original H no-diffusion model. Two separate static H arrays; NaN missing.",
                }
            )
        (destination / "manifest.json").write_text(
            json.dumps(manifest, separators=(",", ":"), allow_nan=False) + "\n"
        )
    for p, digest in source_hashes.items():
        require(checksum(p) == digest, "Scientific source changed during export")
    report = {
        "cells": len(cells),
        "months": len(frames),
        "monthly_binary_bytes": size,
        "manifest_bytes": (destination / "manifest.json").stat().st_size,
        "static_depth_bytes": len(depth_content),
        "static_original_depth_bytes": len(original_content) if sensitivity else 0,
        "independent_coordinate_checks": checks,
        "maximum_aggregation_error_k": max_error,
        "maximum_float32_storage_error_k": max_storage_error,
        "source_sha256": source_hashes,
    }
    (run_dir / "comparison/display_export_report.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    return report
