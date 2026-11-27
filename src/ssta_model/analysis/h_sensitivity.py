"""Controlled H-representation sensitivity from saved historical outputs only."""

import csv
import json
from pathlib import Path

import numpy as np
import xarray as xr

from ssta_model.analysis.diffusion_comparison import validate_controlled_pair
from ssta_model.analysis.era5_comparison import (
    REGIONS,
    aligned_months,
    analyse_comparison,
    correlation,
    paired_statistics,
    region_mask,
)
from ssta_model.data.model_inputs import require, same_grid

FOCUS_REGIONS = {
    "Labrador Sea": ("north", 50, 65, -65, -45),
    "Subpolar North Atlantic": ("north", 45, 65, -65, -10),
}


def validate_h_pair(current, previous):
    validate_controlled_pair(current, previous, same_depth=False)
    require(
        np.array_equal(current.cell_area, previous.cell_area), "Controlled areas differ"
    )
    require(
        np.array_equal(current.time_bounds, previous.time_bounds),
        "Controlled interval bounds differ",
    )
    configs = [json.loads(d.attrs["configuration_json"]) for d in (current, previous)]
    require(
        configs[0].get("mixed_layer_depth", {}).get("variant", "baseline")
        == "era5_bilinear",
        "Expected bilinear H experiment C",
    )
    require(
        configs[1].get("mixed_layer_depth", {}).get("variant", "baseline")
        == "baseline",
        "Expected original H experiment B",
    )
    for key in (
        "physics",
        "parameters",
        "initial_conditions",
        "inputs",
        "solver",
        "surface_damping",
    ):
        require(configs[0][key] == configs[1][key], f"Controlled {key} differs")
    for key in ("start_month", "end_month"):
        require(
            configs[0]["experiment"][key] == configs[1]["experiment"][key],
            f"Controlled {key} differs",
        )
    a, b = [json.loads(d.attrs["provenance_json"]) for d in (current, previous)]
    for name, record in b["inputs"].items():
        require(
            a["inputs"].get(name) == record,
            f"Controlled scientific input differs: {name}",
        )
    require(
        a["initialization_inputs"] == b["initialization_inputs"],
        "Controlled initial source differs",
    )


def effect_fields(current, previous):
    """Physical difference sign is always new bilinear minus original H model."""
    return current - previous


