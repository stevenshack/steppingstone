#!/usr/bin/env python3
"""nib_dump.py - COMPLETE NeXTSTEP nib extractor.
Extracts EVERYTHING from .nib files: all 94-objects, strings, selectors, floats.

Usage:  python3 nib_dump.py [nibfile.nib ...]
Output: JSON with complete extracted data including flat atom scan.
"""

import struct, sys, json, os, re

def find_arrays(data):
    arrays = []
    i = 0
    while i < len(data):
        if data[i]==0x84 and i+2<len(data) and data[i+1] in (0x05,0x06,0x07):
            s = i+2
            e = data.find(b']', s, s+32)
            if e > s and data[s]==ord('['):
                decl = data[s:e+1].decode('latin-1',errors='replace')
                try: sz = int(decl[1:-2])
                except: sz = 0
                raw = data[e+1:e+1+sz] if e+1+sz <= len(data) else data[e+1:]
                arrays.append({'decl': decl, 'size': sz, 'raw': raw})
                i = e+1+sz; continue
        i += 1
    return arrays

class R:
    __slots__ = ('d','o')
    def __init__(self, d, o=0):
        self.d = d; self.o = o
    def adv(self, n=1):
        self.o = min(self.o+n, len(self.d))
    def r1(self):
        if self.o >= len(self.d): return 0
        v = self.d[self.o]; self.o += 1; return v
    def rn(self, n):
        e = min(self.o+n, len(self.d))
        v = self.d[self.o:e]; self.o = e; return v
    def ri(self):
        if self.o >= len(self.d): return 0
        b = self.r1()
        if b == 0x81: v = self.r1(); return v if v < 128 else v-256
        if b == 0x82:
            v = struct.unpack_from('>h',self.d,self.o-2)[0] if self.o-1<len(self.d) else 0; return v
        if b == 0x83:
            v = struct.unpack_from('>i',self.d,self.o-4)[0] if self.o-3<len(self.d) else 0; return v
        if 0x01 <= b <= 0x7f: return b
        if 0x84 <= b <= 0x87: return b-256
        if b in (0xa8,0xac): return self.ri()
        if b == 0x88: return 0
        return b
    def ru(self):
        if self.o >= len(self.d): return 0
        b = self.r1()
        if b == 0x81: return self.r1()
        if b == 0x82:
            v = struct.unpack_from('>H',self.d,self.o-2)[0]; return v
        if b == 0x83:
            v = struct.unpack_from('>I',self.d,self.o-4)[0]; return v
        if 0x01 <= b <= 0x7f: return b
        if b == 0x84:
            n = self.r1()
            return self.ri() if n == 0x01 else n
        return 0
    def rs(self):
        l = self.ru()
        if l <= 0 or self.o+l > len(self.d): return None
        s = self.rn(l).decode('latin-1',errors='replace')
        return s

TE2CLASS = {
    '@@@@s': 'NibData', '%ii': 'Storage', 'i%': 'List',
    '*@': 'CustomObject', '*@ss': 'Cell', '*@ssffi@': 'ButtonCell',
    '*@ss@': 'Control', 'ff': 'MenuTemplate',
    '%%%%i@@': 'HeaderClass', 's*': 'NXImage', '*fss': 'Font',
}

