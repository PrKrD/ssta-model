"""ERA5-targeted fixed H candidate; preserve selected inputs and active domain."""

import csv
import json
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import xarray as xr

from ssta_model.data.mld_rebuild import bilinear_depth, save_product, source_fixed_depth
from ssta_model.data.model_inputs import (
    SPATIAL,
    extratropics,
    require,
    same_grid,
    simulation_mask,
    spherical_cell_areas,
)
from ssta_model.data.prepare import checksum


def retain_baseline_poles(interpolated, latitude, ocean, baseline, active):
    """Retain baseline H only outside ±89.5° on already active ERA5 ocean cells."""
    interpolated, baseline = np.asarray(interpolated), np.asarray(baseline)
    ocean, active = np.asarray(ocean), np.asarray(active)
    require(
        interpolated.shape == baseline.shape == ocean.shape == active.shape
        and ocean.dtype == active.dtype == bool
        and len(latitude) == baseline.shape[0],
        "Polar retention shapes/boolean masks differ",
    )
    require(np.all(~active | ocean), "Baseline active cells outside ERA5 ocean")
    require(
        np.all(np.isfinite(baseline[active]) & (baseline[active] > 0)),
        "Invalid baseline active H",
    )
    outside = abs(np.asarray(latitude)[:, None]) > 89.5
    retained = outside & ocean & active
    result = np.where(ocean & ~outside, interpolated, np.nan).astype("f8")
    result[retained] = baseline[retained]
    return result, retained


