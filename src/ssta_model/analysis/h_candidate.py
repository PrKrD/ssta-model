"""Coverage and static diagnostics for the ERA5-targeted fixed-H candidate."""

import numpy as np
import xarray as xr

from ssta_model.analysis.h_comparison import compare_depths, plot_depth_comparison
from ssta_model.data.model_inputs import EARTH_RADIUS_M


def candidate_statistics(baseline, candidate, area):
    ocean = candidate.era5_ocean.values == 1
    active = candidate.baseline_input_valid.values == 1
    old, new = baseline.H.values, candidate.H.values
    finite = np.isfinite(new)
    common = np.isfinite(old) & finite
    missing = ocean & ~finite
    coastal = np.zeros(ocean.shape, bool)
    for shift in (-1, 1):
        coastal |= ocean & ~np.roll(ocean, shift, axis=1)
    coastal[1:] |= ocean[1:] & ~ocean[:-1]
    coastal[:-1] |= ocean[:-1] & ~ocean[1:]
    # No latitude wrapping and no fictitious land beyond a domain edge.
    statistics = compare_depths(baseline.H, candidate.H, area)
    difference = new - old
    maximum = np.unravel_index(np.nanargmax(abs(difference)), difference.shape)
    statistics.update(
        {
            "era5_ocean_cells": int(ocean.sum()),
            "era5_ocean_cells_with_candidate_H": int((ocean & finite).sum()),
            "newly_valid_H_cells": int((finite & ~np.isfinite(old)).sum()),
            "lost_valid_H_cells": int((~finite & np.isfinite(old)).sum()),
            "baseline_active_cells": int(active.sum()),
            "baseline_active_cells_without_H": int((active & ~finite).sum()),
            "era5_ocean_without_bilinear_support": int(
                (ocean & (candidate.support_method.values != 1)).sum()
            ),
            "polar_baseline_retained_cells": int(
                (candidate.support_method.values == 2).sum()
            ),
            "era5_ocean_without_candidate_H": int(missing.sum()),
            "unsupported_ocean_area_m2": float(area.values[missing].sum()),
            "unsupported_ocean_area_fraction": float(
                area.values[missing].sum() / area.values[ocean].sum()
            ),
            "coastal_era5_cells": int(coastal.sum()),
            "coastal_cells_with_candidate_H": int((coastal & finite).sum()),
            "unsupported_coastal_cells": int((coastal & missing).sum()),
            "bilinear_cells_with_partial_corner_weight": int(
                (
                    (candidate.valid_corner_weight.values > 0)
                    & (candidate.valid_corner_weight.values < 1 - 1e-12)
                ).sum()
            ),
            "maximum_absolute_difference_m": float(abs(difference[maximum])),
            "maximum_difference_location": {
                "latitude": float(candidate.latitude.values[maximum[0]]),
                "longitude": float(candidate.longitude.values[maximum[1]]),
                "signed_difference_m": float(difference[maximum]),
            },
        }
    )
    gradients = [[], []]
    lat = candidate.latitude.values
    lon = candidate.longitude.values
    # Parallel centre distances for zonal faces; zero-distance exact-pole links omitted.
    distances = (
        np.broadcast_to(
            np.r_[abs(np.diff(lat)), np.nan][:, None]
            * np.pi
            / 180
            * EARTH_RADIUS_M
            / 1000,
            new.shape,
        ),
        np.cos(np.deg2rad(lat))[:, None]
        * np.deg2rad(np.diff(np.r_[lon, lon[0] + 360]))[None, :]
        * EARTH_RADIUS_M
        / 1000,
    )
    for axis, distance in enumerate(distances):
        use = (
            common
            & np.roll(common, -1, axis=axis)
            & (distance > 1e-9)
            & np.isfinite(distance)
        )
        if axis == 0:
            use[-1] = False
        for values, field in zip(gradients, (old, new)):
            values.extend(
                ((np.roll(field, -1, axis=axis) - field)[use] / distance[use]).tolist()
            )
    statistics["common_gradient_faces"] = len(gradients[0])
    statistics["current_rms_adjacent_gradient_m_per_km"] = float(
        np.sqrt(np.mean(np.square(gradients[0])))
    )
    statistics["candidate_rms_adjacent_gradient_m_per_km"] = float(
        np.sqrt(np.mean(np.square(gradients[1])))
    )
    return statistics