def scan_flat(raw):
    """FLAT scan: extract ALL strings, selectors, floats, shorts from raw data.
    Uses regex and byte-pattern matching - catches everything."""
    result = {
        'strings': set(),
        'selectors': set(),
        'floats': [],
        'shorts': [],
        'classes': set(),
    }
    # Strings from raw
    for m in re.finditer(b'[A-Za-z_][A-Za-z0-9_]{2,60}', raw):
        try: result['strings'].add(m.group().decode('ascii'))
        except: pass
    for m in re.finditer(b'[ -~]{3,}', raw):
        try:
            s = m.group().decode('ascii').strip()
            if len(s) >= 3: result['strings'].add(s)
        except: pass
    
    # Selectors from raw
    for m in re.finditer(b'[A-Za-z_][A-Za-z0-9_]+:', raw):
        try: result['selectors'].add(m.group().decode('ascii'))
        except: pass
    
    # Typedstream float/short/class extraction
    i = 0
    while i < len(raw) - 5:
        if raw[i] == 0x97:
            st = raw[i+1]
            if st == 0x05 and i+6 <= len(raw):
                v = struct.unpack_from('>f', raw, i+2)[0]
                result['floats'].append(v)
                i += 6; continue
            elif st == 0x06 and i+10 <= len(raw):
                v = struct.unpack_from('>d', raw, i+2)[0]
                result['floats'].append(v)
                i += 10; continue
            elif st == 0x0c:
                l = raw[i+2] if i+2 < len(raw) else 0
                if 0 < l < 60 and i+3+l <= len(raw):
                    result['strings'].add(raw[i+3:i+3+l].decode('latin-1', errors='replace'))
                i += 3; continue
            elif st == 0x0e:
                l = raw[i+2] if i+2 < len(raw) else 0
                if 0 < l < 60 and i+3+l <= len(raw):
                    result['selectors'].add(raw[i+3:i+3+l].decode('latin-1', errors='replace'))
                i += 3; continue
            elif st == 0x84:
                l = raw[i+2] if i+2 < len(raw) else 0
                if 0 < l < 60 and i+3+l <= len(raw):
                    result['strings'].add(raw[i+3:i+3+l].decode('latin-1', errors='replace'))
                i += 3; continue
        elif raw[i] == 0x82 and i+3 <= len(raw):
            result['shorts'].append(struct.unpack_from('>h', raw, i+1)[0])
            i += 3; continue
        elif raw[i] == 0x94:
            # Extract class name from 0x94
            te = None
            if i+2 < len(raw) and raw[i+1] == 0x84:
                l = raw[i+2]
                if i+3+l <= len(raw):
                    te = raw[i+3:i+3+l].decode('latin-1', errors='replace')
            if te: result['classes'].add(te)
        i += 1
    
    return result

