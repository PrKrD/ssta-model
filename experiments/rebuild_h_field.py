"""Rebuild a proposed fixed H and compare masks, without integrating SST."""

import argparse

from ssta_model.data.mld_rebuild import rebuild_h


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default="data/raw/mld_dr003_ref10m_v2023.nc")
    parser.add_argument("--processed", default="data/processed")
    parser.add_argument("--diagnostics", default="runs/h_rebuild_comparison")
    parser.add_argument(
        "--output", help="New product directory; defaults to --processed"
    )
    args = parser.parse_args()
    report = rebuild_h(args.source, args.processed, args.diagnostics, args.output)
    print(report["mask_statistics"]["global"])
    print(f"Figures and report: {args.diagnostics}")


if __name__ == "__main__":
    main()
