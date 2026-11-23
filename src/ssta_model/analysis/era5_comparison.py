"""Retrospective native-grid comparison; month labels deliberately match boundary states to means."""

import csv
import json
from pathlib import Path

import netCDF4
import numpy as np
import xarray as xr

from ssta_model.data.model_inputs import require, same_grid
from ssta_model.data.prepare import checksum

REGIONS = {
    "North Atlantic": ("north", 20, 65, -80, 0),
    "North Pacific": ("north", 20, 65, 120, -100),
    "South Atlantic": ("south", -60, -20, -70, 20),
    "South Pacific": ("south", -60, -20, 150, -70),
    "Southern Indian Ocean": ("south", -60, -20, 20, 150),
}


def correlation(x, y):
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    use = np.isfinite(x) & np.isfinite(y)
    if use.sum() < 2 or np.std(x[use]) == 0 or np.std(y[use]) == 0:
        return None
    return float(np.corrcoef(x[use], y[use])[0, 1])


def paired_statistics(model, observed, area, valid):
    """Common finite ocean cells; population spatial SD and unweighted Pearson pattern r."""
    require(
        model.shape == observed.shape == area.shape == valid.shape,
        "Comparison shapes differ",
    )
    use = valid & np.isfinite(model) & np.isfinite(observed)
    require(
        np.all(np.isfinite(area[use]) & (area[use] > 0)), "Invalid comparison areas"
    )
    if not use.any():
        return {"valid_cells": 0}
    m, e, w = model[use], observed[use], area[use]
    difference = m - e
    result = {
        "valid_cells": int(use.sum()),
        "area_m2": float(w.sum()),
        "spatial_correlation": correlation(m, e),
        "rmse_k": float(np.sqrt(np.average(difference**2, weights=w))),
        "bias_k": float(np.average(difference, weights=w)),
        "model_mean_k": float(np.average(m, weights=w)),
        "era5_mean_k": float(np.average(e, weights=w)),
        "model_std_k": float(m.std()),
        "era5_std_k": float(e.std()),
    }
    for name, values in (("model", m), ("era5", e), ("difference", difference)):
        result.update(
            {
                f"{name}_minimum_k": float(values.min()),
                f"{name}_maximum_k": float(values.max()),
                **{
                    f"{name}_p{q}_k": float(np.percentile(values, q))
                    for q in (1, 5, 50, 95, 99)
                },
            }
        )
    return result


def aligned_months(model, observed):
    """No January initial-state skill; match forcing labels, never shift by saved end time."""
    months = model.forcing_month.values.astype(str)
    era = observed.time.values.astype("datetime64[M]").astype(str)
    require(len(set(months)) == len(months), "Duplicate model months")
    require(
        np.all(np.diff(np.array(months, dtype="datetime64[M]").astype(int)) == 1),
        "Discontinuous model months",
    )
    require(
        np.array_equal(
            model.time.values.astype("datetime64[M]"),
            np.array(months, dtype="datetime64[M]") + 1,
        ),
        "Model state boundary mismatch",
    )
    positions = {m: i for i, m in enumerate(era)}
    require(all(m in positions for m in months), "ERA5 comparison month missing")
    initial = model.attrs.get("initial_month")
    return [(i, positions[m], m) for i, m in enumerate(months) if m != initial]


def region_mask(grid, bounds):
    _, south, north, west, east = bounds
    lat = grid.latitude.values[:, None]
    lon = (grid.longitude.values[None, :] + 180) % 360 - 180
    longitude = (
        (lon >= west) & (lon < east) if west < east else (lon >= west) | (lon < east)
    )
    return (lat >= south) & (lat <= north) & longitude


def summarize_rows(rows):
    usable = [r for r in rows if r.get("valid_cells", 0) > 0]
    require(len(usable) > 0, "No comparison months with valid cells")
    correlations = [
        r["spatial_correlation"] for r in usable if r["spatial_correlation"] is not None
    ]
    return {
        "months": len(usable),
        "mean_monthly_spatial_correlation": float(np.mean(correlations))
        if correlations
        else None,
        "rms_monthly_area_rmse_k": float(
            np.sqrt(np.mean([r["rmse_k"] ** 2 for r in usable]))
        ),
        "mean_monthly_area_bias_k": float(np.mean([r["bias_k"] for r in usable])),
        "hemispheric_mean_temporal_correlation": correlation(
            [r["model_mean_k"] for r in usable], [r["era5_mean_k"] for r in usable]
        ),
        **{
            f"{name}_{stat}_k": float(fn(r[f"{name}_{stat}_k"] for r in usable))
            for name in ("model", "era5")
            for stat, fn in (("minimum", min), ("maximum", max))
        },
    }


