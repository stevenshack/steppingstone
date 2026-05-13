import argparse
import sys

from app2source.orchestrator import run


def main():
    parser = argparse.ArgumentParser(
        prog="app2source",
        description="Phase 1 pipeline: extract readable source code from a NEXTSTEP/OPENSTEP Mach-O binary.",
    )
    parser.add_argument(
        "macho",
        nargs="?",
        help="path to Mach-O binary to process",
    )
    parser.add_argument(
        "--output-dir", "-o",
        default="app2source-output",
        help="output directory for generated source files (default: app2source-output)",
    )
    args = parser.parse_args()

    if args.macho is None:
        parser.print_help()
        sys.exit(2)

    run(macho_path=args.macho, output_dir=args.output_dir)


if __name__ == "__main__":
    main()
