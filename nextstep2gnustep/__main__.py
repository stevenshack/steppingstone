import argparse
import sys

from nextstep2gnustep.orchestrator import run


def main():
    parser = argparse.ArgumentParser(
        prog="nextstep2gnustep",
        description="Phase 2 pipeline: translate NEXTSTEP/OPENSTEP source tree to compilable GNUstep project.",
    )
    parser.add_argument(
        "source_dir",
        nargs="?",
        help="path to Phase 1 output source directory",
    )
    parser.add_argument(
        "--output-dir", "-o",
        default="gnustep-output",
        help="output directory for GNUstep project (default: gnustep-output)",
    )
    args = parser.parse_args()

    if args.source_dir is None:
        parser.print_help()
        sys.exit(2)

    run(source_dir=args.source_dir, output_dir=args.output_dir)


if __name__ == "__main__":
    main()
