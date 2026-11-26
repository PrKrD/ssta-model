"""Run the explicit preparation, historical experiment, comparison and static export."""

import argparse
from pathlib import Path

from ssta_model.analysis.era5_comparison import analyse_comparison
from ssta_model.core.simulation import run_experiment
from ssta_model.data.era5 import prepare_era5


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stage", choices=("prepare", "run", "analyse", "all"), default="all"
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("data/raw/78c42a1ddf5ba77c929fd589ff5d3c61.nc"),
    )
    args = parser.parse_args()
    run = Path("runs/historical_surface_flux_era5_initialised")
    processed = Path("data/processed")
    if args.stage in ("prepare", "all"):
        prepare_era5(args.source, processed)
    if args.stage in ("run", "all"):
        run_experiment("configs/historical_surface_flux_era5_initialised.toml")
    if args.stage in ("analyse", "all"):
        analyse_comparison(run, processed)


if __name__ == "__main__":
    main()