def prepare_candidate(source, processed, diagnostics, output=None):
    """Recompute from the original source with ERA5 target mask; no model integration."""
    from ssta_model.analysis.h_candidate import (
        candidate_statistics,
        plot_candidate,
        write_report,
    )

    source, processed, diagnostics = map(Path, (source, processed, diagnostics))
    output = processed if output is None else Path(output)
    paths = [output / f"{h}_surface_h_era5_bilinear.nc" for h in ("north", "south")]
    require(not any(p.exists() for p in paths), "Candidate outputs already exist")
    require(not diagnostics.exists(), "Candidate diagnostics already exist")
    protected = [
        source,
        *sorted(processed.glob("*.nc")),
        *sorted(processed.glob("*.json")),
    ]
    hashes = {str(p): checksum(p) for p in protected}
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    implementation = [Path(__file__), Path(__file__).with_name("mld_rebuild.py")]
    provenance = {
        "prepared_by": "ssta_model.data.era5_h_candidate",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "source_file": str(source),
        "source_sha256": hashes[str(source)],
        "source_product": "de Boyer Montégut (2023); https://doi.org/10.17882/91774",
        "source_values": "Maximum available positive finite monthly mld_dr003 (m); original mask==1; decoded fill values missing; no n_obs threshold",
        "target_mask_file": str(processed / "era5_ocean_mask.nc"),
        "target_mask_sha256": hashes[str(processed / "era5_ocean_mask.nc")],
        "target_mask": "Existing ERA5 land_fraction < 0.5; exact stored ocean classification checked",
        "regridding": "Direct periodic mask-aware bilinear of original source fixed H with ERA5 target mask; positive valid-corner weights renormalised; no old-mask product used",
        "polar_exception": "Only |latitude|>89.5: retain containing-cell baseline H where baseline input_valid==1 and ERA5 ocean; no extrapolation or coastal filling",
        "domain_policy": "baseline_input_valid copied for explicit comparison only; new finite H never automatically activates cells; runtime products/configuration unchanged",
        "status": "Candidate only; no historical SST/diffusion rerun or Cesium changes",
        "code_revision": revision,
        "implementation_sha256": json.dumps(
            {str(p): checksum(p) for p in implementation}, sort_keys=True
        ),
        "versions": json.dumps(
            {
                "python": platform.python_version(),
                "numpy": np.__version__,
                "xarray": xr.__version__,
            }
        ),
    }
    report = {"provenance": provenance, "hemispheres": {}}
    products, baseline_fields, gaps = [], [], []
    with (
        xr.open_dataset(source, decode_times=False) as raw,
        xr.open_dataset(processed / "era5_ocean_mask.nc") as target,
    ):
        _, fixed, counts = source_fixed_depth(raw)
        require(
            np.all(np.diff(target.latitude) == -0.25)
            and np.all(np.diff(target.longitude) == 0.25),
            "Expected existing 0.25-degree grid",
        )
        require(
            np.isin(target.ocean, [0, 1]).all(), "Invalid ERA5 ocean classification"
        )
        require(
            np.all(
                np.isfinite(target.land_fraction.values)
                & (target.land_fraction.values >= 0)
                & (target.land_fraction.values <= 1)
            ),
            "Invalid ERA5 land fractions",
        )
        require(
            np.array_equal(target.ocean.values == 1, target.land_fraction.values < 0.5),
            "ERA5 mask differs from lsm < 0.5",
        )
        areas = spherical_cell_areas(target)
        for h in ("north", "south"):
            wet = extratropics(target, h)
            with xr.open_dataset(processed / f"{h}_surface.nc") as baseline:
                same_grid(baseline, wet)
                require(baseline.H.attrs.get("units") == "m", "Baseline H units")
                require(
                    np.isin(baseline.input_valid, [0, 1]).all(),
                    "Invalid baseline active mask",
                )
                ocean = wet.ocean.values == 1
                active = baseline.input_valid.values == 1
                # Recompute with ERA5 target mask: never remask the prior MLD-domain result.
                interpolated, coverage, weight = bilinear_depth(
                    fixed,
                    counts,
                    raw.lat.values,
                    raw.lon.values,
                    wet.latitude.values,
                    wet.longitude.values,
                    ocean,
                )
                candidate, retained = retain_baseline_poles(
                    interpolated, wet.latitude.values, ocean, baseline.H.values, active
                )
                require(
                    np.all(np.isnan(candidate[~ocean])), "Candidate H over ERA5 land"
                )
                require(
                    np.all(candidate[np.isfinite(candidate)] > 0),
                    "Nonpositive candidate H",
                )
                supported = np.isfinite(interpolated)
                missing = ocean & ~np.isfinite(candidate)
                flags = supported.astype("i1") + 2 * retained.astype("i1")
                product = xr.Dataset(
                    {
                        "H": (SPATIAL, candidate, {"units": "m"}),
                        "era5_ocean": (SPATIAL, ocean.astype("i1")),
                        "baseline_input_valid": (
                            SPATIAL,
                            active.astype("i1"),
                            {
                                "description": "Preserved baseline active mask; not a recomputed runtime mask"
                            },
                        ),
                        "support_method": (
                            SPATIAL,
                            flags,
                            {
                                "flag_values": np.arange(3, dtype="i1"),
                                "flag_meanings": "unavailable bilinear polar_baseline_retained",
                            },
                        ),
                        "contributing_month_count_min": (
                            SPATIAL,
                            coverage,
                            {
                                "units": "1",
                                "description": "Bilinear contributor coverage only; zero for unavailable or polar-retained cells",
                            },
                        ),
                        "valid_corner_weight": (
                            SPATIAL,
                            weight,
                            {
                                "units": "1",
                                "description": "Before renormalisation; zero for unavailable or polar-retained cells",
                            },
                        ),
                        "unavailable_in_era5": (SPATIAL, missing.astype("i1")),
                    },
                    coords={name: wet[name].copy() for name in SPATIAL},
                    attrs={
                        **provenance,
                        "hemisphere": h,
                        "baseline_file": str(processed / f"{h}_surface.nc"),
                        "baseline_sha256": hashes[str(processed / f"{h}_surface.nc")],
                    },
                )
                for name in (
                    "era5_ocean",
                    "baseline_input_valid",
                    "support_method",
                    "unavailable_in_era5",
                ):
                    product[name].attrs["units"] = "1"
                report["hemispheres"][h] = candidate_statistics(
                    baseline,
                    product,
                    extratropics(areas.to_dataset(name="area"), h).area,
                )
                with xr.open_dataset(processed / f"{h}_regression.nc") as regression:
                    potential = simulation_mask(product, regression, wet, h).values == 1
                    report["hemispheres"][h]["automatically_recomputed_mask_gains"] = (
                        int((potential & ~active).sum())
                    )
                    report["hemispheres"][h]["automatically_recomputed_mask_losses"] = (
                        int((~potential & active).sum())
                    )
                for y, x in zip(*np.where(missing)):
                    gaps.append(
                        {
                            "hemisphere": h,
                            "latitude": float(wet.latitude.values[y]),
                            "longitude": float(wet.longitude.values[x]),
                            "baseline_input_valid": int(active[y, x]),
                            "baseline_H_m": float(baseline.H.values[y, x])
                            if np.isfinite(baseline.H.values[y, x])
                            else "",
                            "reason": "no valid positive-weight source support",
                        }
                    )
                baseline_fields.append(baseline.H.load())
                products.append(product)
    diagnostics.mkdir(parents=True)
    output.mkdir(parents=True, exist_ok=True)
    for product, path in zip(products, paths):
        save_product(product, path)
    with (diagnostics / "unsupported_era5_cells.csv").open("w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "hemisphere",
                "latitude",
                "longitude",
                "baseline_input_valid",
                "baseline_H_m",
                "reason",
            ],
        )
        writer.writeheader()
        writer.writerows(gaps)
    report["can_preserve_baseline_active_mask"] = all(
        r["baseline_active_cells_without_H"] == 0
        for r in report["hemispheres"].values()
    )
    plot_candidate(
        baseline_fields,
        products,
        diagnostics,
        target.latitude.values,
        target.longitude.values,
    )
    for p, digest in hashes.items():
        require(checksum(Path(p)) == digest, f"Preserved input changed: {p}")
    report["preserved_sha256"] = hashes
    report["products"] = {str(p): checksum(p) for p in paths}
    (diagnostics / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
    write_report(report, diagnostics)
    return report
