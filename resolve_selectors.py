#!/usr/bin/env python3
"""Resolve func_0x... and PTR_s_... names in Ghidra decompiler output to ObjC selectors."""

import re
import struct
import sys


def parse_macho_selectors(path):
    """Parse selector strings and message_refs from NeXTSTEP Mach-O __OBJC segment."""
    with open(path, 'rb') as f:
        data = f.read()

    magic = struct.unpack_from('<I', data, 0)[0]
    if magic == 0xFEEDFACE:   # MH_MAGIC in LE → native LE (i386)
        endian = '<'
    elif magic == 0xCEFAEDFE:  # MH_CIGAM in LE → native BE (m68k)
        endian = '>'
    else:
        print(f"Unknown Mach-O magic: 0x{magic:08x}", file=sys.stderr)
        return {}, {}

    ncmds = struct.unpack_from(f'{endian}I', data, 16)[0]

    selectors = {}       # selector string address -> selector name
    msg_refs = {}        # message_ref address -> selector name
    sections = []        # (segname, sectname, addr, size, sect_off)

    off = 28
    for _ in range(ncmds):
        cmd = struct.unpack_from(f'{endian}I', data, off)[0]
        cmdsize = struct.unpack_from(f'{endian}I', data, off+4)[0]
        if cmd == 1:  # LC_SEGMENT
            segname = data[off+8:off+24].rstrip(b'\x00').decode('ascii', errors='replace')
            nsections = struct.unpack_from(f'{endian}I', data, off+48)[0]
            s_off = off + 56
            for _ in range(nsections):
                sectname = data[s_off:s_off+16].rstrip(b'\x00').decode('ascii', errors='replace')
                addr = struct.unpack_from(f'{endian}I', data, s_off+32)[0]
                size = struct.unpack_from(f'{endian}I', data, s_off+36)[0]
                sect_off_val = struct.unpack_from(f'{endian}I', data, s_off+40)[0]
                sections.append((segname, sectname, addr, size, sect_off_val))
                s_off += 68
        off += cmdsize

    # First pass: collect all selector strings
    for segname, sectname, addr, size, sect_off in sections:
        if sectname in ('__selector_strs', '__meth_var_names'):
            pos = sect_off
            end = pos + size
            while pos < end:
                null = data.index(b'\x00', pos)
                sel = data[pos:null].decode('ascii', errors='replace')
                selectors[addr + (pos - sect_off)] = sel
                pos = null + 1
                if pos >= end:
                    break

    # Second pass: resolve message refs using populated selectors
    for segname, sectname, addr, size, sect_off in sections:
        if sectname == '__message_refs':
            for i in range(0, size, 4):
                ptr_addr = addr + i
                target = struct.unpack_from(f'{endian}I', data, sect_off + i)[0]
                if target in selectors:
                    msg_refs[ptr_addr] = selectors[target]

    return selectors, msg_refs


def detect_msg_send_addr(text):
    """Auto-detect the objc_msgSend address from decompiled output."""
    counts = {}
    for m in re.finditer(r'\bfunc_0x([0-9a-fA-F]+)\b', text):
        addr = m.group(1).lower()
        counts[addr] = counts.get(addr, 0) + 1
    if not counts:
        return 0x05003477  # default i386
    # The most-called func_0x* is likely objc_msgSend
    best = max(counts, key=counts.get)
    return int(best, 16)


def resolve_decompiled(text, selectors, msg_refs, msg_send_addr=None):
    """Replace Ghidra-generated names with ObjC selectors."""
    if msg_send_addr is None:
        msg_send_addr = detect_msg_send_addr(text)

    msg_send_hex = format(msg_send_addr, '08x')
    msg_send_hex_upper = format(msg_send_addr, '08X')
    msg_send_short = format(msg_send_addr, 'x')

    # Pre-process: replace funcptr_t calls spanning lines
    # Text: (*(funcptr_t *)0xADDR)(...  or  (*(funcptr_t *)0xADDR)\n(...)
    # Pattern structure: \( \* \(funcptr_t\s*\*\) 0xADDR \) \s* \(
    for variant in [msg_send_hex, msg_send_short]:
        text = re.sub(
            rf'\(\s*\*\s*\(funcptr_t\s*\*\)&?SUB_{variant}\)\s*\(',
            'objc_msgSend(', text
        )
        text = re.sub(
            rf'\(\s*\*\s*\(funcptr_t\s*\*\)0x' + variant + r'\)\s*\(',
            'objc_msgSend(', text
        )

    lines = text.split('\n')
    result = []

    for line in lines:
        # Don't modify extern declaration lines (keeps symbol names as-is)
        if line.strip().startswith('extern'):
            result.append(line)
            continue

        # Replace func_0x<addr> with objc_msgSend
        line = re.sub(r'\bfunc_0x' + msg_send_hex + r'\b', 'objc_msgSend', line)
        line = re.sub(r'\bfunc_0x' + msg_send_hex_upper + r'\b', 'objc_msgSend', line)

        # Replace PTR_s_<name>_<hexaddr> with @selector(name) using msg_refs only
        def replace_ptr(m):
            full = m.group(0)
            if '_' not in full:
                return full
            parts = full.split('_')
            hex_candidate = parts[-1]
            hex_part = re.sub(r'[^0-9a-fA-F].*$', '', hex_candidate)
            if not hex_part:
                return full
            try:
                addr = int(hex_part, 16)
                if addr in msg_refs:
                    return f'@selector({msg_refs[addr]})'
            except ValueError:
                pass
            return full

        line = re.sub(r'PTR_s_[A-Za-z0-9_]+', replace_ptr, line)

        result.append(line)

    return '\n'.join(result)


def main():
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <i386-binary> <decompiled-text>", file=sys.stderr)
        sys.exit(1)

    binary_path = sys.argv[1]
    selectors, msg_refs = parse_macho_selectors(binary_path)
    print(f"// Selectors: {len(selectors)}, msg_refs: {len(msg_refs)}", file=sys.stderr)

    if sys.argv[2] == '-':
        text = sys.stdin.read()
    else:
        with open(sys.argv[2]) as f:
            text = f.read()

    resolved = resolve_decompiled(text, selectors, msg_refs)
    print(resolved)


if __name__ == '__main__':
    main()
