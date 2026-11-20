"""Export an existing SST run to static Cesium JSON and a native-grid diagnostic."""

import argparse
from pathlib import Path

from ssta_model.data.visualization import export_visualization, native_diagnostic_map


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run-dir", type=Path, default=Path("runs/historical_surface_flux_pilot")
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("frontend/public/data/historical_surface_flux_pilot.json"),
    )
    parser.add_argument("--map-month", default="1980-05")
    args = parser.parse_args()
    report = export_visualization(args.run_dir, args.output)
    native_diagnostic_map(
        args.run_dir,
        args.run_dir / "visualization" / f"native_sst_{args.map_month}.png",
        args.map_month,
    )
    print(
        f"Exported {report['frames']} frames, {report['cells']} cells, {report['json_bytes']:,} bytes; maximum sampled error {report['maximum_sample_error_k']:.3g} K"
    )


if __name__ == "__main__":
    main()
