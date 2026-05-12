#!/bin/bash
# Full NeXTSTEP binary analysis pipeline (no decompiler)
set -e
BIN="$1"
DIR=$(dirname "$BIN")
NAME=$(basename "$BIN")
I386="${DIR}/${NAME}.i386"
OUTDIR="${DIR}/analysis"
GHIDRA="/home/sshack/Code/nextthunk/ghidra"
JAVA_HOME="/usr/lib/jvm/java-25-openjdk-amd64"
export JAVA_HOME

mkdir -p "$OUTDIR"

echo "=== Step 1: Extract i386 ==="
python3 -c "
import struct
with open('$BIN', 'rb') as f:
    data = f.read()
magic = struct.unpack_from('>I', data, 0)[0]
if magic == 0xCAFEBABE:
    narchs = struct.unpack_from('>I', data, 4)[0]
    for i in range(narchs):
        off = 8 + i * 20
        cputype = struct.unpack_from('>I', data, off)[0]
        foff = struct.unpack_from('>I', data, off+8)[0]
        fsz = struct.unpack_from('>I', data, off+12)[0]
        if cputype == 7:
            with open('$I386', 'wb') as out: out.write(data[foff:foff+fsz])
            print(f'  Extracted i386: {fsz} bytes')
            import sys; sys.exit(0)
    import sys; sys.exit(1)
elif magic == 0xCEFAEDFE:
    import shutil; shutil.copy('$BIN', '$I386'); print('  Already i386')
else:
    import sys; sys.exit(1)
"

echo "=== Step 2: ObjC metadata + Ghidra function analysis ==="
python3 /home/sshack/Code/nextthunk/dump_objc_metadata.py "$I386" "$OUTDIR"

rm -rf /tmp/ghidra_projects/${NAME}_analysis.* 2>/dev/null
$GHIDRA/support/analyzeHeadless \
    /tmp/ghidra_projects "${NAME}_analysis" \
    -import "$I386" -overwrite \
    -scriptPath /home/sshack/Code/nextthunk/ghidra_scripts \
    -postScript DumpFunctions.java \
    2>&1 | grep "DumpFunctions.java> " | sed 's/.*DumpFunctions.java> //' > "$OUTDIR/functions.txt"

echo "=== Step 3: Merge ==="
python3 << PYEOF
import re

OUTDIR = "$OUTDIR"

# Read Ghidra functions
funcs = {}
with open(f"{OUTDIR}/functions.txt") as f:
    for line in f:
        line = line.strip()
        line = line.replace(" (GhidraScript)", "").strip()
        if "FUNCTIONS" in line or not line: continue
        m = re.match(r'0x([0-9a-fA-F]+)\s+(.*)', line)
        if m:
            funcs[int(m.group(1), 16)] = m.group(2)

# Read ObjC methods with metadata (IMP address + name)
methods = {}
with open(f"{OUTDIR}/objc_metadata.txt") as f:
    for line in f:
        line = line.strip()
        m = re.match(r'0x([0-9a-fA-F]+)\s+\[(.*)\]', line)
        if m:
            methods[int(m.group(1), 16)] = m.group(2)

# Determine binary code range from i386 binary
with open("$I386", "rb") as f:
    import struct
    data = f.read()
    ncmds = struct.unpack_from("<I", data, 16)[0]
    text_start, text_end = 0x2000, 0
    off = 28
    for i in range(ncmds):
        cmd = struct.unpack_from("<I", data, off)[0]
        if cmd == 1:
            segname = data[off+8:off+24].rstrip(b"\x00").decode("latin-1")
            vmaddr = struct.unpack_from("<I", data, off+24)[0]
            vmsize = struct.unpack_from("<I", data, off+28)[0]
            if segname == "__TEXT":
                text_start = vmaddr
                text_end = vmaddr + vmsize
        off += struct.unpack_from("<I", data, off+4)[0]

# Write merged output
with open(f"{OUTDIR}/annotated.txt", "w") as out:
    out.write(f"Binary: $NAME\n")
    out.write(f"__TEXT: 0x{text_start:x}-0x{text_end:x}\n")
    out.write(f"Ghidra functions: {len(funcs)}\n")
    out.write(f"ObjC methods: {len(methods)}\n\n")
    
    out.write("=== METHODS IMPLEMENTED IN THIS BINARY ===\n")
    impl_count = 0
    for addr in sorted(methods):
        if text_start <= addr < text_end:
            fname = funcs.get(addr, "")
            oname = methods[addr]
            if fname and fname != oname and not fname.startswith("FUN_"):
                out.write(f"0x{addr:06x} {fname}  // ObjC: [{oname}]\n")
            else:
                out.write(f"0x{addr:06x} [{oname}]\n")
            impl_count += 1
    
    out.write(f"\n=== METHODS REFERENCED (shared library stubs) ===\n")
    ref_count = 0
    for addr in sorted(methods):
        if not (text_start <= addr < text_end):
            oname = methods[addr]
            out.write(f"0x{addr:06x} [{oname}]\n")
            ref_count += 1
    
    out.write(f"\n  Implemented: {impl_count}, Referenced: {ref_count}")

import os
stats = f"Ghidra functions: {len(funcs)}\nObjC methods: {len(methods)}\nImplemented: {impl_count}\nReferenced: {ref_count}"
with open(f"{OUTDIR}/stats.txt", "w") as f:
    f.write(stats + "\n")
print(stats)
PYEOF
echo "Done. See $OUTDIR/annotated.txt"
