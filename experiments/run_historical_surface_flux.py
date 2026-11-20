"""Run the configured historical SST experiment; reusable work lives in the package."""

import argparse
import json
from pathlib import Path

from ssta_model.core.simulation import run_experiment


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/historical_surface_flux_pilot.toml"),
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("."),
        help="Root for configuration data/output paths",
    )
    args = parser.parse_args()
    summary = run_experiment(args.config, args.root)
    print(
        json.dumps(
            {
                **summary,
                "hemispheres": {
                    h: {k: v for k, v in result.items() if k != "monthly"}
                    for h, result in summary["hemispheres"].items()
                },
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