def decode_94_objects(raw):
    """Decode 94-opcode objects from typedstream data."""
    r = R(raw)
    # Skip header
    if r.o+13 <= len(r.d) and r.d[r.o:r.o+2]==b'\x04\x0b' and r.d[r.o+2:r.o+13]==b'typedstream':
        r.adv(13)
        while r.o < len(r.d) and r.d[r.o] in (0x81,0xa2):
            if r.d[r.o]==0x81: r.adv(2)
            elif r.d[r.o]==0xa2: r.adv(1)
            else: break
    
    objects = []
    all_strings = set()
    all_selectors = set()
    all_floats = []
    
    def read_val():
        nonlocal all_strings, all_selectors, all_floats
        if r.o >= len(r.d): return None
        b = r.r1()
        if 0x01 <= b <= 0x7f: return ('i', b)
        if b in (0x7d,0x7e,0x7f): return read_val()
        if b == 0x81:
            v = r.r1(); v = v if v<128 else v-256; return ('i', v)
        if b == 0x82:
            v = struct.unpack_from('>h',r.d,r.o-2)[0]; return ('s', v)
        if b == 0x83:
            v = struct.unpack_from('>i',r.d,r.o-4)[0]; return ('i4', v)
        if b in (0x85,0x92,0x96,0xa2): return ('r', r.ri())
        if b in (0x88,0x9c,0x9d): return ('n', None)
        if b == 0x86:
            cls = r.rs(); return ('rc', (cls, r.ri()))
        if b == 0x8c: r.rs(); return ('at', None)
        if b == 0x93: return ('ct', r.ri())
        if b == 0x97:
            t = r.r1()
            if t in (0x01,0x04): return ('n', None)
            if t == 0x02: return ('b', True)
            if t == 0x03: return ('b', False)
            if t == 0x05:
                v = struct.unpack_from('>f',r.d,r.o-4)[0] if r.o-3<len(r.d) else 0
                all_floats.append(v); return ('f', v)
            if t == 0x06:
                v = struct.unpack_from('>d',r.d,r.o-8)[0]; return ('d', v)
            if t == 0x0c:
                s = r.rs(); all_strings.add(s) if s else None; return ('cn', s)
            if t == 0x0e:
                s = r.rs(); all_selectors.add(s) if s else None; return ('sl', s)
            if t == 0x84:
                s = r.rs(); all_strings.add(s) if s else None; return ('s', s)
            if t in (0x16,0x81): return ('i', r.ri())
            if t == 0x82:
                v = struct.unpack_from('>h',r.d,r.o-2)[0]; return ('s', v)
            if t == 0x83:
                v = struct.unpack_from('>i',r.d,r.o-4)[0]; return ('i4', v)
            return ('x', t)
        if b in (0x98,0x99): return ('end', None)
        if b in (0xa8,0xac): return ('i', r.ri())
        if b == 0x00: return ('i', 0)
        
        # 0x84 tagged
        if b == 0x84:
            tag = r.r1()
            if tag == 0x01: return ('i', r.ri())
            if tag in (0x05,0x06,0x07):
                start = r.o
                end = r.d.find(b']', start, start+32)
                if end > start and r.d[start]==ord('['):
                    r.adv(end-start+1)
                    sz = int(r.d[start:end].decode()[1:-2])
                    r.adv(sz)
                return ('arr', None)
            if tag == 0x25:
                s = r.rs(); all_strings.add(s) if s else None; return ('s', s)
            if tag == 0x40:
                d = 1
                while d > 0 and r.o < len(r.d):
                    b2 = r.r1()
                    if b2 in (0x98,0x99): d -= 1
                    elif b2 == 0x40: d += 1
                return ('an', None)
            if tag == 0x84:
                if r.o < len(r.d) and r.d[r.o]==0x84: r.adv()
                l = r.ru(); r.adv(l); r.ri()
                return ('oc', None)
            if tag == 0x85: return ('r', r.ri())
            if tag == 0x86:
                cls = r.rs(); return ('rc', (cls, r.ri()))
            return ('t', tag)
        
        # 0x94 CLASS DEF
        if b == 0x94:
            te = None
            pe = r.r1()
            if pe == 0x84:
                l = r.r1()
                te = r.rn(l).decode('latin-1',errors='replace') if l>0 else ''
            elif 0x21 <= pe <= 0x7c:
                chars = [chr(pe)]
                while r.o < len(r.d) and 0x21 <= r.d[r.o] <= 0x7c:
                    chars.append(chr(r.d[r.o])); r.adv()
                te = ''.join(chars)
            if not te: return ('obj', {'te':'','iv':[]})
            
            cls_name = TE2CLASS.get(te, te)
            obj = {'te':te,'cl':cls_name,'iv':[]}
            
            i2 = 0
            while i2 < len(te):
                c = te[i2]
                if c == '@':
                    v = read_val()
                    if v is None or v[0] == 'end': break
                    obj['iv'].append(('@', v))
                elif c == '%':
                    v = read_val()
                    if v and v[0] in ('s','cn','string'):
                        sv = v[1]
                        if sv: all_strings.add(sv)
                        obj['iv'].append(('%', sv))
                    else:
                        obj['iv'].append(('%', v))
                elif c in 'icslIB':
                    v = read_val()
                    if v is None or v[0] == 'end': break
                    obj['iv'].append((c, v))
                elif c in 'fd':
                    v = read_val()
                    if v is None or v[0] == 'end': break
                    obj['iv'].append((c, v))
                elif c == '*':
                    sv = read_cstring(r)
                    if sv: all_strings.add(sv)
                    obj['iv'].append(('*', sv))
                elif c == ':':
                    sv = r.rs()
                    if sv: all_selectors.add(sv)
                    obj['iv'].append((':', sv))
                elif c == '#':
                    sv = r.rs()
                    if sv: all_strings.add(sv)
                    obj['iv'].append(('#', sv))
                elif c == '{':
                    obj['iv'].append(('s', None))
                    d=1; j=i2+1
                    while j < len(te) and d > 0:
                        if te[j] == '{': d += 1
                        elif te[j] == '}': d -= 1
                        j += 1
                    members = te[i2+1:j-1]
                    mi = 0
                    while mi < len(members):
                        mc = members[mi]
                        if mc == '@': read_val()
                        elif mc == '%': read_val()
                        elif mc in 'icslIfd': read_val()
                        elif mc == '*':
                            sv = r.rs()
                            if sv: all_strings.add(sv)
                        elif mc == ':':
                            sv = r.rs()
                            if sv: all_selectors.add(sv)
                        elif mc == '{':
                            d2=1; k=mi+1
                            while k < len(members) and d2>0:
                                if members[k]=='{': d2+=1
                                elif members[k]=='}': d2-=1
                                k+=1
                            mi = k; continue
                        mi += 1
                    i2 = j; continue
                else:
                    read_val()
                i2 += 1
            return ('obj', obj)
        
        # 0x95
        if b == 0x95:
            ref = r.ri()
            while r.o < len(r.d) and r.d[r.o] not in (0x98,0x99): r.adv()
            r.adv()
            return ('or', ref)
        
        return ('?', b)
    
    def read_cstring(r):
        """char * / NXAtom value:
           84 84 <len> <chars> or <len_byte> <chars> or 84 25 <string>"""
        b = r.r1()
        if b == 0x84:
            tag = r.r1()
            if tag == 0x84:
                l = r.r1()
                return r.rn(l).decode('latin-1', errors='replace') if l > 0 else None
            elif tag == 0x25: return r.rs()
            elif tag == 0x01:
                l = r.ri()
                return r.rn(l).decode('latin-1', errors='replace') if l > 0 else None
            return None
        if 0x01 <= b <= 0x7f:
            return r.rn(b).decode('latin-1', errors='replace') if b > 0 else None
        return None
    
    safety = 0
    while r.o < len(r.d) and safety < 200000:
        safety += 1
        v = read_val()
        if v is None: break
        if v[0] == 'obj':
            obj = v[1]
            if obj.get('te'):  # only keep objects with non-empty type encoding
                objects.append(obj)
    
    return objects, all_strings, all_selectors, all_floats


