"""Analyse/export the controlled diffusion historical experiment from saved outputs."""

import argparse
from pathlib import Path

from ssta_model.analysis.diffusion_comparison import compare_diffusion
from ssta_model.data.diffusion_export import export_comparison


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("analyse", "export", "all"), default="all")
    parser.epilog = "Archived sensitivity workflow: reproduce retired native runs before use. Active viewer: export_historical_viewer.py."
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
            Path("runs/archived_historical_sensitivity/compare_diffusion_display"),
            baseline_dir=baseline,
        )


if __name__ == "__main__":
    main()
