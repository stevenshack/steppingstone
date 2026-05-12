#!/usr/bin/env python3
"""Resolve PTR_s_* class/selector references in decompiled ObjC source.

PTR_s_ClassName_ADDR -> [ClassName class]
PTR_s_SelName_ADDR   -> @selector(SelName)

Parses __cls_refs and __message_refs from the Mach-O binary.
"""

import re, sys, os, struct


def parse_macho_refs(binary_path):
    with open(binary_path, 'rb') as f:
        data = f.read()
    magic = struct.unpack_from('<I', data, 0)[0]
    e = '<' if magic == 0xFEEDFACE else '>'
    if magic not in (0xFEEDFACE, 0xCEFAEDFE):
        magic = struct.unpack_from('>I', data, 0)[0]
        e = '>'

    ncmds = struct.unpack_from(f'{e}I', data, 16)[0]
    off = 28
    secs = {}
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
                secs[sname] = (saddr, ssize, sfoff)
                so += 68
        off += cmdsize

    class_names = {}
    if '__class_names' in secs:
        cna, cns, cnf = secs['__class_names']
        pos = cnf
        end = cnf + cns
        while pos < end:
            null = data.index(b'\x00', pos) if b'\x00' in data[pos:end] else end
            n = data[pos:null].decode('latin-1', errors='replace')
            if n:
                class_names[cna + (pos - cnf)] = n
            pos = null + 1

    selectors = {}
    if '__meth_var_names' in secs:
        sa, ss, sf = secs['__meth_var_names']
        pos = sf
        end = sf + ss
        while pos < end:
            null = data.index(b'\x00', pos) if b'\x00' in data[pos:end] else end
            n = data[pos:null].decode('latin-1', errors='replace')
            if n:
                selectors[sa + (pos - sf)] = n
            pos = null + 1

    cls_refs = {}
    if '__cls_refs' in secs:
        sa, ss, sf = secs['__cls_refs']
        for i in range(0, ss, 4):
            ptr = struct.unpack_from(f'{e}I', data, sf + i)[0]
            cls_refs[sa + i] = class_names.get(ptr, '?')

    msg_refs = {}
    if '__message_refs' in secs:
        sa, ss, sf = secs['__message_refs']
        for i in range(0, ss, 4):
            ptr = struct.unpack_from(f'{e}I', data, sf + i)[0]
            msg_refs[sa + i] = selectors.get(ptr, '?')

    return cls_refs, msg_refs


def resolve_source(source_path, binary_path, output_path=None):
    cls_refs, msg_refs = parse_macho_refs(binary_path)

    with open(source_path) as f:
        text = f.read()
    original = text

    # Classify all PTR_s_* symbols
    class_syms = {}
    sel_syms = {}
    for m in re.finditer(r'(PTR_s_\w+?)_(0*[0-9a-fA-F]+)\b', text):
        full = m.group(0)
        addr = int(m.group(2), 16)
        if addr in cls_refs:
            class_syms[full] = cls_refs[addr]
        elif addr in msg_refs:
            sel_syms[full] = msg_refs[addr]

    # Replace each class ref: extern Class PTR_s_Foo_ADDR; -> [Foo class]
    for sym, class_name in class_syms.items():
        # extern Class declarations -> comment
        text = re.sub(
            rf'(extern\s+Class\s+)?{re.escape(sym)}\s*;',
            lambda m: f'[{class_name} class];' if not m.group(1) else f'// {class_name} class ref',
            text
        )
        # inline usages -> [ClassName class]
        text = re.sub(
            rf'(?<!\w){re.escape(sym)}(?!\w)',
            f'[{class_name} class]',
            text
        )

    # Replace each selector ref: extern Class PTR_s_sel_ADDR; -> @selector(sel)
    for sym, sel_name in sel_syms.items():
        text = re.sub(
            rf'(extern\s+Class\s+)?{re.escape(sym)}\s*;',
            lambda m: f'@selector({sel_name});' if not m.group(1) else f'// @selector({sel_name})',
            text
        )
        text = re.sub(
            rf'(?<!\w){re.escape(sym)}(?!\w)',
            f'@selector({sel_name})',
            text
        )

    # Remove the "External ObjC class references" header if all refs were resolved
    if class_syms or sel_syms:
        text = re.sub(r'\n// External ObjC class references \(define in stubs\)\n', '\n', text)

    diffs = sum(1 for a, b in zip(original.split('\n'), text.split('\n')) if a != b)
    out_path = output_path or source_path
    with open(out_path, 'w') as f:
        f.write(text)
    print(f"  {os.path.basename(out_path)}: {len(class_syms)} classes, {len(sel_syms)} selectors ({diffs} lines)")


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: resolve_class_refs.py <source.m> <binary> [output.m]")
        sys.exit(1)
    resolve_source(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
