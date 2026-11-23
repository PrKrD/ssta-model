"""Static 0.5° comparison assets, one three-layer float32 file per calendar month."""

import hashlib
import json
from contextlib import ExitStack
from pathlib import Path

import numpy as np
import xarray as xr

from ssta_model.analysis.era5_comparison import aligned_months

from .model_inputs import require, same_grid
from .prepare import checksum


def comparison_bins(latitude, longitude):
    """Half-degree centre bins, with the same closed domain-edge convention as the pilot."""
    lat = np.asarray(latitude)
    lon = (np.asarray(longitude) + 180) % 360 - 180
    require(
        np.all(np.isfinite(lat) & (abs(lat) <= 90) & (abs(lat) >= 20)),
        "Invalid extratropical latitude",
    )
    require(np.isfinite(lon).all(), "Invalid longitude")
    rows = np.minimum(np.floor((lat + 90) * 2).astype(int), 359)
    rows[lat == -20] = 139
    cols = np.floor((lon + 180) * 2).astype(int)
    return rows[:, None] * 720 + cols[None, :]


def aggregate_pair(model, era, area, valid, bins):
    """Both layers and Model−ERA5 use exactly the same finite native ocean support."""
    use = valid & np.isfinite(model) & np.isfinite(era)
    require(np.all(np.isfinite(area[use]) & (area[use] > 0)), "Invalid native areas")
    weights = np.bincount(bins[use], weights=area[use], minlength=259200)
    result = []
    for values in (model, era):
        total = np.bincount(
            bins[use], weights=values[use] * area[use], minlength=259200
        )
        means = np.full(259200, np.nan)
        np.divide(total, weights, out=means, where=weights > 0)
        result.append(means)
    return np.stack([*result, result[0] - result[1]])


