"""Static depth/mask diagnostics, independent of simulation and the frontend."""

import numpy as np
import xarray as xr


def compare_depths(current, rebuilt, area):
    old, new, weights = current.values, rebuilt.values, area.values
    common = np.isfinite(old) & np.isfinite(new)
    difference = new[common] - old[common]
    # Use identical native adjacent pairs for both versions; longitude is cyclic.
    edges = [[], []]
    for axis in (0, 1):
        use = common & np.roll(common, -1, axis=axis)
        if axis == 0:
            use[-1] = False
        for result, field in zip(edges, (old, new)):
            result.extend((np.roll(field, -1, axis=axis) - field)[use].tolist())
    return {
        "current_valid_cells": int(np.isfinite(old).sum()),
        "rebuilt_valid_cells": int(np.isfinite(new).sum()),
        "common_valid_cells": int(common.sum()),
        "current_only_cells": int((np.isfinite(old) & ~np.isfinite(new)).sum()),
        "rebuilt_only_cells": int((~np.isfinite(old) & np.isfinite(new)).sum()),
        "current_range_m": [float(np.nanmin(old)), float(np.nanmax(old))],
        "rebuilt_range_m": [float(np.nanmin(new)), float(np.nanmax(new))],
        "common_area_mean_difference_m": float(
            np.average(difference, weights=weights[common])
        ),
        "common_area_rms_difference_m": float(
            np.sqrt(np.average(difference**2, weights=weights[common]))
        ),
        "common_difference_percentiles_m": np.percentile(
            difference, [0, 5, 50, 95, 100]
        ).tolist(),
        "common_adjacent_pairs": len(edges[0]),
        "current_adjacent_rms_jump_m": float(np.sqrt(np.mean(np.square(edges[0])))),
        "rebuilt_adjacent_rms_jump_m": float(np.sqrt(np.mean(np.square(edges[1])))),
    }


def plot_comparison(baseline, proposed, masks, directory):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import BoundaryNorm, ListedColormap
    from matplotlib.patches import Patch

    current = xr.full_like(proposed.H, np.nan)
    for field in baseline:
        current.loc[{"latitude": field.latitude}] = field
    rebuilt = proposed.H.where(abs(proposed.latitude) >= 20)
    difference = rebuilt - current
    vmax = max(float(current.max()), float(rebuilt.max()))
    limit = max(float(abs(difference).max()), 1e-12)

    def draw(field, ax, bounds, **options):
        field = (
            field.assign_coords(longitude=(field.longitude + 180) % 360 - 180)
            .sortby("longitude")
            .sortby("latitude")
        )
        picture = ax.pcolormesh(
            field.longitude,
            field.latitude,
            field,
            shading="nearest",
            rasterized=True,
            **options,
        )
        ax.set(
            xlim=bounds[:2],
            ylim=bounds[2:],
            xlabel="Longitude (° east)",
            ylabel="Latitude (° north)",
        )
        ax.set_facecolor("#c9cdd2")
        return picture

    for name, bounds in (
        ("global_H_comparison", (-180, 180, -90, 90)),
        ("north_atlantic_H_detail", (-80, 20, 30, 75)),
    ):
        fig, axes = plt.subplots(3, 1, figsize=(13, 11), layout="constrained")
        for ax, field, title in zip(
            axes,
            (current, rebuilt, difference),
            (
                "Current H · containing source cell · ERA5 ocean domain",
                "Proposed H · mask-aware bilinear · remapped MLD ocean domain",
                "Proposed minus current · common finite support only",
            ),
        ):
            diff = field is difference
            image = draw(
                field,
                ax,
                bounds,
                cmap="RdBu_r" if diff else "viridis",
                vmin=-limit if diff else 0,
                vmax=limit if diff else vmax,
            )
            ax.set_title(title)
            fig.colorbar(
                image,
                ax=ax,
                label="Depth difference (m)" if diff else "Fixed mixed-layer depth (m)",
            )
        fig.suptitle(
            "Maximum monthly de Boyer Montégut (2023) MLD · native 0.25° · no SST rerun\nGray: missing/omitted · shared H limits; independent symmetric difference limits"
        )
        fig.savefig(directory / f"{name}.png", dpi=170)
        plt.close(fig)
    colours = ["#d0d0d0", "#e58635", "#973cb3", "#237ca9"]
    cmap = ListedColormap(colours)
    norm = BoundaryNorm(np.arange(-0.5, 4), 4)
    for name, bounds in (
        ("mask_comparison", (-180, 180, -90, 90)),
        ("north_atlantic_mask_detail", (-80, 20, 30, 75)),
    ):
        fig, axes = plt.subplots(3, 1, figsize=(13, 11), layout="constrained")
        for ax, field, title in zip(
            axes,
            (masks.era5_ocean * 3, masks.mld_ocean * 3, masks.mask_category),
            (
                "Current ERA5 ocean (lsm < 0.5)",
                "Old MLD ocean (source mask==1; spherical overlap ≥50%)",
                "Explicit mask agreement / disagreement",
            ),
        ):
            draw(field, ax, bounds, cmap=cmap, norm=norm)
            ax.set_title(title)
        axes[-1].legend(
            handles=[
                Patch(color=c, label=t)
                for c, t in zip(
                    colours,
                    (
                        "Land in both",
                        "Ocean only in ERA5",
                        "Ocean only in MLD",
                        "Ocean in both",
                    ),
                )
            ],
            loc="lower center",
            ncol=4,
        )
        fig.suptitle(
            "Independent ocean-mask comparison · current 0.25° grid · no preferred-mask substitution"
        )
        fig.savefig(directory / f"{name}.png", dpi=170)
        plt.close(fig)


