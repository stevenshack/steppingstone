#!/usr/bin/env python3
import argparse
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.binary_reader import (
    read_macho_header,
    extract_load_commands,
    index_segments,
    index_sections,
    extract_symbols,
    extract_objc_metadata,
    MachOError,
)

CPU_TYPE_I386 = 7

_CPU_ARCH_MAP = {
    7: "i386",
    18: "powerpc",
    12: "arm",
    16777228: "x86_64",
}


def parse_binary(binpath, manifest_only=False):
    header = read_macho_header(binpath)
    data = header["data"]
    endian = header["endian"]
    cputype = header["cputype"]

    if cputype != CPU_TYPE_I386:
        arch_name = _CPU_ARCH_MAP.get(cputype, f"cpu_type_0x{cputype:x}")
        raise MachOError(
            f"{binpath}: unsupported CPU type {cputype} ({arch_name}), "
            "only i386 is supported"
        )

    load_commands = extract_load_commands(data, endian)
    segments = index_segments(data, endian)
    raw_sections = index_sections(data, endian)
    sections = {}
    for sname, (vaddr, size, file_offset) in raw_sections.items():
        sections[sname] = {
            "vaddr": vaddr,
            "size": size,
            "file_offset": file_offset,
        }

    if manifest_only:
        symbols = []
        objc_classes = []
    else:
        symbols = extract_symbols(data, endian, raw_sections)
        objc_classes = extract_objc_metadata(data, endian, raw_sections)

    manifest = {
        "binary_path": os.path.abspath(binpath),
        "format": "mach-o",
        "architecture": _CPU_ARCH_MAP.get(cputype, "i386"),
        "endian": "little" if endian == "<" else "big",
        "load_commands": load_commands,
        "segments": segments,
        "sections": sections,
        "symbols": symbols,
        "objc_classes": objc_classes,
    }

    return manifest


def main():
    parser = argparse.ArgumentParser(description="Parse a NeXTSTEP Mach-O binary")
    parser.add_argument("binary", help="Path to the Mach-O binary")
    parser.add_argument("--output-dir", help="Directory to write output files")
    parser.add_argument(
        "--manifest-only",
        action="store_true",
        help="Only output the JSON manifest (no additional files)",
    )
    args = parser.parse_args()

    if not os.path.exists(args.binary):
        print(f"error: {args.binary}: no such file", file=sys.stderr)
        sys.exit(1)
    if os.path.isdir(args.binary):
        print(f"error: {args.binary}: is a directory", file=sys.stderr)
        sys.exit(1)

    try:
        manifest = parse_binary(args.binary, manifest_only=args.manifest_only)
    except MachOError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"error: {args.binary}: {e}", file=sys.stderr)
        sys.exit(1)

    manifest_json = json.dumps(manifest, indent=2)

    if args.output_dir:
        os.makedirs(args.output_dir, exist_ok=True)
        manifest_path = os.path.join(args.output_dir, "manifest.json")
        with open(manifest_path, "w") as f:
            f.write(manifest_json)
        print(f"manifest -> {manifest_path}", file=sys.stderr)

    print(manifest_json)


if __name__ == "__main__":
    main()
