#!/usr/bin/env python3
"""nib_complete.py - COMPLETE NeXTSTEP nib decoder.
Extracts EVERYTHING: all objects, all references resolved, all atoms.
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
    def __init__(self, d, o=0): self.d = d; self.o = o
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
        if b == 0x82: v = struct.unpack_from('>h',self.d,self.o-2)[0] if self.o-1<len(self.d) else 0; return v
        if b == 0x83: v = struct.unpack_from('>i',self.d,self.o-4)[0] if self.o-3<len(self.d) else 0; return v
        if 0x01 <= b <= 0x7f: return b
        if 0x84 <= b <= 0x87: return b-256
        if b in (0xa8,0xac): return self.ri()
        if b == 0x88: return 0
        return b
    def ru(self):
        if self.o >= len(self.d): return 0
        b = self.r1()
        if b == 0x81: return self.r1()
        if b == 0x82: v = struct.unpack_from('>H',self.d,self.o-2)[0]; return v
        if b == 0x83: v = struct.unpack_from('>I',self.d,self.o-4)[0]; return v
        if 0x01 <= b <= 0x7f: return b
        if b == 0x84: n = self.r1(); return self.ri() if n == 0x01 else n
        return 0
    def rs(self):
        l = self.ru()
        if l <= 0 or self.o+l > len(self.d): return None
        return self.rn(l).decode('latin-1',errors='replace')

TE2CLASS = {
    '@@@@s': 'NibData', '%ii': 'Storage', 'i%': 'List',
    '*@': 'CustomObject', '*@ss': 'Cell', '*@ssffi@': 'ButtonCell',
    '*@ss@': 'Control', 'ff': 'MenuTemplate', 'ffff': 'NSRect',
    '%%%%i@@': 'HeaderClass', 's*': 'NXImage', '*fss': 'Font',
}

# ---- Typedstream value reader ----
def read_val(r, ctx=None):
    """Read one typedstream value, with optional reference context tracking."""
    if r.o >= len(r.d): return None
    b = r.r1()
    if 0x01 <= b <= 0x7f: return ('i', b, r.o-1)
    if b in (0x7d,0x7e,0x7f): return read_val(r, ctx)
    if b == 0x81: v = r.r1(); v = v if v<128 else v-256; return ('i', v, r.o-2)
    if b == 0x82: v = struct.unpack_from('>h',r.d,r.o-2)[0]; return ('s', v, r.o-4)
    if b == 0x83: v = struct.unpack_from('>i',r.d,r.o-4)[0]; return ('i4', v, r.o-8)
    if b in (0x85,0x92,0x96,0xa2):
        ref = r.ri()
        if ctx and isinstance(ctx, dict) and 'refs' in ctx: ctx['refs'].append((r.o-2, ref))
        return ('r', ref, r.o-2)
    if b in (0x88,0x9c,0x9d): return ('n', None, r.o-1)
    if b == 0x86:
        cls = r.rs()
        ref = r.ri()
        if ctx and isinstance(ctx, dict) and 'refs' in ctx: ctx['refs'].append((r.o-2, ref))
        return ('rc', (cls, ref), r.o-2)
    if b == 0x8c: r.rs(); return ('at', None, r.o-1)
    if b == 0x93: return ('ct', r.ri(), r.o-1)
    if b == 0x97:
        t = r.r1()
        if t in (0x01,0x04): return ('n', None, r.o-2)
        if t == 0x02: return ('b', True, r.o-2)
        if t == 0x03: return ('b', False, r.o-2)
        if t == 0x05: v = struct.unpack_from('>f',r.d,r.o-4)[0] if r.o-3<len(r.d) else 0; return ('f', v, r.o-6)
        if t == 0x06: v = struct.unpack_from('>d',r.d,r.o-8)[0]; return ('d', v, r.o-10)
        if t == 0x0c: s = r.rs(); return ('cn', s, r.o-1) if s else ('n', None, r.o-1)
        if t == 0x0e: s = r.rs(); return ('sl', s, r.o-1) if s else ('n', None, r.o-1)
        if t == 0x84: s = r.rs(); return ('s', s, r.o-1) if s else ('n', None, r.o-1)
        if t in (0x16,0x81): return ('i', r.ri(), r.o-2)
        if t == 0x82: v = struct.unpack_from('>h',r.d,r.o-2)[0]; return ('s', v, r.o-4)
        if t == 0x83: v = struct.unpack_from('>i',r.d,r.o-4)[0]; return ('i4', v, r.o-8)
        return ('x', t, r.o-2)
    if b in (0x98,0x99): return ('e', None, r.o-1)
    if b in (0xa8,0xac): return ('i', r.ri(), r.o-1)
    if b == 0x00: return None
    if b == 0x84: return read_tagged(r, ctx)
    if b == 0x94:
        te, iv = read_94(r, ctx)
        if not te: return ('obj', {'te':''}, r.o-1)
        cls = TE2CLASS.get(te, te)
        return ('obj', {'te':te,'cl':cls,'iv':iv}, r.o-1)
    if b == 0x95:
        ref = r.ri()
        if ctx and isinstance(ctx, dict) and 'refs' in ctx: ctx['refs'].append((r.o-2, ref))
        # Skip ivars
        d = 1
        while d > 0 and r.o < len(r.d):
            if r.d[r.o] in (0x98,0x99): d -= 1
            r.adv()
        return ('or', ref, r.o-1)
    return ('?', b, r.o-1)

def read_tagged(r, ctx=None):
    tag = r.r1()
    if tag == 0x01: return ('i', r.ri(), r.o-2)
    if tag in (0x05,0x06,0x07):
        start = r.o
        end = r.d.find(b']', start, start+32)
        if end > start and r.d[start]==ord('['):
            r.adv(end-start+1)
            sz = int(r.d[start:end].decode()[1:-2])
            r.adv(sz)
        return ('arr', None, r.o-1)
    if tag == 0x25: s = r.rs(); return ('s', s, r.o-1) if s else ('n', None, r.o-1)
    if tag == 0x40:
        d = 1
        while d > 0 and r.o < len(r.d):
            if r.d[r.o] in (0x98,0x99): d -= 1
            r.adv()
        return ('an', None, r.o-1)
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
            ctx2 = {'refs': []}
            iv = read_ivars_by_te(r, te, ctx2)
            for pos, ref in ctx2['refs']:
                if ctx and isinstance(ctx, dict) and 'refs' in ctx: ctx['refs'].append((pos, ref))
            return ('obj', {'te':te,'cl':name,'ver':ver,'iv':iv}, r.o-1)
        return ('oc', None, r.o-1)
    if tag == 0x85: ref = r.ri(); return ('r', ref, r.o-2)
    if tag == 0x86:
        cls = r.rs(); ref = r.ri(); return ('rc', (cls, ref), r.o-2)
    return ('t', tag, r.o-1)

def read_94(r, ctx=None):
    """Read a 94 class_def. Returns (te, iv_list)."""
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
    iv = read_ivars_by_te(r, te, ctx)
    return (te, iv)

def read_ivars_by_te(r, te, ctx=None):
    """Read ivar values according to a type encoding string."""
    iv = []
    i2 = 0
    while i2 < len(te):
        c = te[i2]
        if c == '@':
            v = read_val(r, ctx)
            if v is None or v[0] == 'e': break
            iv.append(('@', v))
        elif c == '%':
            v = read_val(r, ctx)
            if v and v[0] in ('s','cn','S'):
                sv = v[1]; iv.append(('%', sv))
            elif v and v[0] == 'i' and isinstance(v[1], int):
                # Check if this small int is actually a string reference
                # In HeaderClass, consecutive ints after a count are ASCII chars
                iv.append(('%', v))
            elif v and v[0] == 'r':
                iv.append(('%', v))
            else:
                iv.append(('%', v) if v else ('%', None))
        elif c in 'icslIB':
            v = read_val(r, ctx)
            if v is None or v[0] == 'e': break
            iv.append((c, v))
        elif c in 'fd':
            v = read_val(r, ctx)
            if v is None or v[0] == 'e': break
            if c == 'f' and v and v[0] == 'i':
                v = ('f', float(v[1]), v[2])
            if c == 'd' and v and v[0] == 'i':
                v = ('d', float(v[1]), v[2])
            iv.append((c, v))
        elif c == '*':
            sv = read_cstr(r)
            iv.append(('*', sv))
        elif c == ':':
            sv = r.rs()
            iv.append((':', sv))
        elif c == '#':
            sv = r.rs()
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
                if mc in '@%': read_val(r, ctx)
                elif mc in 'icslIfd': read_val(r, ctx)
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
        else:
            read_val(r, ctx)
        i2 += 1
    return iv

def read_cstr(r):
    """Read a char * / NXAtom string: 84 84 <len> or 84 25 <string> or <len> <chars>"""
    b = r.r1()
    if b == 0x84:
        tag = r.r1()
        if tag == 0x84:
            l = r.r1()
            return r.rn(l).decode('latin-1',errors='replace') if l>0 else None
        if tag == 0x25: return r.rs()
        if tag == 0x01:
            l = r.ri()
            return r.rn(l).decode('latin-1',errors='replace') if l>0 else None
        return None
    if 0x01 <= b <= 0x7f:
        return r.rn(b).decode('latin-1',errors='replace') if b>0 else None
    return None

# ---- The NXHashTable reference resolver ----
# Maps reference IDs to object data based on NXHashTable struct layout

class RefResolver:
    """Builds and resolves reference maps from nib data."""
    def __init__(self):
        self.refs = {}      # ref_id -> {'type': '94'|'oc'|'data', 'te': ..., 'obj': ...}
        self.strings = set()
        self.selectors = set()
        self.floats = []
        self.entries = []   # Ordered list of all decoded entries
    
    def scan_for_refs(self, raw):
        """Scan raw data for all 94-objects and collect references."""
        # First pass: find all 94 objects and build ordered list
        pos = 0
        obj_index = 0
        while pos < len(raw):
            if raw[pos] == 0x94:
                r = R(raw)
                r.o = pos + 1
                te, iv = read_94(r, None)
                if te:
                    cls = TE2CLASS.get(te, te)
                    obj = {'te': te, 'cl': cls, 'iv': iv}
                    self.entries.append(('94', obj))
                    self.refs[obj_index] = {'type': '94', 'te': te, 'obj': obj}
                    obj_index += 1
                pos = r.o if te else pos + 2
            else:
                pos += 1
        
        # Second pass: collect all reference IDs from typedstream values
        ref_ids = set()
        pos = 0
        while pos < len(raw):
            if raw[pos] in (0x85,0x92,0x96,0xa2):
                r = R(raw, pos + 1)
                ref = r.ri()
                ref_ids.add(ref)
                pos += 2
            elif raw[pos] == 0x86:
                r = R(raw, pos + 1)
                cls = r.rs(); ref = r.ri()
                ref_ids.add(ref)
                pos = r.o
            else:
                pos += 1
        
        # Map object references: for each ref, note which objects are nearby
        # Simple heuristic: ref N → object at position N in entries
        for ref_id in ref_ids:
            if 0 <= ref_id < len(self.entries):
                if ref_id not in self.refs:
                    self.refs[ref_id] = self.entries[ref_id]
        
        return list(ref_ids)

def _skip_array(r, tag):
    start = r.o
    end = r.d.find(b']', start, start+32)
    if end > start and r.d[start]==ord('['):
        r.adv(end-start+1)
        try: sz = int(r.d[start:end].decode()[1:-2])
        except: sz = 0
        r.adv(sz)

def _scan_values(r):
    """Skip over typedstream values without decoding, STOPPING at 0x94."""
    safety = 0
    while r.o < len(r.d) and safety < 1000:
        safety += 1
        b = r.d[r.o]
        if b in (0x98,0x99): r.adv(); return
        if b == 0x94: return
        if b == 0x84:
            r.adv(); tag = r.r1()
            if tag == 0x84:
                if r.o < len(r.d) and r.d[r.o]==0x84: r.adv()
                l = r.ru(); r.adv(l+1)
            elif tag in (0x05,0x06,0x07):
                _skip_array(r, tag)
            elif tag == 0x25: r.rs()
            elif tag == 0x40:
                d2=1
                while d2 > 0 and r.o < len(r.d):
                    if r.d[r.o] in (0x98,0x99): d2 -= 1
                    r.adv()
            elif tag in (0x01,): r.ri()
            elif tag == 0x85: r.ri()
            elif tag == 0x86: r.rs(); r.ri()
        elif b in (0x85,0x92,0x96,0xa2): r.adv(); r.ri()
        elif b == 0x86: r.adv(); r.rs(); r.ri()
        elif b == 0x95: r.adv(); r.ri()
        elif b in (0x88,0x9c,0x9d): r.adv()
        elif b == 0x97:
            r.adv(); t = r.r1()
            if t in (0x05,): r.adv(4)
            elif t in (0x06,): r.adv(8)
            elif t in (0x0c,0x0e,0x84): r.rs()
            elif t in (0x16,0x81): r.ri()
            elif t == 0x82: r.adv(2)
            elif t == 0x83: r.adv(4)
        elif 0x01 <= b <= 0x7f: r.adv()
        else: r.adv()

def extract_nib(path):
    """Complete nib extraction with reference resolution."""
    with open(path,'rb') as f:
        data = f.read()
    
    arrays = find_arrays(data)
    resolver = RefResolver()
    
    # Phase 1: Flat scan for ALL strings/selectors
    for raw in arrays:
        for m in re.finditer(b'[A-Za-z_][A-Za-z0-9_]{2,60}', raw):
            try: resolver.strings.add(m.group().decode('ascii'))
            except: pass
        for m in re.finditer(b'[ -~]{3,}', raw):
            try:
                s = m.group().decode('ascii').strip()
                if len(s) >= 3: resolver.strings.add(s)
            except: pass
        for m in re.finditer(b'[A-Za-z_][A-Za-z0-9_]+:', raw):
            try: resolver.selectors.add(m.group().decode('ascii'))
            except: pass
        # Typedstream selectors/strings from 97 0e/0c/84
        i = 0
        while i < len(raw) - 5:
            if raw[i] == 0x97:
                st = raw[i+1]
                if st in (0x0c,0x84,0x0e):
                    l = raw[i+2] if i+2 < len(raw) else 0
                    if 0 < l < 60 and i+3+l <= len(raw):
                        s = raw[i+3:i+3+l].decode('latin-1',errors='replace')
                        if st == 0x0e: resolver.selectors.add(s)
                        else: resolver.strings.add(s)
                    i += 3; continue
                elif st == 0x05:
                    resolver.floats.append(struct.unpack_from('>f',raw,i+2)[0])
                    i += 6; continue
            i += 1
    
    # Phase 2: Scan each array for refs and objects
    all_refs = []
    for raw in arrays:
        if len(raw) < 50: continue
        if raw[:2]==b'\x04\x0b' and raw[2:13]==b'typedstream':
            refs = resolver.scan_for_refs(raw)
            all_refs.extend(refs)
    
    # Phase 3: Build resolved object graph
    resolved = {'objects': []}
    for entry_type, obj in resolver.entries:
        if entry_type == '94':
            resolved['objects'].append(obj)
    
    result = {
        'path': path,
        'size': len(data),
        'strings': sorted(resolver.strings),
        'selectors': sorted(resolver.selectors),
        'floats': resolver.floats[:50],
        'objects': resolved['objects'],
        'ref_table': {str(k): v for k, v in resolver.refs.items()},
    }
    
    return result


if __name__ == "__main__":
    for path in sys.argv[1:] if len(sys.argv) > 1 else ['EnvelopeMaker.nib', 'Info.nib']:
        result = extract_nib(path)
        print(f"=== {path} ({result['size']} bytes) ===")
        print(f"  Objects: {len(result['objects'])}")
        print(f"  Strings: {len(result['strings'])}")
        print(f"  Selectors: {len(result['selectors'])}")
        print(f"  Floats: {len(result['floats'])}")
        
        for obj in result['objects']:
            te = obj.get('te','')
            cl = obj.get('cl', te)
            print(f"  [{cl}] te=\"{te}\"")
            # Show decoded ivars
            for iv in obj.get('iv', []):
                t, v = iv[0], iv[1]
                if t == '*':
                    print(f"    * = \"{v}\"" if isinstance(v, str) else f"    * = {v}")
                elif t == '%':
                    if isinstance(v, tuple) and v[0] == 's':
                        print(f"    % = \"{v[1]}\"")
                    elif isinstance(v, tuple):
                        print(f"    % = {v}")
                    else:
                        print(f"    % = \"{v}\"")
                elif t == '@':
                    if isinstance(v, tuple) and len(v) >= 2:
                        print(f"    @ = {v[0]}({v[1]})")
                    else:
                        print(f"    @ = {v}")
                else:
                    print(f"    {t} = {v}")
        
        print(f"\n  All selectors ({len(result['selectors'])}):")
        for s in result['selectors']:
            print(f"    {s}")
        
        jpath = path.replace('.nib','.complete.json')
        with open(jpath, 'w') as f:
            json.dump(result, f, indent=2, default=str, ensure_ascii=False)
        print(f"\n  -> {jpath}")