def export_comparison(run_dir, processed_dir, destination):
    """Bound browser memory with ordinary static monthly files; no API or scientific regridding."""
    run_dir, processed_dir, destination = map(
        Path, (run_dir, processed_dir, destination)
    )
    destination.mkdir(parents=True, exist_ok=True)
    (run_dir / "comparison").mkdir(exist_ok=True)
    (destination / "frames").mkdir(exist_ok=True)
    with ExitStack() as stack:
        datasets = {}
        bins = {}
        valid = {}
        source_hashes = {}
        reference = None
        for h in ("north", "south"):
            model = stack.enter_context(xr.open_dataset(run_dir / f"{h}_sst.nc"))
            era = stack.enter_context(
                xr.open_dataset(processed_dir / f"{h}_era5_ssta.nc")
            )
            same_grid(model, era)
            aligned = aligned_months(model, era)
            require(
                model.attrs.get("initial_month") == "1979-01",
                "Expected January 1979 observed initialisation",
            )
            months = [model.attrs["initial_month"]] + [m for _, _, m in aligned]
            if reference is not None:
                require(months == reference, "Hemisphere comparison months differ")
            reference = months
            datasets[h] = (model, era, aligned)
            bins[h] = comparison_bins(model.latitude.values, model.longitude.values)
            valid[h] = model.input_valid.values == 1
            for p in (run_dir / f"{h}_sst.nc", processed_dir / f"{h}_era5_ssta.nc"):
                source_hashes[str(p)] = checksum(p)
        counts = sum(np.bincount(bins[h][valid[h]], minlength=259200) for h in datasets)
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
        frames = []
        timestamps = []
        labels = []
        samples = [[], []]
        extrema = [[np.inf, -np.inf] for _ in range(2)]
        max_error = 0.0
        checks = 0
        size = 0
        for index, month in enumerate(reference):
            combined = np.full((3, 259200), np.nan)
            for h, (model, era, aligned) in datasets.items():
                if index == 0:
                    m = model.initial_sst_anomaly.values
                    j = int(
                        np.flatnonzero(
                            era.time.values.astype("datetime64[M]")
                            == np.datetime64(month, "M")
                        )[0]
                    )
                else:
                    i, j, _ = aligned[index - 1]
                    m = model.sst_anomaly.isel(time=i).values.astype(float)
                e = era.sst_anomaly.isel(time=j).values.astype(float)
                a = model.cell_area.values
                values = aggregate_pair(m, e, a, valid[h], bins[h])
                available = np.isfinite(values[0])
                combined[:, available] = values[:, available]
                # Coordinate-based checks independent of integer bin assignment.
                if index in (0, 1, 16, len(reference) - 1):
                    keys = np.flatnonzero(available)
                    for key in keys[
                        np.linspace(0, len(keys) - 1, min(12, len(keys)), dtype=int)
                    ]:
                        south = -90 + (key // 720) / 2
                        west = -180 + (key % 720) / 2
                        lat = model.latitude.values[:, None]
                        lon = (model.longitude.values[None, :] + 180) % 360 - 180
                        latitude = (lat >= south) & (lat < south + 0.5)
                        if south + 0.5 in (-20, 90):
                            latitude |= lat == south + 0.5
                        use = (
                            valid[h]
                            & latitude
                            & (lon >= west)
                            & (lon < west + 0.5)
                            & np.isfinite(m)
                            & np.isfinite(e)
                        )
                        for layer, original in enumerate((m, e, m - e)):
                            expected = np.average(original[use], weights=a[use])
                            error = abs(expected - values[layer, key])
                            max_error = max(max_error, float(error))
                            checks += 1
                            require(
                                error < 1e-10,
                                "Independent half-degree aggregate mismatch",
                            )
            display = combined[:, occupied]
            for group, values in enumerate((display[:2].ravel(), display[2])):
                finite = values[np.isfinite(values)]
                if finite.size:
                    extrema[group][0] = min(extrema[group][0], float(finite.min()))
                    extrema[group][1] = max(extrema[group][1], float(finite.max()))
                    offset = (index * 37) % 1024
                    samples[group].extend(finite[offset::1024].tolist())
            saved = display.astype("<f4")
            finite = np.isfinite(display)
            require(
                np.max(abs(saved[finite] - display[finite]), initial=0)
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
            timesource = datasets["north"][0]
            timestamps.append(
                timesource.attrs["initial_time"]
                if index == 0
                else str(timesource.time.values[index - 1].astype("datetime64[s]"))
                + "Z"
            )
            labels.append(
                f"{month} · January ERA5 initial state"
                if index == 0
                else f"{month} · model interval-end / ERA5 monthly mean"
            )
            if index % 120 == 0:
                print(f"Exported comparison {index + 1}/{len(reference)}", flush=True)
        populations = [sorted([*v, *extrema[i]]) for i, v in enumerate(samples)]
        manifest = {
            "format": "sst-comparison-f32-v1",
            "grid": {"id": "historical-sst-0.5deg", "cells": cells},
            "months": reference,
            "timestamps": timestamps,
            "frameLabels": labels,
            "frames": frames,
            "populations": {"sst": populations[0], "difference": populations[1]},
            "description": "0.5° common-ocean-area aggregates · retrospective ERA5-related comparison, not independent prediction validation. Calendar labels match model boundary states to ERA5 monthly means. Fixed colour percentiles use deterministic rotating samples across the full history; model and ERA5 share one population.",
            "encoding": "Little-endian float32, layer-major model/ERA5/difference; NaN means missing; each file has 3 × grid.cells.length values",
            "source_sha256": source_hashes,
            "aggregation": "Native 0.25° centres in half-open 0.5° bins; closed northern polar edge and southern -20° edge. Saved native areas weight common finite ocean only; difference=Model−ERA5. No smoothing.",
            "percentile_sampling": "Finite aggregates every 1024th value with month-dependent rotating offset; extrema included; approximate display percentiles only, never changes data",
        }
        (destination / "manifest.json").write_text(
            json.dumps(manifest, separators=(",", ":"), allow_nan=False) + "\n"
        )
    report = {
        "cells": len(cells),
        "months": len(frames),
        "monthly_binary_bytes": size,
        "manifest_bytes": (destination / "manifest.json").stat().st_size,
        "independent_coordinate_checks": checks,
        "maximum_aggregation_error_k": max_error,
        "source_sha256": source_hashes,
    }
    for p, digest in source_hashes.items():
        require(checksum(p) == digest, "Comparison source changed during export")
    (run_dir / "comparison/display_export_report.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    return report
