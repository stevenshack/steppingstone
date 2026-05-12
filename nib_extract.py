#!/usr/bin/env python3
"""NibExtract - robust extraction of ALL data from NeXTSTEP nib files.
Uses direct byte searching for arrays + regex-based extraction.
"""

import struct, sys, json, re

def find_typedstream_arrays(data):
    """Find all [Nc] array declarations in typedstream data."""
    arrays = []
    i = 0
    while i < len(data):
        if data[i] == 0x84 and i+2 < len(data) and data[i+1] in (0x05, 0x06, 0x07):
            tag = data[i+1]
            start = i + 2
            end = data.find(b']', start, start + 32)
            if end > start and data[start] == ord('['):
                decl = data[start:end+1].decode('latin-1', errors='replace')
                try:
                    size = int(decl[1:-2])
                except: size = 0
                raw_start = end + 1
                raw_end = raw_start + size
                raw = data[raw_start:raw_end] if raw_end <= len(data) else data[raw_start:]
                arrays.append({
                    'offset': i, 'tag': tag, 'decl': decl, 'size': size, 'raw': raw,
                })
                i = raw_end
                continue
        i += 1
    return arrays

def extract_all_strings(data):
    """Extract all printable strings (>=3 chars) from data."""
    strings = set()
    for m in re.finditer(b'[A-Za-z_][A-Za-z0-9_]{2,60}', data):
        try: strings.add(m.group().decode('ascii'))
        except: pass
    for m in re.finditer(b'[ -~]{4,60}', data):
        try: s = m.group().decode('ascii').strip()
        except: continue
        if len(s) >= 3:
            strings.add(s)
    return strings

