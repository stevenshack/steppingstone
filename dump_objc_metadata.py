#!/usr/bin/env python3
"""Dump ObjC metadata from NeXTSTEP Mach-O (m68k BE or i386 LE)."""

import struct, sys, os

def main(binpath, outdir):
    with open(binpath, "rb") as f:
        data = f.read()

    magic = struct.unpack_from("<I", data, 0)[0]
    if magic == 0xFEEDFACE:
        e = "<"  # LE (i386)
    else:
        magic = struct.unpack_from(">I", data, 0)[0]
        if magic == 0xFEEDFACE:
            e = ">"  # BE (m68k)
        else:
            print(f"Not Mach-O: magic=0x{magic:08x}")
            return

    ncmds = struct.unpack_from(f"{e}I", data, 16)[0]
    off = 28

    # Index all sections
    secs = {}
    for _ in range(ncmds):
        cmd = struct.unpack_from(f"{e}I", data, off)[0]
        cmdsize = struct.unpack_from(f"{e}I", data, off+4)[0]
        if cmd == 1:
            segname = data[off+8:off+24].rstrip(b"\x00").decode("latin-1")
            svm = struct.unpack_from(f"{e}I", data, off+24)[0]
            soff = struct.unpack_from(f"{e}I", data, off+32)[0]
            nsects = struct.unpack_from(f"{e}I", data, off+48)[0]
            so = off + 56
            for _ in range(nsects):
                sname = data[so:so+16].rstrip(b"\x00").decode("latin-1")
                saddr = struct.unpack_from(f"{e}I", data, so+32)[0]
                ssize = struct.unpack_from(f"{e}I", data, so+36)[0]
                sfoff = struct.unpack_from(f"{e}I", data, so+40)[0]
                secs[sname] = (saddr, ssize, sfoff)
                so += 68
        off += cmdsize

    def vm2f(vm):
        for sname, (sa, ss, sf) in secs.items():
            if sf and sa <= vm < sa + ss:
                return sf + (vm - sa)
        return 0

    def rd32(off):
        return struct.unpack_from(f"{e}I", data, off)[0]

    def resolve_name(vm, sec_name):
        if sec_name in secs:
            sa, ss, sf = secs[sec_name]
            if sa <= vm < sa + ss:
                nf = sf + (vm - sa)
                end = nf
                while end < sf + ss and data[end] != 0:
                    end += 1
                return data[nf:end].decode("latin-1", errors="replace")
        return "?"

    def read_method_list(vm, out, seen):
        """Recursively read a NeXTSTEP method list from vm address."""
        if vm in seen or not vm:
            return
        seen.add(vm)
        mf = vm2f(vm)
        if not mf or mf + 8 > len(data):
            return
        mnext = rd32(mf)       # pointer to next method list
        mcnt = rd32(mf + 4)    # count
        if mcnt < 0 or mcnt > 500000:
            return
        for i in range(mcnt):
            moff = mf + 8 + i * 12
            if moff + 12 > len(data):
                break
            mn = rd32(moff)
            imp = rd32(moff + 8)
            name = resolve_name(mn, "__meth_var_names")
            out.append((imp, name))
        if mnext:
            read_method_list(mnext, out, seen)

    # Read __class section
    lines, methods, seen = [], [], set()
    if "__class" in secs:
        ca, cs, cf = secs["__class"]
        for ci in range(cs // 40):
            coff = cf + ci * 40
            ml_vm = rd32(coff + 28)
            read_method_list(ml_vm, methods, seen)

    for imp, name in sorted(methods):
        lines.append(f"  0x{imp:06x} [{name}]")

    outpath = os.path.join(outdir, "objc_metadata.txt")
    with open(outpath, "w") as f:
        f.write(f"METHODS: {len(methods)} total\n")
        f.write("\n".join(lines))

    print(f"  {len(methods)} methods -> {outpath}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <binary> [outdir]")
        sys.exit(1)
    outdir = sys.argv[2] if len(sys.argv) > 2 else os.path.dirname(sys.argv[1])
    main(sys.argv[1], outdir)
