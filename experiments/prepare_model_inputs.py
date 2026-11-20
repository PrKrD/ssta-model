"""Prepare the supplied local scientific inputs; run from the repository root."""

import argparse
from pathlib import Path

from ssta_model.data.prepare import prepare_inputs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument(
        "--damping-config", type=Path, default=Path("configs/surface_damping.toml")
    )
    arguments = parser.parse_args()
    prepare_inputs(arguments.data_dir, arguments.damping_config)


if __name__ == "__main__":
    main()
