"""Controlled with/without-diffusion diagnostics and fixed-depth scientific maps."""

import csv
import json
from pathlib import Path

import numpy as np
import xarray as xr

from ssta_model.analysis.era5_comparison import (
    REGIONS,
    analyse_comparison,
    paired_statistics,
)
from ssta_model.data.model_inputs import require, same_grid


def validate_controlled_pair(diffusion, baseline):
    same_grid(diffusion, baseline)
    require(
        np.array_equal(diffusion.forcing_month, baseline.forcing_month),
        "Controlled run months differ",
    )
    require(
        np.array_equal(diffusion.time, baseline.time),
        "Controlled state boundaries differ",
    )
    require(
        np.array_equal(diffusion.input_valid, baseline.input_valid),
        "Controlled masks differ",
    )
    require(
        np.array_equal(diffusion.H, baseline.H, equal_nan=True), "Controlled H differs"
    )
    require(
        np.array_equal(
            diffusion.initial_sst_anomaly, baseline.initial_sst_anomaly, equal_nan=True
        ),
        "Controlled initial fields differ",
    )


def compare_diffusion(run_dir, baseline_dir, processed_dir):
    run_dir, baseline_dir, processed_dir = map(
        Path, (run_dir, baseline_dir, processed_dir)
    )
    current = analyse_comparison(run_dir, processed_dir)
    baseline = json.loads((baseline_dir / "comparison/summary.json").read_text())
    out = run_dir / "comparison"
    result = {
        "interpretation": "Controlled kappa=1000 m2 s-1 experiment; unchanged forcing, damping, H, initial field and mask. Retrospective ERA5 comparison, not independent validation.",
        "hemispheres": {},
    }
    for h in ("north", "south"):
        with (
            xr.open_dataset(run_dir / f"{h}_sst.nc") as d,
            xr.open_dataset(baseline_dir / f"{h}_sst.nc") as b,
        ):
            validate_controlled_pair(d, b)
            rows = []
            valid = d.input_valid.values == 1
            area = d.cell_area.values
            for i, month in enumerate(d.forcing_month.values.astype(str)):
                dv = d.sst_anomaly.isel(time=i).values.astype(float)
                bv = b.sst_anomaly.isel(time=i).values.astype(float)
                metrics = paired_statistics(dv, bv, area, valid)
                rows.append(
                    {
                        "month": month,
                        "effect_area_mean_k": metrics["bias_k"],
                        "effect_area_rms_k": metrics["rmse_k"],
                        "effect_minimum_k": metrics["difference_minimum_k"],
                        "effect_maximum_k": metrics["difference_maximum_k"],
                        "with_spatial_variance_k2": metrics["model_std_k"] ** 2,
                        "without_spatial_variance_k2": metrics["era5_std_k"] ** 2,
                    }
                )
            with (out / f"{h}_diffusion_effect.csv").open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=rows[0])
                writer.writeheader()
                writer.writerows(rows)
        before = baseline["hemispheres"][h]["all_integrated_months"]
        after = current["hemispheres"][h]["all_integrated_months"]
        result["hemispheres"][h] = {
            "without_diffusion": before,
            "with_diffusion": after,
            "rmse_change_k": after["rms_monthly_area_rmse_k"]
            - before["rms_monthly_area_rmse_k"],
            "pattern_correlation_change": after["mean_monthly_spatial_correlation"]
            - before["mean_monthly_spatial_correlation"],
            "mean_spatial_variance_ratio": float(
                np.mean([r["with_spatial_variance_k2"] for r in rows])
                / np.mean([r["without_spatial_variance_k2"] for r in rows])
            ),
            "maximum_absolute_diffusion_effect_k": max(
                max(abs(r["effect_minimum_k"]), abs(r["effect_maximum_k"]))
                for r in rows
            ),
        }
    (out / "diffusion_summary.json").write_text(json.dumps(result, indent=2) + "\n")
    diffusion_figures(run_dir, baseline_dir, processed_dir)
    return result


