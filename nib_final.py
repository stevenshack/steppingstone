#!/usr/bin/env python3
"""nib_final.py - NeXTSTEP nib extractor.
Extracts 94-opcode objects from .nib files with type-encoding-driven ivar decoding.

Usage:  python3 nib_final.py [nibfile.nib ...]

Output: JSON file with all decoded objects, strings, and selectors per array.

Key findings from NeXTSTEP typedstream.h:
- '%' = NXAtom (unique string), NOT 'id'
- '*' = char * (C string, often encoded as 84 84 <len> <chars>)
- '@' = id (object reference)
- '!' = int (ignored)
"""

import struct, sys, json, os

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
        if b == 0x81: return self.r1()
        if b == 0x82:
            v = struct.unpack_from('>h',self.d,self.o-2)[0] if self.o-1<len(self.d) else 0
            return v
        if b == 0x83:
            v = struct.unpack_from('>i',self.d,self.o-4)[0] if self.o-3<len(self.d) else 0
            return v
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
            v = struct.unpack_from('>H',self.d,self.o-2)[0] if self.o-1<len(self.d) else 0
            return v
        if b == 0x83:
            v = struct.unpack_from('>I',self.d,self.o-4)[0] if self.o-3<len(self.d) else 0
            return v
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
    '{_NSRect=ffff}{_NSRect=ffff}@@': 'View',
    'iiii***@s@': 'WindowTemplate', '%%%%i@@': 'HeaderClass',
}