def plot_candidate(baseline, products, directory, latitude, longitude):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import BoundaryNorm, ListedColormap
    from matplotlib.patches import Patch

    full = xr.DataArray(
        np.full((len(latitude), len(longitude)), np.nan),
        dims=("latitude", "longitude"),
        coords={"latitude": latitude, "longitude": longitude},
    )
    proposed = full.copy()
    original = full.copy()
    availability = full.copy()
    for current, product in zip(baseline, products):
        original.loc[{"latitude": current.latitude}] = current
        proposed.loc[{"latitude": product.latitude}] = product.H
        flags = product.support_method.values.copy()
        wet = product.era5_ocean.values == 1
        flags[wet & (flags == 0)] = 3
        flags[np.isfinite(product.H.values) & ~np.isfinite(current.values)] = 4
        availability.loc[{"latitude": product.latitude}] = flags
    plot_depth_comparison(
        baseline,
        proposed.to_dataset(name="H"),
        directory,
        "ERA5 ocean domain; baseline H retained beyond ±89.5° on baseline active cells",
    )
    difference = proposed - original

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
        ax.set_facecolor("#d0d0d0")
        return image

    fig, ax = plt.subplots(figsize=(13, 5), layout="constrained")
    bound = float(abs(difference).max())
    image = draw(
        difference, ax, cmap="RdBu_r", vmin=-max(bound, 1e-12), vmax=max(bound, 1e-12)
    )
    ax.set_title(
        "ERA5-targeted candidate minus original H · common finite native cells · no SST rerun"
    )
    fig.colorbar(image, ax=ax, label="Depth difference (m)")
    fig.savefig(directory / "candidate_minus_baseline_H.png", dpi=170)
    plt.close(fig)
    colours = ["#d0d0d0", "#287da8", "#9256aa", "#d33333", "#30a275"]
    fig, ax = plt.subplots(figsize=(13, 6), layout="constrained")
    draw(
        availability,
        ax,
        cmap=ListedColormap(colours),
        norm=BoundaryNorm(np.arange(-0.5, 5), 5),
    )
    ax.set_title("Candidate H support inside ERA5 ocean · extratropical native grid")
    ax.legend(
        handles=[
            Patch(color=c, label=t)
            for c, t in zip(
                colours,
                (
                    "ERA5 land / omitted tropics",
                    "Bilinear supported",
                    "Polar baseline retained",
                    "ERA5 ocean: H unavailable",
                    "New H on previously unsupported cells",
                ),
            )
        ],
        loc="lower center",
        ncol=2,
    )
    fig.savefig(directory / "unavailable_H_in_era5_ocean.png", dpi=170)
    plt.close(fig)


