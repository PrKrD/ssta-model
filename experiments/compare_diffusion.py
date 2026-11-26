"""Analyse/export the controlled diffusion historical experiment from saved outputs."""

import argparse
from pathlib import Path

from ssta_model.analysis.diffusion_comparison import compare_diffusion
from ssta_model.data.diffusion_export import export_comparison


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("analyse", "export", "all"), default="all")
    args = parser.parse_args()
    diffusion = Path("runs/historical_surface_flux_with_diffusion")
    baseline = Path("runs/historical_surface_flux_era5_initialised")
    processed = Path("data/processed")
    if args.stage in ("analyse", "all"):
        compare_diffusion(diffusion, baseline, processed)
    if args.stage in ("export", "all"):
        export_comparison(
            diffusion,
            processed,
            Path("frontend/public/data/era5_comparison"),
            baseline_dir=baseline,
        )


if __name__ == "__main__":
    main()