def decode_all(raw):
    r = R(raw)
    # Skip typedstream header
    if r.o+13 <= len(r.d) and r.d[r.o:r.o+2]==b'\x04\x0b' and r.d[r.o+2:r.o+13]==b'typedstream':
        r.adv(13)
        while r.o < len(r.d) and r.d[r.o] in (0x81,0xa2):
            if r.d[r.o]==0x81: r.adv(2)
            elif r.d[r.o]==0xa2: r.adv(1)
            else: break
    
    objects = []
    strings = set()
    selectors = set()
    floats = []
    
    def read_cstring(r):
        """Read a char * / NXAtom value from typedstream.
        Format: 84 84 <len_byte> <chars>  OR  <len_byte> <chars>  OR  84 25 <string>"""
        b = r.r1()
        if b == 0x84:
            tag = r.r1()
            if tag == 0x84:
                l = r.r1()
                return r.rn(l).decode('latin-1', errors='replace') if l > 0 else None
            elif tag == 0x25:
                return r.rs()
            elif tag == 0x01:
                l = r.ri()
                return r.rn(l).decode('latin-1', errors='replace') if l > 0 else None
            return None
        elif 0x01 <= b <= 0x7f:
            # Direct length byte
            if b == 0: return None
            return r.rn(b).decode('latin-1', errors='replace') if b > 0 else None
        return None
    
    def read_val():
        nonlocal strings, selectors, floats
        if r.o >= len(r.d): return None
        b = r.r1()
        if 0x01 <= b <= 0x7f: return ('i', b)
        if b in (0x7d,0x7e,0x7f): return read_val()
        if b == 0x81: return ('i', r.r1())
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
                floats.append(v); return ('f', v)
            if t == 0x06:
                v = struct.unpack_from('>d',r.d,r.o-8)[0] if r.o-7<len(r.d) else 0
                return ('d', v)
            if t == 0x0c:
                s = r.rs(); strings.add(s) if s else None; return ('cn', s)
            if t == 0x0e:
                s = r.rs(); selectors.add(s) if s else None; return ('sl', s)
            if t == 0x84:
                s = r.rs(); strings.add(s) if s else None; return ('s', s)
            if t in (0x16,0x81): return ('i', r.ri())
            if t == 0x82:
                v = struct.unpack_from('>h',r.d,r.o-2)[0]; return ('s', v)
            if t == 0x83:
                v = struct.unpack_from('>i',r.d,r.o-4)[0]; return ('i4', v)
            return ('x', t)
        if b in (0x98,0x99): return ('end', None)
        if b in (0xa8,0xac): return ('i', r.ri())
        # 0x00 is NOT a stream terminator here - it's a version byte for old class_defs
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
                s = r.rs(); strings.add(s) if s else None; return ('s', s)
            if tag == 0x40:
                depth = 1
                while depth > 0 and r.o < len(r.d):
                    b2 = r.r1()
                    if b2 in (0x98,0x99): depth -= 1
                    elif b2 == 0x40: depth += 1
                return ('an', None)
            if tag == 0x84:
                if r.o < len(r.d) and r.d[r.o]==0x84: r.adv()
                l = r.ru()
                r.adv(l)
                r.ri()
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
                        if sv: strings.add(sv)
                        obj['iv'].append(('%', sv))
                    else:
                        obj['iv'].append(('%', v))
                elif c in 'icslIB':
                    v = read_val()
                    if v is None or v[0] == 'end': break
                    obj['iv'].append((c, v))
                elif c == 'f':
                    v = read_val()
                    if v is None or v[0] == 'end': break
                    obj['iv'].append(('f', v))
                elif c == 'd':
                    v = read_val()
                    if v is None or v[0] == 'end': break
                    obj['iv'].append(('d', v))
                elif c == '*':
                    # char *: 84 84 <len> <chars> or <len_byte> <chars>
                    # or 84 25 <len> <string>
                    sv = read_cstring(r)
                    if sv: strings.add(sv)
                    obj['iv'].append(('*', sv))
                elif c == ':':
                    v = r.rs()
                    if v: selectors.add(v)
                    obj['iv'].append((':', v))
                elif c == '#':
                    v = r.rs()
                    if v: strings.add(v)
                    obj['iv'].append(('#', v))
                elif c == '{':
                    obj['iv'].append(('s', None))
                    d=1; j=i2+1
                    while j < len(te) and d > 0:
                        if te[j] == '{': d+=1
                        elif te[j] == '}': d-=1
                        j+=1
                    # Read struct members
                    members = te[i2+1:j-1]
                    mi = 0
                    while mi < len(members):
                        mc = members[mi]
                        if mc == '@': read_val()
                        elif mc == '%': read_cstring(r)
                        elif mc in 'icslIfd': read_val()
                        elif mc == '*' or mc == ':': r.rs()
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
    
    # Process through entire data
    safety = 0
    while r.o < len(r.d) and safety < 200000:
        safety += 1
        v = read_val()
        if v is None: break
        if v[0] == 'obj':
            objects.append(v[1])
    
    return {
        'objects': objects,
        'strings': sorted(strings),
        'selectors': sorted(selectors),
        'floats': floats[:50],
    }

if __name__ == "__main__":
    for path in sys.argv[1:] if len(sys.argv) > 1 else ['EnvelopeMaker.nib', 'Info.nib']:
        with open(path,'rb') as f:
            data = f.read()
        arrays = find_arrays(data)
        print(f"=== {path} ({len(data)} bytes) ===")
        for idx, raw in enumerate(arrays):
            if len(raw) < 50: continue
            result = decode_all(raw)
            print(f"\n  Array {idx} ({len(raw)}B): {len(result['objects'])} objects, "
                  f"{len(result['strings'])} strings, {len(result['selectors'])} selectors")
            for obj in result['objects'][:15]:
                cl = obj.get('cl', obj.get('te', '?'))
                print(f"    [{cl}] te={obj.get('te','')}")
                print(f"      Full: {str(obj)[:120]}")
                for iv in obj['iv'][:8]:
                    print(f"      {iv}")
                if len(obj['iv']) > 8:
                    print(f"      ... {len(obj['iv'])-8} more")
            if len(result['objects']) > 15:
                print(f"    ... {len(result['objects'])-15} more")
        
        out = path.replace('.nib','.final.json')
        all_objs = []
        for raw in arrays:
            if len(raw) >= 50:
                r = decode_all(raw)
                all_objs.extend(r['objects'])
        with open(out,'w') as f:
            json.dump({'objects': all_objs}, f, indent=2, default=str)
        print(f"  -> {out}")