def extract_typedstream_atoms(data):
    """Extract classes, selectors, strings, floats, and shorts from typedstream."""
    atoms = {
        'classes': set(),
        'selectors': set(),
        'strings': set(),
        'floats': [],
        'shorts': [],
        'refs': [],
        'arrays': [],
    }
    
    def ri(d, p):
        if p[0] >= len(d): return 0
        b = d[p[0]]; p[0] += 1
        if b == 0x81:
            if p[0] >= len(d): return 0
            v = d[p[0]]; p[0] += 1; return v
        elif b == 0x82:
            if p[0]+1 >= len(d): return 0
            v = struct.unpack_from('>h', d, p[0])[0]; p[0] += 2; return v
        elif b == 0x83:
            if p[0]+3 >= len(d): return 0
            v = struct.unpack_from('>i', d, p[0])[0]; p[0] += 4; return v
        elif 0x01 <= b <= 0x7f: return b
        elif 0x84 <= b <= 0x87: return b - 256
        elif b == 0x88: return 0
        else: return b
    
    def rs(d, p):
        l = ri(d, p)
        if l <= 0 or p[0]+l > len(d): return None
        s = d[p[0]:p[0]+l].decode('latin-1', errors='replace')
        p[0] += l; return s
    
    def scan(d, p):
        """Recursive typedstream scanner."""
        # Skip any typedstream headers
        while p[0] + 13 <= len(d):
            if d[p[0]:p[0]+2] == b'\x04\x0b' and d[p[0]+2:p[0]+13] == b'typedstream':
                p[0] += 13
                while p[0] < len(d) and d[p[0]] in (0x81, 0xa2, 0x84):
                    if d[p[0]] == 0x81: p[0] += 2
                    elif d[p[0]] == 0xa2: p[0] += 1
                    elif d[p[0]] == 0x84: 
                        if p[0]+1 < len(d) and d[p[0]+1] == 0x01: p[0] += 3
                        elif p[0]+1 < len(d) and d[p[0]+1] == 0x40: p[0] += 2
                        else: break
            else: break
        
        while p[0] < len(d):
            b = d[p[0]]; p[0] += 1
            
            if 0x01 <= b <= 0x7f:
                pass
            elif b in (0x7d, 0x7e, 0x7f, 0x00):
                pass
            elif b == 0x81:
                if p[0] < len(d): ri(d, p)  # use proper ri to handle multi-byte
            elif b == 0x82:
                v = struct.unpack_from('>h', d, p[0])[0] if p[0]+1 < len(d) else 0
                atoms['shorts'].append(v); p[0] += 2
            elif b == 0x83:
                p[0] += 4
            elif b == 0x84:
                if p[0] >= len(d): break
                t = d[p[0]]; p[0] += 1
                if t == 0x01: ri(d, p)
                elif t in (0x05, 0x06, 0x07):
                    end_br = d.find(b']', p[0], p[0]+32)
                    if end_br > p[0] and d[p[0]] == ord('['):
                        decl = d[p[0]:end_br+1].decode('latin-1')
                        p[0] = end_br + 1
                        try: sz = int(decl[1:-2])
                        except: sz = 0
                        raw = d[p[0]:p[0]+sz] if p[0]+sz <= len(d) else d[p[0]:]
                        atoms['arrays'].append({'decl':decl,'size':sz,'raw':raw})
                        if len(raw) >= 13 and raw[:2]==b'\x04\x0b' and raw[2:13]==b'typedstream':
                            scan(raw, [0])
                        p[0] += sz
                elif t == 0x25: rs(d, p)
                elif t == 0x40: pass
                elif t == 0x84: pass  # class_def_old marker
                elif t == 0x85: ri(d, p)
                elif t == 0x86: rs(d, p); ri(d, p)
                elif t == 0x0b:  # This shouldn't happen but handle gracefully
                    pass
                else: ri(d, p)
            elif b == 0x85: ri(d, p)
            elif b == 0x86: rs(d, p); ri(d, p)
            elif b in (0x88, 0x9c, 0x9d): pass
            elif b == 0x8c: rs(d, p)
            elif b == 0x92: ri(d, p)
            elif b == 0x93: ri(d, p)
            elif b == 0x94:
                # Read class name with tagged-length format
                if p[0] >= len(d): break
                l_or_tag = d[p[0]]
                name = None
                if l_or_tag == 0x84:
                    p[0] += 1
                    l = d[p[0]] if p[0] < len(d) else 0; p[0] += 1
                    if l > 0 and p[0]+l <= len(d):
                        name = d[p[0]:p[0]+l].decode('latin-1', errors='replace')
                        p[0] += l
                elif 0x01 <= l_or_tag <= 0x7f:
                    l = d[p[0]]; p[0] += 1
                    if l > 0 and p[0]+l <= len(d):
                        name = d[p[0]:p[0]+l].decode('latin-1', errors='replace')
                        p[0] += l
                else:
                    name = rs(d, p)
                ver = ri(d, p)
                if name: atoms['classes'].add(name)
            elif b == 0x95:
                if p[0] < len(d): p[0] += 1  # skip ref
            elif b == 0x96:
                if p[0] < len(d): p[0] += 1
            elif b == 0x97:
                if p[0] >= len(d): break
                t = d[p[0]]; p[0] += 1
                if t == 0x05:
                    if p[0]+4 <= len(d):
                        atoms['floats'].append(struct.unpack_from('>f', d, p[0])[0])
                    p[0] += 4
                elif t == 0x06:
                    if p[0]+8 <= len(d):
                        atoms['floats'].append(struct.unpack_from('>d', d, p[0])[0])
                    p[0] += 8
                elif t == 0x0c:
                    s = rs(d, p)
                    if s: atoms['classes'].add(s)
                elif t == 0x0e:
                    s = rs(d, p)
                    if s: atoms['selectors'].add(s)
                elif t == 0x16: ri(d, p)
                elif t in (0x81,): ri(d, p)
                elif t in (0x82,):
                    if p[0]+2 <= len(d):
                        atoms['shorts'].append(struct.unpack_from('>h',d,p[0])[0])
                    p[0] += 2
                elif t in (0x83,): p[0] += 4
            elif b in (0x98, 0x99): pass
            elif b == 0xa2:
                if p[0] < len(d): p[0] += 1
            elif b in (0xa8, 0xac): ri(d, p)
    
    scan(data, [0])
    return atoms


def decode_raw_nib_struct(raw, known_strings):
    """Extract UI data from raw nib struct bytes.
    NeXTSTEP nibs encode window/control frames as 16-bit big-endian shorts.
    """
    result = {
        'window_frames': [],
        'control_frames': [],
        'strings': set(),
        'shorts': [],
    }
    
    # Extract strings
    result['strings'] = extract_all_strings(raw)
    
    # Extract shorts (potential coordinates)
    i = 0
    while i + 2 <= len(raw):
        v = struct.unpack_from('>h', raw, i)[0]
        # Valid NeXTSTEP screen coordinates: typically 0-1200
        result['shorts'].append((i, v))
        i += 2
    
    return result


