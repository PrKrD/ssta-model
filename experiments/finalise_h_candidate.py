"""Prepare and validate ERA5-targeted bilinear H, without running SST."""

import argparse

from ssta_model.data.era5_h_candidate import prepare_candidate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default="data/raw/mld_dr003_ref10m_v2023.nc")
    parser.add_argument("--processed", default="data/processed")
    parser.add_argument(
        "--output", help="Candidate product directory; defaults to --processed"
    )
    parser.add_argument("--diagnostics", default="runs/h_era5_bilinear_candidate")
    args = parser.parse_args()
    report = prepare_candidate(
        args.source, args.processed, args.diagnostics, args.output
    )
    print(
        "Can preserve baseline active mask:",
        report["can_preserve_baseline_active_mask"],
    )
    print("Report:", args.diagnostics)


if __name__ == "__main__":
    main()