def diffusion_figures(run_dir, baseline_dir, processed_dir, month="1980-05"):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import TwoSlopeNorm

    run_dir, baseline_dir, processed_dir = map(
        Path, (run_dir, baseline_dir, processed_dir)
    )
    out = run_dir / "comparison"
    out.mkdir(exist_ok=True)
    maps = []
    depths = []
    variability = []
    for h in ("north", "south"):
        with (
            xr.open_dataset(run_dir / f"{h}_sst.nc") as d,
            xr.open_dataset(baseline_dir / f"{h}_sst.nc") as b,
            xr.open_dataset(processed_dir / f"{h}_era5_ssta.nc") as e,
        ):
            validate_controlled_pair(d, b)
            i = int(np.flatnonzero(d.forcing_month.values.astype(str) == month)[0])
            j = int(
                np.flatnonzero(
                    e.time.values.astype("datetime64[M]") == np.datetime64(month)
                )[0]
            )
            dv = d.sst_anomaly.isel(time=i).load()
            bv = b.sst_anomaly.isel(time=i).load()
            ev = e.sst_anomaly.isel(time=j).load()
            common = (
                (d.input_valid == 1)
                & np.isfinite(dv)
                & np.isfinite(bv)
                & np.isfinite(ev)
            )
            maps.append(tuple(f.where(common) for f in (dv, bv, ev, dv - ev, dv - bv)))
        with xr.open_dataset(processed_dir / f"{h}_surface.nc") as ds:
            depths.append(ds.H.where(np.isfinite(ds.H) & (ds.H > 0)).load())
        with (
            xr.open_dataset(out / f"{h}_temporal_variability.nc") as d,
            xr.open_dataset(
                baseline_dir / f"comparison/{h}_temporal_variability.nc"
            ) as b,
        ):
            variability.append(
                (d.model_std.load(), b.model_std.load(), d.era5_std.load())
            )

    def draw(field, ax, **kwargs):
        field = (
            field.assign_coords(longitude=(field.longitude + 180) % 360 - 180)
            .sortby("longitude")
            .sortby("latitude")
        )
        image = ax.pcolormesh(
            field.longitude,
            field.latitude,
            field,
            shading="nearest",
            rasterized=True,
            **kwargs,
        )
        ax.set(
            xlim=(-180, 180),
            ylim=(-90, 90),
            xlabel="Longitude (° east)",
            ylabel="Latitude (° north)",
        )
        ax.set_facecolor("#d0d3d8")
        return image

    shared = max(float(abs(f).max()) for fields in maps for f in fields[:3])
    extents = [shared] * 3 + [
        max(float(abs(fields[k]).max()) for fields in maps) for k in (3, 4)
    ]
    fig, axes = plt.subplots(5, 1, figsize=(12, 15), layout="constrained")
    for k, title in enumerate(
        (
            "Model — with diffusion",
            "Model — without diffusion",
            "ERA5 reference",
            "With diffusion − ERA5",
            "Diffusion effect: with − without",
        )
    ):
        extent = max(extents[k], 1e-12)
        for fields in maps:
            image = draw(
                fields[k],
                axes[k],
                cmap="RdBu_r",
                norm=TwoSlopeNorm(vmin=-extent, vcenter=0, vmax=extent),
            )
        axes[k].set_title(title)
        fig.colorbar(image, ax=axes[k], label="K")
    fig.suptitle(
        f"{month} calendar label · native 0.25° · identical limits for all three SSTA fields"
    )
    fig.savefig(out / f"diffusion_comparison_{month}.png", dpi=150)
    plt.close(fig)
    fig, axes = plt.subplots(3, 1, figsize=(12, 10), layout="constrained")
    vmax = max(float(f.max()) for fields in variability for f in fields)
    for k, title in enumerate(
        (
            "With diffusion temporal SST standard deviation",
            "Without diffusion temporal SST standard deviation",
            "ERA5 temporal SST standard deviation",
        )
    ):
        for fields in variability:
            image = draw(fields[k], axes[k], cmap="viridis", vmin=0, vmax=vmax)
        axes[k].set_title(title)
        fig.colorbar(image, ax=axes[k], label="K")
    fig.savefig(out / "controlled_temporal_variability.png", dpi=150)
    plt.close(fig)
    fig, axes = plt.subplots(2, 1, figsize=(12, 8), layout="constrained")
    vmax = max(float(f.max()) for f in depths)
    for f in depths:
        image = draw(f, axes[0], cmap="viridis", vmin=0, vmax=vmax)
    axes[0].set_title(
        "Fixed H · de Boyer Montégut (2023) · maximum monthly climatology"
    )
    for f in depths:
        draw(f, axes[1], cmap="viridis", vmin=0, vmax=vmax)
    axes[1].set(
        xlim=(-80, 20),
        ylim=(30, 75),
        title="North Atlantic detail · native 0.25° displays unchanged 1° containing-cell mapping",
    )
    fig.colorbar(image, ax=axes, label="Mixed-layer depth (m)")
    fig.savefig(out / "fixed_H_native.png", dpi=180)
    plt.close(fig)
    for label, regions in (
        ("regional", list(REGIONS)),
        ("hemispheric", ["north", "south"]),
    ):
        allrows = []
        for path in (out, baseline_dir / "comparison"):
            if label == "regional":
                with (path / "regional_monthly.csv").open() as f:
                    allrows.append(list(csv.DictReader(f)))
            else:
                rows = []
                for h in regions:
                    with (path / f"{h}_monthly.csv").open() as f:
                        rows.extend({"region": h, **r} for r in csv.DictReader(f))
                allrows.append(rows)
        fig, axes = plt.subplots(
            len(regions),
            1,
            figsize=(12, 3 * len(regions)),
            layout="constrained",
            sharex=True,
        )
        for ax, region in zip(np.atleast_1d(axes), regions):
            d = [r for r in allrows[0] if r["region"] == region]
            b = [r for r in allrows[1] if r["region"] == region]
            require(
                [r.get("month") for r in d] == [r.get("month") for r in b],
                "Series months differ",
            )
            dates = np.array([r["month"] for r in d], dtype="datetime64[M]")
            for rows, key, name in (
                (d, "model_mean_k", "With diffusion"),
                (b, "model_mean_k", "Without diffusion"),
                (d, "era5_mean_k", "ERA5"),
            ):
                ax.plot(
                    dates,
                    [float(r[key]) if r[key] else np.nan for r in rows],
                    label=name,
                )
            ax.set(title=region, ylabel="K")
            ax.legend()
        fig.savefig(out / f"controlled_{label}_series.png", dpi=150)
        plt.close(fig)
