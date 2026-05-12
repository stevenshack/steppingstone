#!/usr/bin/env python3
"""Extract C function symbols from NeXTSTEP Mach-O LC_SYMTAB.
Outputs: address hex, symbol name for all non-ObjC functions in __text.
"""

import struct, sys, os

def main(binpath, outdir):
    with open(binpath, "rb") as f:
        data = f.read()

    magic = struct.unpack_from("<I", data, 0)[0]
    if magic == 0xFEEDFACE:
        e = "<"
    elif struct.unpack_from(">I", data, 0)[0] == 0xFEEDFACE:
        e = ">"
    else:
        print(f"Not Mach-O: magic=0x{magic:08x}")
        return

    ncmds = struct.unpack_from(f"{e}I", data, 16)[0]
    off = 28

    # First pass: index sections and assign 1-based section numbers
    secs = {}          # sname -> (vaddr, vsize, foff)
    sect_to_name = {}  # 1-based index -> sname
    sect_idx = 1

    # Also find LC_SYMTAB
    symtab_off = None
    nsyms = None
    stroff = None
    strsize = None

    for _ in range(ncmds):
        cmd = struct.unpack_from(f"{e}I", data, off)[0]
        cmdsize = struct.unpack_from(f"{e}I", data, off+4)[0]

        if cmd == 1:  # LC_SEGMENT
            nsects = struct.unpack_from(f"{e}I", data, off+48)[0]
            so = off + 56
            for _ in range(nsects):
                sname = data[so:so+16].rstrip(b"\x00").decode("latin-1")
                saddr = struct.unpack_from(f"{e}I", data, so+32)[0]
                ssize = struct.unpack_from(f"{e}I", data, so+36)[0]
                sfoff = struct.unpack_from(f"{e}I", data, so+40)[0]
                secs[sname] = (saddr, ssize, sfoff)
                sect_to_name[sect_idx] = sname
                sect_idx += 1
                so += 68

        elif cmd == 2:  # LC_SYMTAB
            symtab_off = struct.unpack_from(f"{e}I", data, off+8)[0]
            nsyms = struct.unpack_from(f"{e}I", data, off+12)[0]
            stroff = struct.unpack_from(f"{e}I", data, off+16)[0]
            strsize = struct.unpack_from(f"{e}I", data, off+20)[0]

        off += cmdsize

    if symtab_off is None:
        print("  No LC_SYMTAB found")
        return

    # Read string table
    strtable = data[stroff:stroff+strsize]

    # Read nlist entries (12 bytes each)
    symbols = []
    for i in range(nsyms):
        entry_off = symtab_off + i * 12
        if entry_off + 12 > len(data):
            break
        n_strx = struct.unpack_from(f"{e}I", data, entry_off)[0]
        n_type = struct.unpack_from(f"{e}B", data, entry_off+4)[0]
        n_sect = struct.unpack_from(f"{e}B", data, entry_off+5)[0]
        n_value = struct.unpack_from(f"{e}I", data, entry_off+8)[0]

        # Only N_SECT symbols (defined in a section, not STABS debug)
        if (n_type & 0x0e) != 0x0e:
            continue

        # Skip if not in __text section
        sect_name = sect_to_name.get(n_sect, "")
        if sect_name != "__text":
            continue

        sym_name = strtable[n_strx:strtable.find(b"\x00", n_strx)].decode("latin-1", errors="replace") if n_strx < len(strtable) else ""

        # Skip empty, internal, ObjC, and debug symbols
        if not sym_name:
            continue
        if sym_name.startswith("._") or sym_name.startswith(".objc"):
            continue
        if sym_name.startswith("-"):       # ObjC method names like -[Class method]
            continue
        if sym_name.endswith(".s") or sym_name.endswith(".o"):
            continue
        if sym_name.endswith(".c") or sym_name.endswith(".m"):
            continue
        if sym_name.startswith("__"):      # compiler stabs/internals
            continue
        if ":" in sym_name:                # debug labels like function:f20
            continue

        symbols.append((n_value, sym_name))

    # Write output (same format as ObjC metadata for easy merging)
    outpath = os.path.join(outdir, "c_symbols.txt")
    with open(outpath, "w") as f:
        f.write(f"SYMBOLS: {len(symbols)} total\n")
        for addr, name in sorted(symbols):
            f.write(f"  0x{addr:06x} {name}\n")

    print(f"  {len(symbols)} C symbols -> {outpath}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <binary> [outdir]")
        sys.exit(1)
    outdir = sys.argv[2] if len(sys.argv) > 2 else os.path.dirname(sys.argv[1])
    main(sys.argv[1], outdir)
