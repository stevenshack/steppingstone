#!/usr/bin/env python3
"""Extract the app icon from a NeXTSTEP Mach-O's __TEXT/app section.
The app section contains a TIFF image used as the application icon.
Outputs to analysis/ and the ported app's Resources directory."""

import struct, sys, os

def extract(path, outdir=None):
    with open(path, 'rb') as f:
        data = f.read()

    magic = struct.unpack_from('<I', data, 0)[0]
    if magic == 0xCEFAEDFE:
        e = '>'
    elif magic == 0xFEEDFACE:
        e = '<'
    else:
        magic = struct.unpack_from('>I', data, 0)[0]
        if magic != 0xFEEDFACE:
            print(f"  Not Mach-O: {path}", file=sys.stderr)
            return
        e = '>'

    ncmds = struct.unpack_from(f'{e}I', data, 16)[0]
    off = 28
    for _ in range(ncmds):
        cmd = struct.unpack_from(f'{e}I', data, off)[0]
        cmdsize = struct.unpack_from(f'{e}I', data, off+4)[0]
        if cmd == 1:
            nsects = struct.unpack_from(f'{e}I', data, off+48)[0]
            so = off + 56
            for _ in range(nsects):
                sname = data[so:so+16].rstrip(b'\x00').decode('latin-1')
                saddr = struct.unpack_from(f'{e}I', data, so+32)[0]
                ssize = struct.unpack_from(f'{e}I', data, so+36)[0]
                sfoff = struct.unpack_from(f'{e}I', data, so+40)[0]
                if sname == 'app' and ssize > 0:
                    icon_data = data[sfoff:sfoff+ssize]
                    # Verify it looks like a TIFF
                    if icon_data[:2] == b'MM':
                        app_name = os.path.basename(path)
                        if app_name.endswith('.i386'):
                            app_name = app_name.replace('.i386', '')
                        tiff_name = app_name + '.tiff'

                        if outdir:
                            # Write to analysis directory
                            os.makedirs(outdir, exist_ok=True)
                            out_path = os.path.join(outdir, tiff_name)
                            with open(out_path, 'wb') as f:
                                f.write(icon_data)

                            # Also write to ported app Resources if it exists
                            parent = os.path.dirname(outdir)
                            ported_res = os.path.join(parent, 'ported', f'{app_name}.app', 'Resources')
                            if os.path.isdir(ported_res):
                                res_path = os.path.join(ported_res, tiff_name)
                                with open(res_path, 'wb') as f:
                                    f.write(icon_data)
                                print(f"  Icon -> {res_path}")

                            print(f"  Icon -> {out_path} ({ssize} bytes)")
                        else:
                            out_path = os.path.join(os.path.dirname(path), tiff_name)
                            with open(out_path, 'wb') as f:
                                f.write(icon_data)
                            print(f"  Icon -> {out_path} ({ssize} bytes)")
                    else:
                        print(f"  app section exists but is not a TIFF ({ssize} bytes)")
                so += 68
        off += cmdsize


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: extract_app_icon.py <binary> [analysis_dir]")
        sys.exit(1)
    extract(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
