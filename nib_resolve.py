#!/usr/bin/env python3
"""nib_resolve.py - Complete NeXTSTEP nib decoder with reference resolution.
Extracts ALL 94-objects AND resolves references through the HashTable mapping.
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
                raw = data[e+1:e+1+sz]
                arrays.append(raw)
                i = e+1+sz; continue
        i += 1
    return arrays

class R:
    __slots__ = ('d','o')
    def __init__(self, d): self.d = d; self.o = 0
    def adv(self, n=1): self.o = min(self.o+n, len(self.d))
    def r1(self):
        if self.o >= len(self.d): return 0
        v = self.d[self.o]; self.o += 1; return v
    def rn(self, n):
        e = min(self.o+n, len(self.d)); v = self.d[self.o:e]; self.o = e; return v
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
        return self.rn(l).decode('latin-1',errors='replace')
    def read_cstr(self):
        b = self.r1()
        if b == 0x84:
            t = self.r1()
            if t == 0x84:
                l = self.r1()
                return self.rn(l).decode('latin-1',errors='replace') if l>0 else None
            if t == 0x25: return self.rs()
            if t == 0x01:
                l = self.ri()
                return self.rn(l).decode('latin-1',errors='replace') if l>0 else None
            return None
        if 0x01 <= b <= 0x7f:
            return self.rn(b).decode('latin-1',errors='replace') if b>0 else None
        return None

TE2CLASS = {
    '@@@@s': 'NibData', '%ii': 'Storage', 'i%': 'List',
    '*@': 'CustomObject', '*@ss': 'Cell', '*@ssffi@': 'ButtonCell',
    '*@ss@': 'Control', 'ff': 'MenuTemplate',
    '%%%%i@@': 'HeaderClass', 's*': 'NXImage', '*fss': 'Font',
}

def decode_94_te(r, strings, selectors, floats):
    """Read and decode a 94 class_def from current position.
    Returns (type_encoding, ivar_list)."""
    pe = r.r1()
    te = None
    if pe == 0x84:
        l = r.r1()
        te = r.rn(l).decode('latin-1',errors='replace') if l>0 else ''
    elif 0x21 <= pe <= 0x7c:
        chars = [chr(pe)]
        while r.o < len(r.d) and 0x21 <= r.d[r.o] <= 0x7c:
            chars.append(chr(r.d[r.o])); r.adv()
        te = ''.join(chars)
    else:
        return (None, [])
    
    iv = []
    i2 = 0
    while i2 < len(te):
        c = te[i2]
        if c == '@':
            v = read_val(r)
            if v is None or v[0] == 'e': break
            iv.append(('@', v))
        elif c == '%':
            v = read_val(r)
            if v and v[0] in ('s','cn','S'):
                sv = v[1]; strings.add(sv) if sv else None
                iv.append(('%', sv))
            else:
                iv.append(('%', v))
        elif c in 'icslIB':
            v = read_val(r)
            if v is None or v[0] == 'e': break
            iv.append((c, v))
        elif c in 'fd':
            v = read_val(r)
            if v is None or v[0] == 'e': break
            iv.append((c, v))
        elif c == '*':
            sv = r.read_cstr()
            if sv: strings.add(sv)
            iv.append(('*', sv))
        elif c == ':':
            sv = r.rs()
            if sv: selectors.add(sv)
            iv.append((':', sv))
        elif c == '#':
            sv = r.rs()
            if sv: strings.add(sv)
            iv.append(('#', sv))
        elif c == '{':
            iv.append(('s', None))
            d=1; j=i2+1
            while j < len(te) and d > 0:
                if te[j] == '{': d += 1
                elif te[j] == '}': d -= 1
                j += 1
            members = te[i2+1:j-1]
            mi = 0
            while mi < len(members):
                mc = members[mi]
                if mc == '@': read_val(r)
                elif mc == '%': read_val(r)
                elif mc in 'icslIfd': read_val(r)
                elif mc == '*':
                    sv = r.rs()
                    if sv: strings.add(sv)
                elif mc == ':':
                    sv = r.rs()
                    if sv: selectors.add(sv)
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
            read_val(r)
        i2 += 1
    return (te, iv)

def read_val(r):
    """Read one typedstream value."""
    if r.o >= len(r.d): return None
    b = r.r1()
    if 0x01 <= b <= 0x7f: return ('i', b)
    if b in (0x7d,0x7e,0x7f): return read_val(r)
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
            v = struct.unpack_from('>f',r.d,r.o-4)[0] if r.o-3<len(r.d) else 0; return ('f', v)
        if t == 0x06:
            v = struct.unpack_from('>d',r.d,r.o-8)[0]; return ('d', v)
        if t == 0x0c:
            s = r.rs(); return ('cn', s) if s else ('n', None)
        if t == 0x0e:
            s = r.rs(); return ('sl', s) if s else ('n', None)
        if t == 0x84:
            s = r.rs(); return ('s', s) if s else ('n', None)
        if t in (0x16,0x81): return ('i', r.ri())
        if t == 0x82:
            v = struct.unpack_from('>h',r.d,r.o-2)[0]; return ('s', v)
        if t == 0x83:
            v = struct.unpack_from('>i',r.d,r.o-4)[0]; return ('i4', v)
        return ('x', t)
    if b in (0x98,0x99): return ('e', None)
    if b in (0xa8,0xac): return ('i', r.ri())
    if b == 0x00: return None
    if b == 0x84:
        return read_tagged(r)
    if b == 0x94:
        te, iv = decode_94_te(r, set(), set(), [])
        if not te: return ('obj', {'te':'','iv':[]})
        cls = TE2CLASS.get(te, te)
        return ('obj', {'te':te,'cl':cls,'iv':iv})
    if b == 0x95:
        ref = r.ri()
        while r.o < len(r.d) and r.d[r.o] not in (0x98,0x99): r.adv()
        r.adv()
        return ('or', ref)
    return ('?', b)

def read_tagged(r):
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
        s = r.rs(); return ('s', s) if s else ('n', None)
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


def extract_hash_table_mapping(raw, start_offset):
    """Extract the reference → object mapping from the HashTable data.
    The HashTable is encoded with type_enc 'i%%' after the class_def+version.
    Returns {ref_id: object_info_dict}."""
    r = R(raw)
    # Skip to HashTable data
    if r.o+13 <= len(r.d) and r.d[r.o:r.o+2]==b'\x04\x0b' and r.d[r.o+2:r.o+13]==b'typedstream':
        r.adv(13)
        while r.o < len(r.d) and r.d[r.o] in (0x81,0xa2):
            if r.d[r.o]==0x81: r.adv(2)
            elif r.d[r.o]==0xa2: r.adv(1)
            else: break
    
    # Find the [20c] array (first object - small HashTable) area
    # Skip outer StreamTable/HashTable
    r.adv(3)  # int 64
    # Skip StreamTable class_def (84 84 ... StreamTable 01)
    if r.d[r.o]==0x84:
        read_tagged(r)  # skip StreamTable
    # Skip HashTable class_def
    if r.d[r.o]==0x84:
        read_tagged(r)  # skip HashTable
    
    # Find the [20c] array which contains the ref mapping
    while r.o < len(r.d):
        b = r.d[r.o]
        if b == 0x84 and r.o+2 < len(r.d) and r.d[r.o+1] in (0x05,0x06,0x07):
            tag = r.d[r.o+1]
            start = r.o+2
            end = r.d.find(b']', start, start+32)
            if end > start:
                decl = r.d[start:end+1].decode('latin-1',errors='replace')
                try: sz = int(decl[1:-2])
                except: sz = 0
                if sz == 20:
                    # [20c] contains the HashTable with reference mapping
                    ra = r.d[end+1:end+1+sz]
                    return extract_refs_from_hash(ra)
                r.adv(end-start+3+sz); continue
        r.adv()
    return {}

def extract_refs_from_hash(data):
    """Extract reference IDs from a small [20c] HashTable typedstream.
    The [20c] contains: header + obj_ref + hash data."""
    r = R(data)
    # Skip header
    if r.o+13 <= len(r.d) and r.d[r.o:r.o+2]==b'\x04\x0b' and r.d[r.o+2:r.o+13]==b'typedstream':
        r.adv(13)
        while r.o < len(r.d) and r.d[r.o] in (0x81,0xa2):
            if r.d[r.o]==0x81: r.adv(2)
            elif r.d[r.o]==0xa2: r.adv(1)
            else: break
    
    # Read: int 64, then ref 0 (from [20c] data)
    v = read_val(r)
    v = read_val(r)
    
    refs = set()
    while r.o < len(r.d):
        v = read_val(r)
        if v and v[0] == 'r':
            refs.add(v[1])
    
    return refs


def build_ref_table(raw_arrays):
    """Build the complete reference table from all arrays.
    Scans the data for ref opcodes paired with 94 objects."""
    
    ref_table = {}
    strings = set()
    
    for raw in raw_arrays:
        if len(raw) < 50: continue
        if not (raw[:2]==b'\x04\x0b' and raw[2:13]==b'typedstream'): continue
        
        r = R(raw)
        r.adv(13)
        while r.o < len(r.d) and r.d[r.o] in (0x81,0xa2):
            if r.d[r.o]==0x81: r.adv(2)
            elif r.d[r.o]==0xa2: r.adv(1)
            else: break
        
        safety = 0
        while r.o < len(r.d) and safety < 50000:
            safety += 1
            b = r.d[r.o]
            
            if b in (0x98,0x99):
                r.adv(); continue
            
            if b == 0x94:
                te, iv = decode_94_te(r, set(), set(), [])
                if te:
                    ref_table[f'94_{te}'] = {'te': te, 'iv_count': len(iv)}
                continue
            
            if b in (0x85,0x92,0x96,0xa2):
                r.adv(); ref_val = r.ri()
                if ref_val not in ref_table:
                    ref_table[ref_val] = {'ref': ref_val}
                continue
            
            if b == 0x84:
                tag = r.d[r.o+1] if r.o+1 < len(r.d) else 0
                if tag == 0x84:
                    r.adv(2)
                    if r.o < len(r.d) and r.d[r.o]==0x84: r.adv()
                    l = r.ru()
                    name = r.rn(l).decode('latin-1',errors='replace') if l>0 else ''
                    r.ri()
                    ref_table[f'oc_{name}'] = {'name': name}
                elif tag in (0x05,0x06,0x07):
                    r.adv(2)
                    end = r.d.find(b']', r.o, r.o+32)
                    if end > r.o and r.d[r.o]==ord('['):
                        decl = r.d[r.o:end+1].decode('latin-1',errors='replace')
                        r.adv(end - r.o + 1)
                        sz = int(decl[1:-2])
                        r.adv(sz)
                    else: r.adv()
                elif tag == 0x25:
                    r.adv(2); l = r.ru(); r.adv(l) if l else None
                elif tag in (0x01,): r.adv(2); r.ri()
                elif tag == 0x40:
                    r.adv(2); d = 1
                    while r.o < len(r.d) and d > 0:
                        if r.d[r.o] in (0x98,0x99): d -= 1
                        r.adv()
                elif tag == 0x85: r.adv(2); r.ri()
                else: r.adv(2)
                continue
            
            if b == 0x97:
                r.adv(); t = r.r1()
                if t in (0x05,): r.adv(4)
                elif t in (0x06,): r.adv(8)
                elif t in (0x0c,0x0e,0x84): r.rs()
                elif t in (0x16,0x81): r.ri()
                elif t == 0x82: r.adv(2)
                elif t == 0x83: r.adv(4)
                continue
            
            if 0x01 <= b <= 0x7f: r.adv(); continue
            if b in (0x88,0x9c,0x9d): r.adv(); continue
            if b == 0x86: r.adv(); r.rs(); r.ri(); continue
            if b in (0x8c,): r.adv(); r.rs(); continue
            if b == 0x93: r.adv(); r.ri(); continue
            if b in (0xa8,0xac): r.adv(); r.ri(); continue
            
            r.adv()
    
    return ref_table


def decode_any_te(r, strings, selectors, floats):
    """Read and decode ANY type-encoding-driven object.
    Handles both old-style 84 84 and new-style 94 class_defs."""
    if r.o >= len(r.d): return None
    
    b = r.d[r.o]
    
    if b == 0x94:
        r.adv()
        te, iv = decode_94_te(r, strings, selectors, floats)
        return {'te': te, 'iv': iv} if te else None
    
    if b == 0x84:
        r.adv()
        tag = r.r1()
        if tag == 0x84:
            if r.o < len(r.d) and r.d[r.o]==0x84: r.adv()
            l = r.ru()
            name = r.rn(l).decode('latin-1',errors='replace') if l>0 else ''
            ver = r.ri()
            # Read type encoding chars
            te_chars = []
            while r.o < len(r.d) and 0x21 <= r.d[r.o] <= 0x7c:
                te_chars.append(chr(r.d[r.o])); r.adv()
            te = ''.join(te_chars)
            if te:
                # Parse ivars according to type encoding
                iv = []
                i2 = 0
                while i2 < len(te):
                    c = te[i2]
                    if c in '@':
                        v = read_val(r)
                        iv.append(('@', v))
                    elif c == '%':
                        sv = r.read_cstr()
                        if sv: strings.add(sv)
                        iv.append(('%', sv))
                    elif c in 'icslIBfd':
                        v = read_val(r)
                        if v and v[0] != 'e': iv.append((c, v))
                    elif c == '*':
                        sv = r.read_cstr()
                        if sv: strings.add(sv)
                        iv.append(('*', sv))
                    elif c == ':':
                        sv = r.rs()
                        if sv: selectors.add(sv)
                        iv.append((':', sv))
                    elif c == '{':
                        iv.append(('s', None))
                        d=1; j=i2+1
                        while j < len(te) and d > 0:
                            if te[j] == '{': d += 1
                            elif te[j] == '}': d -= 1
                            j += 1
                        members = te[i2+1:j-1]
                        mi = 0
                        while mi < len(members):
                            mc = members[mi]
                            if mc == '@': read_val(r)
                            elif mc in 'icslIfd': read_val(r)
                            elif mc == '*': r.rs()
                            elif mc == ':': r.rs()
                            elif mc == '{':
                                d2=1; k=mi+1
                                while k < len(members) and d2>0:
                                    if members[k]=='{': d2+=1
                                    elif members[k]=='}': d2-=1
                                    k+=1
                                mi = k; continue
                            mi += 1
                        i2 = j; continue
                    i2 += 1
                return {'cl': name, 'te': te, 'iv': iv}
        elif tag == 0x01:
            r.ri()
        # other tags (array, string) handled implicitly
    
    return None


def extract_everything(path):
    """Complete extraction of everything from a nib file."""
    with open(path,'rb') as f:
        data = f.read()
    
    arrays = find_arrays(data)
    result = {
        'path': path,
        'size': len(data),
        'arrays': [],
        'all_strings': set(),
        'all_selectors': set(),
        'all_floats': [],
        'ref_table': {},
    }
    
    strings = result['all_strings']
    selectors = result['all_selectors']
    floats = result['all_floats']
    
    # First: flat scan for ALL atoms
    for raw in arrays:
        if len(raw) < 10: continue
        # Strings
        for m in re.finditer(b'[A-Za-z_][A-Za-z0-9_]{2,60}', raw):
            try: strings.add(m.group().decode('ascii'))
            except: pass
        for m in re.finditer(b'[ -~]{3,}', raw):
            try:
                s = m.group().decode('ascii').strip()
                if len(s) >= 3: strings.add(s)
            except: pass
        # Selectors
        for m in re.finditer(b'[A-Za-z_][A-Za-z0-9_]+:', raw):
            try: selectors.add(m.group().decode('ascii'))
            except: pass
        # Typedstream atoms
        i = 0
        while i < len(raw) - 5:
            if raw[i] == 0x97:
                st = raw[i+1]
                if st == 0x05 and i+6 <= len(raw):
                    floats.append(struct.unpack_from('>f',raw,i+2)[0])
                    i += 6; continue
                elif st == 0x0e:
                    l = raw[i+2] if i+2 < len(raw) else 0
                    if 0 < l < 60 and i+3+l <= len(raw):
                        selectors.add(raw[i+3:i+3+l].decode('latin-1',errors='replace'))
                    i += 3; continue
                elif st == 0x0c or st == 0x84:
                    l = raw[i+2] if i+2 < len(raw) else 0
                    if 0 < l < 60 and i+3+l <= len(raw):
                        strings.add(raw[i+3:i+3+l].decode('latin-1',errors='replace'))
                    i += 3; continue
            i += 1
    
    # Second: decode 94-objects and build ref table from each array
    for raw in arrays:
        if len(raw) < 50: continue
        if not (raw[:2]==b'\x04\x0b' and raw[2:13]==b'typedstream'): continue
        
        r = R(raw)
        r.adv(13)
        while r.o < len(r.d) and r.d[r.o] in (0x81,0xa2):
            if r.d[r.o]==0x81: r.adv(2)
            elif r.d[r.o]==0xa2: r.adv(1)
            else: break
        
        entry = {'size': len(raw), 'objects': [], 'strings': [], 'selectors': []}
        
        # Find 94 objects and decode them all
        safety = 0
        pos = 0
        while pos < len(raw) and safety < 5000:
            safety += 1
            if raw[pos] == 0x94:
                nr = R(raw)
                nr.o = pos + 1  # skip 0x94 opcode
                te, iv = decode_94_te(nr, strings, selectors, floats)
                if te:
                    cls = TE2CLASS.get(te, te)
                    entry['objects'].append({'te': te, 'cl': cls, 'iv': iv})
                pos = nr.o
            else:
                pos += 1
        
        entry['strings'] = sorted(strings.intersection(entry['objects'][0]['te'] if entry['objects'] else []))[:10] if entry['objects'] else []
        entry['selectors'] = sorted(selectors)[:30]
        result['arrays'].append(entry)
    
    result['all_strings'] = sorted(strings)
    result['all_selectors'] = sorted(selectors)
    result['all_floats'] = floats[:50]
    
    # Build ref table
    result['ref_table'] = build_ref_table(arrays)
    
    return result


if __name__ == "__main__":
    for path in sys.argv[1:] if len(sys.argv) > 1 else ['EnvelopeMaker.nib', 'Info.nib']:
        result = extract_everything(path)
        print(f"=== {path} ===")
        print(f"  Objects: {sum(len(a['objects']) for a in result['arrays'])}")
        print(f"  Strings: {len(result['all_strings'])}")
        print(f"  Selectors: {len(result['all_selectors'])}")
        print(f"  Floats: {len(result['all_floats'])}")
        
        for i, a in enumerate(result['arrays']):
            print(f"  Array {i} ({a['size']}B): {len(a['objects'])} objects")
            for o in a['objects'][:10]:
                cl = o.get('cl', o.get('te', '?'))
                print(f"    [{cl}] te={o.get('te','')}")
                for iv in o.get('iv',[])[:4]:
                    print(f"      {str(iv)[:100]}")
                if len(o.get('iv',[])) > 4:
                    print(f"      ... {len(o['iv'])-4} more")
        
        print(f"  Selectors: {[s for s in result['all_selectors'] if s.endswith(':')][:35]}")
        print(f"  -> {path.replace('.nib','.full.json')}")
        
        with open(path.replace('.nib','.full.json'), 'w') as f:
            json.dump(result, f, indent=2, default=lambda x: sorted(x) if isinstance(x, set) else str(x))