def analyze_nib(path):
    with open(path, 'rb') as f:
        data = f.read()
    
    result = {
        'path': path,
        'size': len(data),
    }
    
    # Extract atoms from entire nib
    atoms = extract_typedstream_atoms(data)
    result['atoms'] = {
        'classes': sorted(atoms['classes']),
        'selectors': sorted(atoms['selectors']),
        'floats': atoms['floats'],
        'shorts': atoms['shorts'][:50],
    }
    
    # Process arrays
    result['arrays'] = []
    for a in atoms['arrays']:
        arr_info = {
            'decl': a['decl'],
            'size': a['size'],
        }
        raw = a['raw']
        
        if len(raw) >= 13 and raw[:2]==b'\x04\x0b' and raw[2:13]==b'typedstream':
            # Nested typedstream - extract its atoms
            nested = extract_typedstream_atoms(raw)
            arr_info['nested_classes'] = sorted(nested['classes'])
            arr_info['nested_selectors'] = sorted(nested['selectors'])
            arr_info['nested_floats'] = nested['floats'][:20]
            arr_info['nested_shorts'] = nested['shorts'][:50]
            
            # Also extract raw struct data (after typedstream header)
            # Find where typedstream data ends
            pos = 0
            while pos + 13 <= len(raw):
                if raw[pos:pos+2]==b'\x04\x0b' and raw[pos+2:pos+13]==b'typedstream':
                    pos += 13
                    while pos < len(raw) and raw[pos] in (0x81, 0xa2, 0x84):
                        if raw[pos] == 0x81: pos += 2
                        elif raw[pos] == 0xa2: pos += 1
                        elif raw[pos] == 0x84:
                            if pos+1 < len(raw) and raw[pos+1] == 0x01: pos += 3
                            elif pos+1 < len(raw) and raw[pos+1] == 0x40: pos += 2
                            else: break
                else: break
            
            if pos < len(raw):
                struct_data = raw[pos:]
                arr_info['struct_data_hex'] = struct_data[:128].hex()
                # Extract coordinates from struct data
                coords = []
                i = 0
                while i + 4 <= len(struct_data):
                    x = struct.unpack_from('>h', struct_data, i)[0]
                    y = struct.unpack_from('>h', struct_data, i+2)[0]
                    if (0 <= x <= 1200) and (0 <= y <= 1200):
                        coords.append((x, y))
                    i += 2
                # Find window-like rects: 4 consecutive shorts that make sense
                all_shorts = []
                i = 0
                while i + 2 <= len(struct_data):
                    all_shorts.append(struct.unpack_from('>h', struct_data, i)[0])
                    i += 2
                # Look for 4-tuples that look like rects (x, y, w, h)
                rects = []
                for i in range(len(all_shorts) - 3):
                    x, y, w, h = all_shorts[i:i+4]
                    if (0 <= x <= 1200 and 0 <= y <= 1200 and
                        10 <= w <= 800 and 10 <= h <= 600):
                        rects.append({'x': x, 'y': y, 'w': w, 'h': h, 'idx': i})
                arr_info['struct_rects'] = rects[:10]
        else:
            arr_info['hex'] = raw[:64].hex()
        
        result['arrays'].append(arr_info)
    
    return result


def print_report(result):
    print(f"=== {result['path']} ({result['size']} bytes) ===")
    
    a = result['atoms']
    print(f"\nClasses: {len(a['classes'])}")
    for c in a['classes']:
        print(f"  {c}")
    
    print(f"\nSelectors: {len(a['selectors'])}")
    for s in a['selectors']:
        print(f"  {s}")
    
    print(f"\nFloats ({len(a['floats'])}): {a['floats'][:20]}")
    
    for i, arr in enumerate(result['arrays']):
        print(f"\nArray {i}: {arr['decl']} ({arr['size']}B)")
        if 'nested_classes' in arr:
            nc = arr['nested_classes']
            ns = arr['nested_selectors']
            print(f"  Classes: {nc}")
            print(f"  Selectors: {ns}")
            print(f"  Floats: {arr['nested_floats'][:30]}")
            if arr.get('struct_rects'):
                print(f"  Window/Control rects (from struct data):")
                for r in arr['struct_rects']:
                    print(f"    x={r['x']} y={r['y']} w={r['w']} h={r['h']} (idx={r['idx']})")


if __name__ == "__main__":
    import sys
    
    for path in ['EnvelopeMaker.nib', 'Info.nib']:
        r = analyze_nib(path)
        print_report(r)
        print()
        with open(path + '.analysis.json', 'w') as f:
            json.dump(r, f, indent=2, default=str, ensure_ascii=False)
    
    # Output decoding hints
    print("\n" + "="*60)
    print("UI RECONSTRUCTION GUIDE")
    print("="*60)
    print("""
The nib files contain:
1. [20c] array: small HashTable with object metadata
2. [908c] array: main objects (HeaderClass, Application, outlets, actions)
3. [2517c] array: UI objects (MenuTemplate, WindowTemplate, buttons, text fields)

For EnvelopeMaker.nib:
- Window: titled "Envelope Editor" with frame from struct rects
- Fields: fromField1-4, toField1-5 (text fields for address info)
- Buttons: Set (sends printEnvelope:), Print, Hide, Quit
- Menu: Standard App/Edit/Window menus
- Custom view: EnvelopeView (the envelope display area)

For Info.nib:
- Window panel: titled "Envelope Maker" about box
- Fields: VersionNumber, Field, Field1, Field2, Button1
- Labels: "Version 1.00 (prototype)", "by Steven H. Schmidt", 
           "Copyright 1992,  ScHmIdT House Software"
- Image: envelope (NXImage)
""")
