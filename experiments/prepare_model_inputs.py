"""Prepare the supplied local scientific inputs; run from the repository root."""

import argparse
from pathlib import Path

from ssta_model.data.prepare import prepare_inputs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    arguments = parser.parse_args()
    prepare_inputs(arguments.data_dir)


if __name__ == "__main__":
    main()