def compare_h(run_dir, original_dir, baseline_dir, processed_dir):
    run_dir, original_dir, baseline_dir, processed_dir = map(
        Path, (run_dir, original_dir, baseline_dir, processed_dir)
    )
    current = analyse_comparison(run_dir, processed_dir)
    previous = json.loads((original_dir / "comparison/summary.json").read_text())
    baseline = json.loads((baseline_dir / "comparison/summary.json").read_text())
    out = run_dir / "comparison"
    result = {
        "interpretation": "Only H representation changes between diffusion experiments B and C. Unchanged forcing, damping, diffusivity, geometry, masks, initial state and solver. Retrospective ERA5 comparison, not independent validation.",
        "hemispheres": {},
        "persistence": {},
        "focus_regions": FOCUS_REGIONS,
    }
    for h in ("north", "south"):
        with (
            xr.open_dataset(run_dir / f"{h}_sst.nc") as c,
            xr.open_dataset(original_dir / f"{h}_sst.nc") as b,
            xr.open_dataset(baseline_dir / f"{h}_sst.nc") as a,
            xr.open_dataset(processed_dir / f"{h}_era5_ssta.nc") as e,
        ):
            validate_h_pair(c, b)
            validate_controlled_pair(b, a)
            same_grid(c, e)
            valid = c.input_valid.values == 1
            area = c.cell_area.values
            regions = {
                name: region_mask(c, bounds)
                for name, bounds in {
                    **REGIONS,
                    **FOCUS_REGIONS,
                }.items()
                if bounds[0] == h
            }
            rows = []
            series = {
                name: {key: [] for key in ("bilinear", "original", "era5")}
                for name in [h, *regions]
            }
            for i, j, month in aligned_months(c, e):
                cv = c.sst_anomaly.isel(time=i).values.astype(float)
                bv = b.sst_anomaly.isel(time=i).values.astype(float)
                ev = e.sst_anomaly.isel(time=j).values.astype(float)
                m = paired_statistics(cv, bv, area, valid)
                rows.append(
                    {
                        "month": month,
                        "effect_mean_k": m["bias_k"],
                        "effect_rms_k": m["rmse_k"],
                        "effect_minimum_k": m["difference_minimum_k"],
                        "effect_maximum_k": m["difference_maximum_k"],
                        "bilinear_spatial_variance_k2": m["model_std_k"] ** 2,
                        "original_spatial_variance_k2": m["era5_std_k"] ** 2,
                    }
                )
                common = valid & np.isfinite(cv) & np.isfinite(bv) & np.isfinite(ev)
                for name, region in {h: np.ones(valid.shape, bool), **regions}.items():
                    use = common & region
                    for key, field in zip(
                        ("bilinear", "original", "era5"), (cv, bv, ev)
                    ):
                        series[name][key].append(
                            float(np.average(field[use], weights=area[use]))
                        )
            with (out / f"{h}_H_effect.csv").open("w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=rows[0])
                writer.writeheader()
                writer.writerows(rows)
            for name, s in series.items():
                result["persistence"][name] = {
                    key: {
                        "lag1_monthly_correlation": correlation(v[:-1], v[1:]),
                        "temporal_std_k": float(np.std(v)),
                    }
                    for key, v in s.items()
                }
                result["persistence"][name]["bilinear_era5_temporal_correlation"] = (
                    correlation(s["bilinear"], s["era5"])
                )
                result["persistence"][name]["original_era5_temporal_correlation"] = (
                    correlation(s["original"], s["era5"])
                )
                with (out / f"series_{name.replace(' ', '_')}.csv").open(
                    "w", newline=""
                ) as f:
                    writer = csv.writer(f)
                    writer.writerow(["month", "bilinear", "original", "era5"])
                    writer.writerows(
                        zip(
                            [r["month"] for r in rows],
                            s["bilinear"],
                            s["original"],
                            s["era5"],
                        )
                    )
        before = previous["hemispheres"][h]["all_integrated_months"]
        after = current["hemispheres"][h]["all_integrated_months"]
        changes = {}
        for key in (
            "mean_monthly_spatial_correlation",
            "rms_monthly_area_rmse_k",
            "mean_monthly_area_bias_k",
        ):
            delta = after[key] - before[key]
            changes[key] = {
                "absolute": delta,
                "relative_percent": 100 * delta / abs(before[key])
                if before[key]
                else None,
            }
        result["hemispheres"][h] = {
            "A_no_diffusion": baseline["hemispheres"][h]["all_integrated_months"],
            "B_original_H_diffusion": before,
            "C_bilinear_H_diffusion": after,
            "changes": changes,
            "mean_spatial_variance_ratio": float(
                np.mean([r["bilinear_spatial_variance_k2"] for r in rows])
                / np.mean([r["original_spatial_variance_k2"] for r in rows])
            ),
            "maximum_absolute_H_effect_k": max(
                max(abs(r["effect_minimum_k"]), abs(r["effect_maximum_k"]))
                for r in rows
            ),
        }
    (out / "h_sensitivity_summary.json").write_text(json.dumps(result, indent=2) + "\n")
    sensitivity_figures(run_dir, original_dir, processed_dir)
    return result


def sensitivity_figures(run_dir, original_dir, processed_dir, month="1980-05"):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out = run_dir / "comparison"
    maps = []
    variability = []
    for h in ("north", "south"):
        with (
            xr.open_dataset(run_dir / f"{h}_sst.nc") as c,
            xr.open_dataset(original_dir / f"{h}_sst.nc") as b,
            xr.open_dataset(processed_dir / f"{h}_era5_ssta.nc") as e,
        ):
            i = int(np.flatnonzero(c.forcing_month.values.astype(str) == month)[0])
            j = int(
                np.flatnonzero(
                    e.time.values.astype("datetime64[M]") == np.datetime64(month)
                )[0]
            )
            cv = c.sst_anomaly.isel(time=i).load()
            bv = b.sst_anomaly.isel(time=i).load()
            ev = e.sst_anomaly.isel(time=j).load()
            active = c.input_valid == 1
            common = active & np.isfinite(cv) & np.isfinite(bv)
            maps.append(
                [
                    b.H.where(active).load(),
                    c.H.where(active).load(),
                    (c.H - b.H).where(active).load(),
                    bv.where(common).load(),
                    cv.where(common).load(),
                    effect_fields(cv, bv).where(common).load(),
                    ev.where(common & np.isfinite(ev)).load(),
                    effect_fields(
                        c.sst_anomaly.isel(time=-1), b.sst_anomaly.isel(time=-1)
                    )
                    .where(active)
                    .load(),
                ]
            )
        with (
            xr.open_dataset(out / f"{h}_temporal_variability.nc") as c,
            xr.open_dataset(
                original_dir / f"comparison/{h}_temporal_variability.nc"
            ) as b,
        ):
            variability.append(
                [c.model_std.load(), b.model_std.load(), c.era5_std.load()]
            )

    def draw(field, ax, bounds, **kwargs):
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
            xlim=bounds[:2],
            ylim=bounds[2:],
            xlabel="Longitude (° east)",
            ylabel="Latitude (° north)",
        )
        ax.set_facecolor("#c9cdd2")
        return image

    hmax = max(float(f.max()) for m in maps for f in m[:2])
    sstmax = max(float(abs(f).max()) for m in maps for f in m[3:5] + [m[6]])
    for name, bounds in (
        ("global_H_SST_comparison", (-180, 180, -90, 90)),
        ("north_atlantic_H_SST_detail", (-80, 10, 40, 75)),
    ):
        fig, axes = plt.subplots(6, 1, figsize=(13, 18), layout="constrained")
        for k, title in enumerate(
            (
                "Original H",
                "Bilinear H",
                "Bilinear minus original H",
                "Original H + diffusion SSTA",
                "Bilinear H + diffusion SSTA",
                "H representation effect: bilinear minus original SSTA",
            )
        ):
            fields = [m[k] for m in maps]
            limit = (
                hmax
                if k < 2
                else (
                    sstmax if k in (3, 4) else max(float(abs(f).max()) for f in fields)
                )
            )
            sequential = k < 2
            for field in fields:
                image = draw(
                    field,
                    axes[k],
                    bounds,
                    cmap="viridis" if sequential else "RdBu_r",
                    vmin=0 if sequential else -max(limit, 1e-12),
                    vmax=max(limit, 1e-12),
                )
            axes[k].set_title(title)
            fig.colorbar(image, ax=axes[k], label="m" if k < 3 else "K")
        fig.suptitle(
            f"{month} calendar label · native 0.25° · unchanged model domain · shared H and direct SSTA limits"
        )
        fig.savefig(out / f"{name}_{month}.png", dpi=150)
        plt.close(fig)
    fig, ax = plt.subplots(figsize=(13, 5), layout="constrained")
    limit = max(float(abs(m[7]).max()) for m in maps)
    for m in maps:
        image = draw(
            m[7], ax, (-180, 180, -90, 90), cmap="RdBu_r", vmin=-limit, vmax=limit
        )
    ax.set_title(
        "October 2026 accumulated H-representation effect: bilinear minus original model"
    )
    fig.colorbar(image, ax=ax, label="K")
    fig.savefig(out / "final_H_effect.png", dpi=150)
    plt.close(fig)
    fig, axes = plt.subplots(3, 1, figsize=(13, 11), layout="constrained")
    limit = max(float(f.max()) for m in variability for f in m)
    for k, title in enumerate(
        (
            "Bilinear H + diffusion temporal SD",
            "Original H + diffusion temporal SD",
            "ERA5 temporal SD",
        )
    ):
        for m in variability:
            image = draw(
                m[k], axes[k], (-180, 180, -90, 90), cmap="viridis", vmin=0, vmax=limit
            )
        axes[k].set_title(title)
        fig.colorbar(image, ax=axes[k], label="K")
    fig.savefig(out / "H_controlled_temporal_variability.png", dpi=150)
    plt.close(fig)
    for label, names in (
        ("hemispheric", ["north", "south"]),
        ("regional", [*REGIONS, "Labrador Sea", "Subpolar North Atlantic"]),
    ):
        fig, axes = plt.subplots(
            len(names),
            1,
            figsize=(13, len(names) * 3),
            sharex=True,
            layout="constrained",
        )
        for ax, name in zip(np.atleast_1d(axes), names):
            with (out / f"series_{name.replace(' ', '_')}.csv").open() as f:
                rows = list(csv.DictReader(f))
            dates = np.array([r["month"] for r in rows], dtype="datetime64[M]")
            for key, title in (
                ("bilinear", "Bilinear H"),
                ("original", "Original H"),
                ("era5", "ERA5"),
            ):
                ax.plot(dates, [float(r[key]) for r in rows], label=title)
            ax.set(title=name, ylabel="K")
            ax.legend()
        fig.savefig(out / f"H_controlled_{label}_series.png", dpi=150)
        plt.close(fig)
