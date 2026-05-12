#!/usr/bin/env python3
"""Extract UI layout from NeXTSTEP nib by parsing nested typedstreams."""
import struct, sys, json

def parse_ts(data, name="stream", top_level=True):
    atoms = []
    pos = [0]
    depth = [0]  # object nesting depth
    
    def ri():
        b = data[pos[0]]; pos[0] += 1
        if b == 0x81: v = data[pos[0]]; pos[0] += 1; return v
        elif b == 0x82: v = struct.unpack_from('>h', data, pos[0])[0]; pos[0] += 2; return v
        elif b == 0x83: v = struct.unpack_from('>i', data, pos[0])[0]; pos[0] += 4; return v
        elif b == 0x88: return 0
        elif 0x01 <= b <= 0x7f: return b
        elif 0x84 <= b <= 0x87: return b - 256
        return b
    
    def rs():
        l = ri()
        if l <= 0: return None
        s = data[pos[0]:pos[0]+l].decode('latin-1', errors='replace')
        pos[0] += l; return s
    
    def add(t, v=None):
        atoms.append({'t': t, 'v': v, 'd': depth[0]})
    
    def push():
        depth[0] += 1
    
    def pop():
        depth[0] -= 1
    
    # Skip header
    while pos[0] < len(data):
        if data[pos[0]:pos[0]+2] == b'\x04\x0b':
            pos[0] += 2
            if data[pos[0]:pos[0]+11] == b'typedstream':
                pos[0] += 11
            if pos[0] < len(data) and data[pos[0]] == 0x81:
                pos[0] += 2
            if pos[0] < len(data) and data[pos[0]] == 0xa2:
                pos[0] += 1
            continue
        break
    
    while pos[0] < len(data):
        b = data[pos[0]]; pos[0] += 1
        prev_b = data[pos[0]-2] if pos[0] >= 2 else 0  # Previous byte
        
        if 0x01 <= b <= 0x20:
            if prev_b == 0x84:
                # 84 84 <len> <name> pattern: this is a class definition
                cls_name = data[pos[0]:pos[0]+b].decode('latin-1', errors='replace')
                pos[0] += b
                ver = ri()
                add('class_def', (cls_name, ver))
            else:
                add('int', b)
        elif 0x21 <= b <= 0x7c: pass  # char data, skip
        elif b == 0x81: add('int', data[pos[0]]); pos[0] += 1
        elif b == 0x82: add('short', struct.unpack_from('>h', data, pos[0])[0]); pos[0] += 2
        elif b == 0x83: add('int32', struct.unpack_from('>i', data, pos[0])[0]); pos[0] += 4
        elif b == 0x84:
            t = data[pos[0]]; pos[0] += 1
            if t == 0x01: add('int', ri())
            elif t == 0x05:  # array [Ntype]
                end = data[pos[0]:].find(b']')
                if end >= 0:
                    decl = data[pos[0]:pos[0]+end+1].decode('latin-1')
                    pos[0] += end + 1
                    sz = int(decl[1:-2])
                    raw = data[pos[0]:pos[0]+sz]
                    pos[0] += sz
                    arr_info = {'decl': decl, 'size': sz}
                    if raw[:2] == b'\x04\x0b':
                        nested = parse_ts(raw, f"{name}_nest")
                        arr_info['nested_ts'] = nested
                    add('array', arr_info)
            elif t == 0x06:  # array with 4-byte length
                sz = struct.unpack_from('>I', data, pos[0])[0]; pos[0] += 4
                end = data[pos[0]:].find(b']')
                if end >= 0:
                    decl = data[pos[0]:pos[0]+end+1].decode('latin-1')
                    pos[0] += end + 1
                    add('array_decl', decl)
            elif t == 0x25: add('string', rs())
            elif t == 0x40: add('obj_start'); push()
            elif t == 0x84: pass  # continuation
            elif t == 0x85: add('ref', ri())
            else: add(f't{t:02x}', ri())
        elif b == 0x7d or b == 0x7e or b == 0x7f or b == 0x86: pass
        elif b == 0x85: add('ref', ri())
        elif b == 0x86: add('ref_cls', (rs(), ri()))
        elif b == 0x88: add('nil')
        elif b == 0x8c: add('arr_type', rs())
        elif b == 0x92: add('ref', ri())
        elif b == 0x93: add('cont', ri())
        elif b == 0x94: add('class_def', (rs(), ri()))
        elif b == 0x95: add('obj_ref', ri()); push()
        elif b == 0x96: add('obj_ref', ri())
        elif b == 0x97:
            t = data[pos[0]]; pos[0] += 1
            if t == 0x01: add('nil')
            elif t == 0x02: add('bool', True)
            elif t == 0x03: add('bool', False)
            elif t == 0x04: add('nil')
            elif t == 0x05: add('float', struct.unpack_from('>f', data, pos[0])[0]); pos[0] += 4
            elif t == 0x06: add('double', struct.unpack_from('>d', data, pos[0])[0]); pos[0] += 8
            elif t == 0x0c: add('cls_name', rs())
            elif t == 0x0e: add('sel', rs())
            elif t == 0x14: pass
            elif t == 0x16: add('int', ri())
            else: add(f'97_{t:02x}', hex(t))
        elif b == 0x98: add('end'); pop()
        elif b == 0x99: add('end'); pop()
        elif b in (0x9c, 0x9d): add('nil')
        elif b == 0xa2: add('ref', ri())
        elif b == 0xa8: add('int', ri())
        elif b == 0xac: add('int', ri())
        elif b == 0x7d: pass
    
    return atoms

def extract_layout(nib_path):
    with open(nib_path, 'rb') as f:
        data = f.read()
    
    atoms = parse_ts(data)
    
    def scan(atom_list, result):
        for a in atom_list:
            if a['t'] == 'cls_name' and a['v']:
                result['classes'].add(a['v'])
            elif a['t'] == 'sel' and a['v']:
                result['selectors'].add(a['v'])
            elif a['t'] == 'string' and a['v']:
                result['strings'].add(a['v'])
            elif a['t'] == 'float':
                result['floats'].append(a['v'])
            elif a['t'] == 'short':
                result['shorts'].append(a['v'])
            elif a['t'] == 'class_def' and a['v'] and a['v'][0]:
                result['classes'].add(a['v'][0])
            elif a['t'] == 'array':
                nested = a['v'].get('nested_ts')
                if nested:
                    scan(nested, result)
    
    result = {'classes': set(), 'selectors': set(), 'strings': set(),
              'floats': [], 'shorts': []}
    scan(atoms, result)
    
    return {
        'classes': sorted(result['classes']),
        'selectors': sorted(result['selectors']),
        'strings': sorted(result['strings']),
        'floats': result['floats'],
        'shorts': result['shorts'],
        'atoms': atoms,
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: extract_nib.py <nibfile>")
        sys.exit(1)
    
    layout = extract_layout(sys.argv[1])
    for cls in layout.get('classes', []):
        print(f"Class: {cls}")
    for sel in layout.get('selectors', []):
        print(f"  Sel: {sel}")
    if layout.get('floats'):
        print(f"  Floats: {layout['floats'][:10]}")
    if layout.get('shorts'):
        print(f"  Shorts: {layout['shorts'][:20]}")
    print(f"Atoms: {len(layout.get('atoms', []))}")
