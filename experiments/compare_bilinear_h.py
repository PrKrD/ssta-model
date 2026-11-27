"""Analyse/export the controlled bilinear-H historical sensitivity from saved data."""

import argparse
from pathlib import Path

from ssta_model.analysis.h_sensitivity import compare_h
from ssta_model.data.diffusion_export import export_comparison


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("analyse", "export", "all"), default="all")
    args = parser.parse_args()
    run = Path("runs/historical_surface_flux_bilinear_h")
    original = Path("runs/historical_surface_flux_with_diffusion")
    baseline = Path("runs/historical_surface_flux_era5_initialised")
    processed = Path("data/processed")
    if args.stage in ("analyse", "all"):
        compare_h(run, original, baseline, processed)
    if args.stage in ("export", "all"):
        export_comparison(
            run,
            processed,
            Path("frontend/public/data/era5_comparison"),
            baseline_dir=baseline,
            original_h_dir=original,
        )


if __name__ == "__main__":
    main()
