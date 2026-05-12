#!/bin/bash
# Extract i386 slice from a NeXTSTEP universal Mach-O binary
# Usage: ./extract_i386.sh <path-to-universal-binary>

set -e
BIN="$1"
if [ -z "$BIN" ] || [ ! -f "$BIN" ]; then
    echo "Usage: $0 <path-to-universal-binary>"
    exit 1
fi

DIR=$(dirname "$BIN")
NAME=$(basename "$BIN")
OUT="${DIR}/${NAME}.i386"

python3 -c "
import struct, sys
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
        if cputype == 7:  # i386
            with open('$OUT', 'wb') as out:
                out.write(data[foff:foff+fsz])
            print(f'Extracted i386 slice: {fsz} bytes')
            sys.exit(0)
    print('No i386 slice found')
    sys.exit(1)
elif magic == 0xCEFAEDFE:
    print('Already i386')
    sys.exit(0)
else:
    print(f'Unknown magic: 0x{magic:08x}')
    sys.exit(1)
"