def write_report(report, directory):
    lines = [
        "# Fixed H rebuild and explicit ocean-mask comparison",
        "",
        "Proposed products only. **No historical SST or diffusion rerun was performed.** Baseline H, ERA5 masks, forcing, damping, existing scientific outputs and viewer assets are unchanged.",
        "",
        "Source: local `data/raw/mld_dr003_ref10m_v2023.nc`, de Boyer Montégut (2023), https://doi.org/10.17882/91774. Source-ocean rule: `mask == 1`. H is the maximum available positive finite monthly `mld_dr003` value; source-land values are excluded before reduction. Partial-month support is retained; no n_obs threshold is added.",
        "",
        "Methods adapt the inspected `globetest/backend/app/mld.py`: exact spherical overlap of rectangular source/target footprints, periodic longitude, target ocean at ≥50% area (ties ocean); bilinear interpolation of source fixed H, removing invalid corners and renormalising remaining positive weights. No low-pass filter or nearest-valid search is applied. A numerical tie tolerance of 16 float64 eps protects mathematical half-area ties.",
        "",
        "The current target includes polar centres absent from the old interpolation grid. Source centres stop at ±89.5°: proposed H is missing beyond them, without extrapolation. The ocean mask still covers clipped polar footprints. Latitude order and all 0.25° native centres are preserved.",
        "",
        "## Mask statistics",
        "",
        "Northern hemisphere includes the equator; southern hemisphere is latitude <0. Extratropical summaries use inclusive ±20° centre selection. Cell fractions divide by all selected cells; area fractions divide by the entire selected spherical domain. Union-ocean area fractions are provided separately in summary.json.",
        "",
        "| Domain | ERA5 ocean | MLD ocean | ERA5 only | MLD only | Disagree | Cell fraction | Domain area fraction |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, s in report["mask_statistics"].items():
        lines.append(
            f"| {name} | {s['era5_ocean_cells']} | {s['mld_ocean_cells']} | {s['era5_only_cells']} | {s['mld_only_cells']} | {s['disagreement_cells']} | {s['disagreement_cell_fraction']:.4%} | {s['disagreement_domain_area_fraction']:.4%} |"
        )
    lines += [
        "",
        "The mask maps should be inspected for coastal belts, marginal seas, inland waters and high-latitude geometry. These are different mask definitions/resolutions, not evidence that one product is universally preferable. Counts overrepresent high latitudes relative to area; the separate |latitude|≥60° row makes that distinction explicit.",
        "",
        "## H comparison",
        "",
        "Depth differences use common finite support only; separate coverage counts expose domain changes. Adjacent RMS jumps use exactly the same unweighted native N/S and periodic E/W pairs in both fields; they measure grid-scale roughness in metres, not a physical gradient per kilometre or area-conservation property.",
        "",
        "| Domain | Current / proposed valid cells | Common cells | Mean ΔH (m), area weighted | RMS ΔH (m), area weighted | Adjacent RMS jump, old → new (m) |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name, s in report["H_comparison"].items():
        lines.append(
            f"| {name} | {s['current_valid_cells']} / {s['rebuilt_valid_cells']} | {s['common_valid_cells']} | {s['common_area_mean_difference_m']:.4f} | {s['common_area_rms_difference_m']:.4f} | {s['current_adjacent_rms_jump_m']:.4f} → {s['rebuilt_adjacent_rms_jump_m']:.4f} |"
        )
    lines += [
        "",
        "## Products and interpretation",
        "",
        "Proposed hemispheric products `data/processed/north_surface_h_bilinear.nc` and `south_surface_h_bilinear.nc` contain float64 H (m), minimum contributing month count, valid-corner weight and remapped MLD mask. They deliberately omit runtime input_valid: selecting a future model domain requires an explicit decision about ERA5/MLD disagreement, forcing coverage, observed initialization and polar support. `data/processed/mld_mask_remapped.nc` contains both masks, overlap fraction, agreement/disagreement flags, four directional categories and cell areas. Baseline surface files remain the explicit reference.",
        "",
        "Figures: [global H comparison](global_H_comparison.png), [North Atlantic H detail](north_atlantic_H_detail.png), [global masks](mask_comparison.png), [North Atlantic masks](north_atlantic_mask_detail.png). H panels use shared sequential limits; differences have their own zero-centred range. Tropical H is omitted to match the baseline's extratropical scope; masks cover the full sphere.",
        "",
        "Bilinear interpolation redistributes source values without creating values outside valid corner ranges. It is not heat-capacity-conservative regridding and should not be treated as a validated improvement in physical accuracy. Mask changes alter geographical support independently of interpolation; coastal weights can rely on a single source-ocean corner. Do not automatically replace the ERA5 mask or feed these proposed files into a run. Resolve the domain and polar policy before a controlled historical rerun.",
        "",
        "summary.json records raw/baseline/product hashes, generation time, numerical/software provenance, coverage and reproducible statistics. All original processed NetCDF and JSON products were rehashed after generation. The raw source was also unchanged. Generated products and figures are Git-ignored.",
    ]
    (directory / "report.md").write_text("\n".join(lines) + "\n")