def write_report(report, directory):
    safe = report["can_preserve_baseline_active_mask"]
    lines = [
        "# ERA5-targeted bilinear fixed-H candidate",
        "",
        "**No historical SST or diffusion run was performed.** Runtime H, forcing, damping, diffusivity, polar-cap solver and Cesium are unchanged. Both the containing-cell baseline and previous MLD-mask bilinear products are preserved.",
        "",
        "The candidate is recomputed from original de Boyer Montégut (2023) source monthly depths using mask==1, maximum positive finite monthly MLD, and the existing periodic mask-aware bilinear kernel. The target mask is the existing ERA5 lsm<0.5 classification, independently checked against stored ocean flags. No previous bilinear result is remasked. Invalid source corners are removed and positive weights renormalised. Wholly unsupported cells remain missing; no coastal filling or zeros are introduced.",
        "",
        "For |latitude|>89.5° only, baseline H is retained exactly where baseline input_valid==1 and ERA5 ocean. This is a limited reuse of existing containing-cell values, not extrapolation. At these cells support_method=2 and bilinear weight/coverage remain zero. No diffusion polar-cap treatment changes.",
        "",
        "## Coverage and domain",
        "",
        "| Domain | ERA5 ocean | Candidate valid H | Newly valid / lost | Baseline active gaps | Polar retained | Unsupported ERA5 ocean |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for h, s in report["hemispheres"].items():
        lines.append(
            f"| {h} | {s['era5_ocean_cells']} | {s['era5_ocean_cells_with_candidate_H']} | {s['newly_valid_H_cells']} / {s['lost_valid_H_cells']} | {s['baseline_active_cells_without_H']} | {s['polar_baseline_retained_cells']} | {s['era5_ocean_without_candidate_H']} |"
        )
    lines += [
        "",
        f"All baseline active cells have positive finite candidate H: **{safe}**. The unchanged baseline_input_valid is included for inspection; no runtime input_valid is recomputed or selected. Newly supported cells must remain inactive if the existing domain is to be preserved. Unsupported ocean coordinates and baseline-active status are listed explicitly in [unsupported_era5_cells.csv](unsupported_era5_cells.csv). If any row has baseline_input_valid=1, domain preservation is unresolved; no unsupported coastal filling is performed.",
        "",
        "Coastal cells mean ERA5 ocean with at least one immediate native N/S/E/W land neighbour, with periodic longitude and no latitude wrap. Coverage details and area fractions of unavailable H appear in summary.json. Pure bilinear-support counts exclude the polar exception; final unavailable counts include it.",
        "",
        "## Depth and gradient changes",
        "",
        "Differences use common finite native cells. Means/RMS are weighted by existing spherical cell areas. Adjacent RMS jumps use common N/S and periodic E/W pairs. Physical gradients divide those temperature-independent depth jumps by meridional/parallel centre distances (m/km); co-located exact-pole zonal faces are excluded.",
        "",
        "| Domain | Mean ΔH (m) | RMS ΔH (m) | Maximum absolute ΔH (m) | RMS adjacent jump old → new (m) | RMS gradient old → new (m/km) |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for h, s in report["hemispheres"].items():
        lines.append(
            f"| {h} | {s['common_area_mean_difference_m']:.5f} | {s['common_area_rms_difference_m']:.5f} | {s['maximum_absolute_difference_m']:.5f} | {s['current_adjacent_rms_jump_m']:.5f} → {s['rebuilt_adjacent_rms_jump_m']:.5f} | {s['current_rms_adjacent_gradient_m_per_km']:.5f} → {s['candidate_rms_adjacent_gradient_m_per_km']:.5f} |"
        )
    lines += [
        "",
        "## Coastal support and extrema",
        "",
        "| Domain | Coastal ocean cells | Coastal H available | Coastal H missing | Partial-corner bilinear cells (whole domain) |",
        "|---|---:|---:|---:|---:|",
    ]
    for h, s in report["hemispheres"].items():
        lines.append(
            f"| {h} | {s['coastal_era5_cells']} | {s['coastal_cells_with_candidate_H']} | {s['unsupported_coastal_cells']} | {s['bilinear_cells_with_partial_corner_weight']} |"
        )
    for h, s in report["hemispheres"].items():
        location = s["maximum_difference_location"]
        lines.append(
            f"\nLargest absolute difference in {h}: {location['signed_difference_m']:.5f} m at {location['latitude']}° N, {location['longitude']}° E (longitude convention 0–360°)."
        )
    lines += [
        "",
        "## Inspection and use",
        "",
        "Figures: [global original/candidate H](global_H_comparison.png), [North Atlantic detail](north_atlantic_H_detail.png), [candidate minus baseline](candidate_minus_baseline_H.png), [unavailable H in ERA5 ocean](unavailable_H_in_era5_ocean.png). Original/candidate depths share sequential limits; differences use a zero-centred scale. Tropical H is omitted to match the scientific model domain.",
        "",
        "The candidate files are named north_surface_h_era5_bilinear.nc and south_surface_h_era5_bilinear.nc. H remains float64 in metres. Flags distinguish bilinear support, limited polar retention and missing H. baseline_input_valid is the exact preserved mask, not an activation request. Candidate data are not installed into the model by this preparation command. The current runtime validator expects input_valid to equal its automatically derived finite-H/forcing mask. Merely replacing H while retaining the old mask would therefore fail validation where additional H becomes finite; recomputing that mask would expand the domain. A later activation must explicitly support preserving the baseline mask (or explicitly mask candidate H outside it), without weakening other validation. No runtime code is changed here. Per-hemisphere automatic-mask gains/losses are recorded in summary.json.",
        "",
        "Coverage compatibility does not establish scientific accuracy or unchanged dynamics. Bilinear H alters heat capacity and face conductances; it is not a conservative heat-capacity remap. Coastal renormalisation may use partial source support and does not resolve sub-grid barriers. The polar exception is explicit and exact. Any future rerun must deliberately preserve the baseline active mask and initial-condition policy rather than automatically admitting newly finite cells.",
        "",
        "summary.json includes raw/target/baseline hashes, versions, generation time, code identity, output hashes, and post-generation verification of every existing processed scientific product. New NetCDF files passed exact decoded-value and coordinate round-trip validation. Generated products and diagnostics are Git-ignored.",
    ]
    (directory / "report.md").write_text("\n".join(lines) + "\n")