def dump_nib(path):
    """Complete dump of a nib file."""
    with open(path,'rb') as f:
        data = f.read()
    
    result = {
        'path': path,
        'size': len(data),
        'arrays': [],
        'flat_atoms': scan_flat(data),
    }
    
    arrays = find_arrays(data)
    for a in arrays:
        if a['size'] < 10: continue
        entry = {
            'decl': a['decl'],
            'size': a['size'],
            'flat_atoms': scan_flat(a['raw']),
        }
        
        is_ts = len(a['raw'])>=13 and a['raw'][:2]==b'\x04\x0b' and a['raw'][2:13]==b'typedstream'
        if is_ts:
            objs, strs, sels, flts = decode_94_objects(a['raw'])
            entry['objects'] = objs
            entry['94_strings'] = sorted(strs)
            entry['94_selectors'] = sorted(sels)
            entry['94_floats'] = flts
        
        result['arrays'].append(entry)
    
    return result


if __name__ == "__main__":
    for path in sys.argv[1:] if len(sys.argv) > 1 else ['EnvelopeMaker.nib', 'Info.nib']:
        result = dump_nib(path)
        print(f"=== {path} ({result['size']} bytes) ===")
        
        fa = result['flat_atoms']
        print(f"Flat scan: {len(fa['strings'])} strings, {len(fa['selectors'])} selectors, "
              f"{len(fa['floats'])} floats, {len(fa['classes'])} classes")
        
        for a in result['arrays']:
            print(f"  [{a['decl']}] ({a['size']}B)")
            aft = a.get('94_strings', [])
            afs = a.get('94_selectors', [])
            objs = a.get('objects', [])
            print(f"    94-objects: {len(objs)}")
            if objs:
                for o in objs[:8]:
                    print(f"      [{o['cl']}] {str(o['iv'][:3])[:100]}")
                if len(objs) > 8:
                    print(f"      ... {len(objs)-8} more")
            if aft:
                print(f"    Strings: {sorted(aft)[:20]}")
            if afs:
                print(f"    Selectors: {sorted(afs)}")
        
        # Combine flat + structural selectors/strings
        all_sels = fa['selectors']
        all_strs = fa['strings']
        for a in result['arrays']:
            all_sels.update(a.get('flat_atoms', {}).get('selectors', set()))
            all_strs.update(a.get('flat_atoms', {}).get('strings', set()))
        
        print(f"\n  Combined selectors ({len(all_sels)}):")
        for s in sorted(all_sels):
            print(f"    {s}")
        
        print(f"\n  UI strings ({len([s for s in all_strs if len(s) < 50])}):")
        ui_strs = sorted([s for s in all_strs if 2 < len(s) < 50 and not s.startswith('_')])[:30]
        for s in ui_strs:
            print(f'    "{s}"')
        
        # Write detailed JSON
        jpath = path.replace('.nib','.dump.json')
        # Make JSON-serializable
        def clean(v):
            if isinstance(v, set): return sorted(v)
            if isinstance(v, bytes): return v.decode('latin-1', errors='replace')
            return v
        with open(jpath, 'w') as f:
            json.dump(result, f, indent=2, default=clean, ensure_ascii=False)
        print(f"\n  -> {jpath}")