def analyse_comparison(run_dir, processed_dir):
    run_dir, processed_dir = Path(run_dir), Path(processed_dir)
    out = run_dir / "comparison"
    out.mkdir(exist_ok=True)
    summary = {
        "netcdf4_version": netCDF4.__version__,
        "interpretation": "Retrospective ERA5-related comparison, not independent forecast validation. Calendar labels compare model interval-end states to monthly ERA5 means by explicit milestone convention.",
        "statistics": "Unweighted spatial Pearson r and population SD; area-weighted means, bias and RMSE on each month's common valid ocean; summary gives equal weight to months.",
        "spinup_sensitivity": "Exclude first 24 calendar months from January 1979 (start sensitivity January 1981); not a proven complete spin-up.",
        "regions": {k: list(v) for k, v in REGIONS.items()},
        "hemispheres": {},
        "regional_skill": {},
        "source_sha256": {},
    }
    regional_rows = []
    for h in ("north", "south"):
        model_path = run_dir / f"{h}_sst.nc"
        era_path = processed_dir / f"{h}_era5_ssta.nc"
        summary["source_sha256"].update(
            {str(p): checksum(p) for p in (model_path, era_path)}
        )
        with (
            xr.open_dataset(model_path) as model,
            xr.open_dataset(era_path) as observed,
        ):
            same_grid(model, observed)
            require(
                model.sst_anomaly.attrs.get("units")
                == observed.sst_anomaly.attrs.get("units")
                == "K",
                "Comparison SST units",
            )
            valid = model.input_valid.values == 1
            area = model.cell_area.values
            aligned = aligned_months(model, observed)
            rows = []
            counts = np.zeros(valid.shape, dtype="i4")
            means = [np.zeros(valid.shape) for _ in range(2)]
            m2 = [np.zeros(valid.shape) for _ in range(2)]
            regions = {
                name: region_mask(model, b) for name, b in REGIONS.items() if b[0] == h
            }
            for i, j, month in aligned:
                m = model.sst_anomaly.isel(time=i).values.astype(float)
                e = observed.sst_anomaly.isel(time=j).values.astype(float)
                row = {"month": month, **paired_statistics(m, e, area, valid)}
                rows.append(row)
                use = valid & np.isfinite(m) & np.isfinite(e)
                counts[use] += 1
                for values, mean, variance in zip((m, e), means, m2):
                    delta = values[use] - mean[use]
                    mean[use] += delta / counts[use]
                    variance[use] += delta * (values[use] - mean[use])
                for name, region in regions.items():
                    stats = paired_statistics(m, e, area, valid & region)
                    regional_rows.append({"region": name, "month": month, **stats})
                if len(rows) % 120 == 0:
                    print(f"Compared {h}: {len(rows)} months", flush=True)
            with (out / f"{h}_monthly.csv").open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)
            summary["hemispheres"][h] = {
                "all_integrated_months": summarize_rows(rows),
                "excluding_first_24_calendar_months": summarize_rows(
                    [r for r in rows if r["month"] >= "1981-01"]
                ),
                "first_month": rows[0]["month"],
                "last_month": rows[-1]["month"],
            }
            arrays = {}
            for name, variance in zip(("model_std", "era5_std"), m2):
                result = np.full(valid.shape, np.nan)
                np.divide(variance, counts, out=result, where=counts >= 2)
                arrays[name] = (("latitude", "longitude"), np.sqrt(result))
            variability = xr.Dataset(
                arrays, coords={k: model[k] for k in ("latitude", "longitude")}
            )
            variability["paired_month_count"] = (("latitude", "longitude"), counts)
            for name in ("model_std", "era5_std"):
                variability[name].attrs = {
                    "units": "K",
                    "definition": "Temporal population SD on common finite months; >=2 samples",
                }
            variability.to_netcdf(
                out / f"{h}_temporal_variability.nc",
                engine="netcdf4",
                encoding={
                    k: {"zlib": True, "complevel": 4} for k in variability.data_vars
                },
            )
    with (out / "regional_monthly.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=regional_rows[0].keys())
        writer.writeheader()
        writer.writerows(regional_rows)
    for name in REGIONS:
        rows = [r for r in regional_rows if r["region"] == name]
        summary["regional_skill"][name] = {}
        for label, subset in (
            ("all_integrated_months", rows),
            (
                "excluding_first_24_calendar_months",
                [r for r in rows if r["month"] >= "1981-01"],
            ),
        ):
            model = np.array([r.get("model_mean_k", np.nan) for r in subset])
            era = np.array([r.get("era5_mean_k", np.nan) for r in subset])
            summary["regional_skill"][name][label] = {
                "months": len(subset),
                "temporal_correlation": correlation(model, era),
                "model_series_std_k": float(np.nanstd(model)),
                "era5_series_std_k": float(np.nanstd(era)),
                "model_to_era5_std_ratio": float(np.nanstd(model) / np.nanstd(era))
                if np.nanstd(era) > 0
                else None,
            }
    (out / "summary.json").write_text(
        json.dumps(summary, indent=2, allow_nan=False) + "\n"
    )
    comparison_figures(run_dir, processed_dir)
    return summary


def comparison_figures(run_dir, processed_dir, month="1980-05"):
    """Native maps and diagnostics; no Cartopy or regridding."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import TwoSlopeNorm

    out = Path(run_dir) / "comparison"
    maps = []
    variability = []
    series = {}
    for h in ("north", "south"):
        with (
            xr.open_dataset(Path(run_dir) / f"{h}_sst.nc") as model,
            xr.open_dataset(Path(processed_dir) / f"{h}_era5_ssta.nc") as era,
        ):
            aligned = aligned_months(model, era)
            entry = next(
                (a for a in aligned if a[2] == month), aligned[len(aligned) // 2]
            )
            i, j, month = entry
            m = model.sst_anomaly.isel(time=i).where(model.input_valid == 1).load()
            e = era.sst_anomaly.isel(time=j).where(model.input_valid == 1).load()
            common = np.isfinite(m) & np.isfinite(e)
            maps.append((m.where(common), e.where(common), (m - e).where(common)))
        with xr.open_dataset(out / f"{h}_temporal_variability.nc") as ds:
            variability.append((ds.model_std.load(), ds.era5_std.load()))
        with (out / f"{h}_monthly.csv").open() as stream:
            series[h] = list(csv.DictReader(stream))

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

    extent = max(float(abs(f).max()) for pair in maps for f in pair[:2])
    diffextent = max(float(abs(pair[2]).max()) for pair in maps)
    fig, axes = plt.subplots(3, 1, figsize=(12, 10), layout="constrained")
    for index, label in enumerate(
        ("Modelled SSTA", "ERA5 monthly SSTA", "Model − ERA5")
    ):
        extent_i = extent if index < 2 else diffextent
        for fields in maps:
            image = draw(
                fields[index],
                axes[index],
                cmap="RdBu_r",
                norm=TwoSlopeNorm(vmin=-extent_i, vcenter=0, vmax=extent_i),
            )
        axes[index].set_title(label)
        fig.colorbar(image, ax=axes[index], label="K")
    fig.suptitle(
        f"Calendar comparison {month} · model interval-end state vs ERA5 monthly mean\nNative 0.25°; common valid ocean; gray = missing"
    )
    fig.savefig(out / f"maps_{month}.png", dpi=150)
    plt.close(fig)
    vmax = max(float(f.max()) for pair in variability for f in pair)
    fig, axes = plt.subplots(2, 1, figsize=(12, 7), layout="constrained")
    for index, label in enumerate(
        (
            "Model temporal SSTA standard deviation",
            "ERA5 temporal SSTA standard deviation",
        )
    ):
        for fields in variability:
            image = draw(fields[index], axes[index], cmap="viridis", vmin=0, vmax=vmax)
        axes[index].set_title(label)
        fig.colorbar(image, ax=axes[index], label="K")
    fig.savefig(out / "temporal_variability.png", dpi=150)
    plt.close(fig)
    for name, keys in (
        ("hemispheric_means", ("model_mean_k", "era5_mean_k")),
        ("pattern_correlation", ("spatial_correlation",)),
    ):
        fig, axes = plt.subplots(
            2, 1, figsize=(12, 6), layout="constrained", sharex=True
        )
        for ax, (h, rows) in zip(axes, series.items()):
            dates = np.array([r["month"] for r in rows], dtype="datetime64[M]")
            for key in keys:
                ax.plot(
                    dates,
                    [float(r[key]) if r[key] else np.nan for r in rows],
                    label=key,
                )
            ax.axvline(
                np.datetime64("1981-01"),
                color="gray",
                linestyle="--",
                label="24-calendar-month sensitivity",
            )
            ax.set_title(h)
            ax.set_ylabel("K" if name == "hemispheric_means" else "Pearson r")
            ax.legend()
        fig.savefig(out / f"{name}.png", dpi=150)
        plt.close(fig)
    with (out / "regional_monthly.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    fig, axes = plt.subplots(5, 1, figsize=(12, 13), layout="constrained", sharex=True)
    for ax, name in zip(axes, REGIONS):
        subset = [r for r in rows if r["region"] == name]
        dates = np.array([r["month"] for r in subset], dtype="datetime64[M]")
        for key in ("model_mean_k", "era5_mean_k"):
            ax.plot(
                dates, [float(r[key]) if r[key] else np.nan for r in subset], label=key
            )
        ax.set_title(name)
        ax.set_ylabel("K")
        ax.legend()
    fig.savefig(out / "regional_time_series.png", dpi=150)
    plt.close(fig)
