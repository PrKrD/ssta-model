"""Export the current saved bilinear-H model and ERA5, without old experiments."""

import argparse
from pathlib import Path

from ssta_model.data.historical_export import export_historical


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run", type=Path, default=Path("runs/historical_surface_flux_bilinear_h")
    )
    parser.add_argument("--processed", type=Path, default=Path("data/processed"))
    parser.add_argument(
        "--destination", type=Path, default=Path("frontend/public/data/era5_comparison")
    )
    args = parser.parse_args()
    export_historical(args.run, args.processed, args.destination)


if __name__ == "__main__":
    main()
