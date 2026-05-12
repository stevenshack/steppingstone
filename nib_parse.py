#!/usr/bin/env python3
"""nib_parse: Minimal NeXTSTEP nib parser.
Extracts ALL 94-opcode class_def objects with full type-encoding-driven ivar decoding.
Internal container classes (84 84 format) are skipped.

Usage: nib_parse.py <nibfile>
Output: JSON with all UI objects, strings, selectors, frames.
"""

import struct, sys, json

class Reader:
    __slots__ = ('d','o')
    def __init__(self, d, o=0):
        self.d = d; self.o = o
    def e(self): return self.o >= len(self.d)
    def r1(self):
        v = self.d[self.o] if self.o < len(self.d) else 0
        self.o += 1
        return v
    def adv(self, n=1):
        self.o = min(self.o + n, len(self.d))
    def rn(self, n):
        e = min(self.o+n, len(self.d))
        v = self.d[self.o:e]; self.o = e; return v
    def ri(self):
        if self.o >= len(self.d): return 0
        b = self.d[self.o]; self.adv()
        if b == 0x81: return self.r1() if self.o < len(self.d) else 0
        if b == 0x82:
            v = struct.unpack_from('>h',self.d,self.o)[0] if self.o+1<len(self.d) else 0
            self.adv(2); return v
        if b == 0x83:
            v = struct.unpack_from('>i',self.d,self.o)[0] if self.o+3<len(self.d) else 0
            self.adv(4); return v
        if 0x01 <= b <= 0x7f: return b
        if 0x84 <= b <= 0x87: return b-256
        if b in (0xa8,0xac): return self.ri()
        if b == 0x88: return 0
        return b
    def ru(self):
        if self.o >= len(self.d): return 0
        b = self.d[self.o]; self.adv()
        if b == 0x81: return self.r1()
        if b == 0x82:
            v = struct.unpack_from('>H',self.d,self.o)[0] if self.o+1<len(self.d) else 0
            self.adv(2); return v
        if b == 0x83:
            v = struct.unpack_from('>I',self.d,self.o)[0] if self.o+3<len(self.d) else 0
            self.adv(4); return v
        if 0x01 <= b <= 0x7f: return b
        if b == 0x84:
            n = self.r1()
            if n == 0x01: return self.ri()
            return n
        return 0
    def rs(self):
        l = self.ru()
        if l <= 0 or self.o+l > len(self.d): return None
        s = self.d[self.o:self.o+l]
        self.adv(l)
        return s.decode('latin-1',errors='replace')

# Type encoding → known class name mapping  
TE2CLASS = {
    '@@@@s': 'NibData', '%ii': 'Storage', 'i%': 'List',
    '*@': 'CustomObject', '*@ss': 'Cell', '*@ssffi@': 'ButtonCell',
    '*@ss@': 'Control', 'ff': 'MenuTemplate',
    '{_NSRect=ffff}{_NSRect=ffff}@@': 'View',
    'iiii***@s@': 'WindowTemplate', '%%%%i@@': 'HeaderClass',
    '@@': 'Box', 's*': 'NXImage', '*fss': 'Font',
    '@': 'ViewTemplate',
}

def decode_nib(path):
    """Decode nib file, return all 94-objects + metadata."""
    with open(path,'rb') as f:
        data = f.read()
    
    # Find all [Nc] arrays
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
                arrays.append({'decl':decl,'size':sz,'raw':raw})
                i = e+1+sz; continue
        i += 1
    
    result = {'objects': [], 'strings': set(), 'selectors': set(), 'floats': []}
    strs = result['strings']; sels = result['selectors']; flts = result['floats']
    
    def scan(r, top_level=True):
        """Flat scanner for typedstream."""
        import struct as _struct
        _safety = 0
        
        while not r.e():
            _safety += 1
            if _safety > 100000: return
            
            b = r.r1()
            
            if b == 0x00: return
            if b in (0x7d,0x7e,0x7f): continue
            
            # End markers
            if b in (0x98,0x99):
                if top_level: continue  # skip at top level
                return
            
            if 0x01 <= b <= 0x7f: continue
            
            # Multi-byte ints
            if b == 0x81: r.adv(); continue
            if b == 0x82: r.adv(2); continue
            if b == 0x83: r.adv(4); continue
            
            # References
            if b in (0x85,0x92,0x96,0xa2): r.ri(); continue
            if b == 0x86: r.rs(); r.ri(); continue
            if b == 0x8c: r.rs(); continue
            if b == 0x93: r.ri(); continue
            
            # Nil
            if b in (0x88,0x9c,0x9d): continue
            
            # Tagged value 0x84
            if b == 0x84:
                tag = r.r1()
                if tag == 0x01: r.ri(); continue
                if tag in (0x05,0x06,0x07):
                    start = r.o
                    end = r.d.find(b']', start, start+32)
                    if end > start and r.d[start]==ord('['):
                        decl = r.d[start:end+1].decode('latin-1',errors='replace')
                        r.adv(end-start+1)
                        try: sz = int(decl[1:-2])
                        except: sz = 0
                        arr_raw = r.rn(sz)
                        if len(arr_raw)>=13 and arr_raw[:2]==b'\x04\x0b' and arr_raw[2:13]==b'typedstream':
                            nr = Reader(arr_raw)
                            nr.adv(13)
                            while nr.o < len(arr_raw) and nr.d[nr.o] in (0x81,0xa2):
                                if nr.d[nr.o]==0x81: nr.adv(2)
                                elif nr.d[nr.o]==0xa2: nr.adv(1)
                                else: break
                            scan(nr)
                    continue
                if tag == 0x25: r.rs(); continue
                if tag == 0x40:
                    # anonymous object - skip to 98/99
                    _s2 = 0
                    while not r.e() and _s2 < 5000:
                        _s2 += 1
                        if r.d[r.o] in (0x98,0x99): r.adv(); break
                        r.adv()
                    continue
                if tag == 0x84:
                    if r.o < len(r.d) and r.d[r.o] == 0x84: r.adv()
                    l = r.ru()
                    r.adv(l)  # skip class name
                    r.ri()    # skip version
                    continue
                if tag == 0x85: r.ri(); continue
                if tag == 0x86: r.rs(); r.ri(); continue
                if tag in (0x8c,): r.rs(); continue
                continue
            
            # Extended value 0x97
            if b == 0x97:
                if r.e(): continue
                t = r.r1()
                if t == 0x05: r.adv(4); flts.append(struct.unpack_from('>f',r.d,r.o-4)[0])
                elif t == 0x06: r.adv(8)
                elif t == 0x0c: s = r.rs(); strs.add(s) if s else None
                elif t == 0x0e: s = r.rs(); sels.add(s) if s else None
                elif t in (0x16,0x81): r.ri()
                elif t == 0x82: r.adv(2)
                elif t == 0x83: r.adv(4)
                elif t == 0x84: s = r.rs(); strs.add(s) if s else None
                elif t == 0x14: pass
                continue
            
            # 94 class_def - THIS IS WHAT WE CARE ABOUT
            if b == 0x94:
                obj = decode_94_obj(r, strs, sels)
                if obj:
                    result['objects'].append(obj)
                continue
            
            # 95 object ref with ivars
            if b == 0x95:
                r.ri()
                _s2 = 0
                while not r.e() and _s2 < 5000:
                    _s2 += 1
                    if r.d[r.o] in (0x98,0x99): r.adv(); break
                    r.adv()
                continue
            
            if b in (0xa8,0xac): r.ri(); continue
    
    def decode_94_obj(r, strs, sels):
        """Decode a 94 class_def object.
        Format: 94 [tagged_len|<chars>] <ivar_values...> (NO version)
        """
        te = None
        b = r.r1()
        
        # Read type encoding
        if b == 0x84:
            l = r.r1()
            te = r.rn(l).decode('latin-1',errors='replace') if l > 0 else ''
        elif 0x21 <= b <= 0x7c:
            chars = [chr(b)]
            while r.o < len(r.d) and 0x21 <= r.d[r.o] <= 0x7c:
                chars.append(chr(r.d[r.o])); r.adv()
            te = ''.join(chars)
        
        if not te:
            return None
        
        cls_name = TE2CLASS.get(te, te)
        obj = {'class': cls_name, 'type_enc': te, 'ivars': []}
        
        def read_typed_val():
            """Read a typed value from stream, returning decoded value."""
            nonlocal strs, sels
            if r.e(): return ('nil', None)
            b = r.r1()
            if 0x01 <= b <= 0x7f: return ('int', b)
            if b in (0x7d,0x7e,0x7f): return read_typed_val()
            if b == 0x81:
                v = r.r1(); v = v if v<128 else v-256; return ('int', v)
            if b == 0x82:
                v = struct.unpack_from('>h',r.d,r.o)[0] if r.o+1<len(r.d) else 0
                r.adv(2); return ('short', v)
            if b == 0x83:
                v = struct.unpack_from('>i',r.d,r.o)[0] if r.o+3<len(r.d) else 0
                r.adv(4); return ('int32', v)
            if b == 0x84:
                tag = r.r1()
                if tag == 0x01: return ('int', r.ri())
                if tag in (0x05,0x06,0x07):
                    start = r.o
                    end = r.d.find(b']', start, start+32)
                    if end > start and r.d[start]==ord('['):
                        r.adv(end-start+1)
                        try: sz = int(r.d[start:end].decode()[1:-2])
                        except: sz = 0
                        r.adv(sz)
                    return ('array', None)
                if tag == 0x25:
                    s = r.rs()
                    if s: strs.add(s)
                    return ('string', s)
                if tag == 0x40:
                    while not r.e() and r.d[r.o] not in (0x98,0x99): r.adv()
                    r.adv()
                    return ('anon', None)
                if tag == 0x84:
                    if r.o < len(r.d) and r.d[r.o] == 0x84: r.adv()
                    l = r.ru()
                    name = r.rn(l).decode() if l>0 else None
                    r.ri()
                    return ('oldclass', name)
                if tag == 0x85: return ('ref', r.ri())
                if tag == 0x86:
                    cls = r.rs()
                    return ('ref_class', (cls, r.ri()))
                return ('tag', tag)
            if b in (0x85,0x92,0xa2): return ('ref', r.ri())
            if b == 0x86:
                cls = r.rs()
                return ('ref_class', (cls, r.ri()))
            if b in (0x88,0x9c,0x9d): return ('nil', None)
            if b == 0x8c: r.rs(); return ('arrtype', None)
            if b == 0x93: return ('cont', r.ri())
            if b == 0x94:
                te2 = r.rtype_enc()
                if not te2: return ('nil', None)
                sub_obj = {'class': TE2CLASS.get(te2, te2), 'type_enc': te2, 'ivars': []}
                i2 = 0
                while i2 < len(te2):
                    c2 = te2[i2]
                    if c2 in '@%':
                        sub_obj['ivars'].append(('@', read_typed_val()))
                    elif c2 == 'i' or c2 == 's' or c2 == 'I':
                        sub_obj['ivars'].append((c2, read_typed_val()))
                    elif c2 == 'f' or c2 == 'd':
                        sub_obj['ivars'].append((c2, read_typed_val()))
                    elif c2 == '*':
                        sv = r.rs()
                        if sv: strs.add(sv)
                        sub_obj['ivars'].append(('*', sv))
                    elif c2 == ':':
                        sv = r.rs()
                        if sv: sels.add(sv)
                        sub_obj['ivars'].append((':', sv))
                    elif c2 == '{':
                        sub_obj['ivars'].append(('s', None))
                        d=1; j=i2+1
                        while j<len(te2) and d>0:
                            if te2[j]=='{': d+=1
                            elif te2[j]=='}': d-=1
                            j+=1
                        i2=j; continue
                    else:
                        read_typed_val()
                    i2 += 1
                return ('obj', sub_obj)
            if b == 0x95:
                ref = r.ri()
                while not r.e() and r.d[r.o] not in (0x98,0x99): r.adv()
                r.adv()
                return ('or', ref)
            if b == 0x96: return ('ref', r.ri())
            if b == 0x97:
                t = r.r1()
                if t in (0x01,0x04): return ('nil', None)
                if t == 0x02: return ('bool', True)
                if t == 0x03: return ('bool', False)
                if t == 0x05:
                    v = struct.unpack_from('>f',r.d,r.o)[0] if r.o+3<len(r.d) else 0
                    r.adv(4); return ('float', v)
                if t == 0x06:
                    v = struct.unpack_from('>d',r.d,r.o)[0] if r.o+7<len(r.d) else 0
                    r.adv(8); return ('double', v)
                if t == 0x0c:
                    s = r.rs(); strs.add(s) if s else None; return ('class', s)
                if t == 0x0e:
                    s = r.rs(); sels.add(s) if s else None; return ('sel', s)
                if t == 0x84:
                    s = r.rs(); strs.add(s) if s else None; return ('string', s)
                if t in (0x16,0x81): return ('int', r.ri())
                if t == 0x82:
                    v = struct.unpack_from('>h',r.d,r.o)[0] if r.o+1<len(r.d) else 0
                    r.adv(2); return ('short', v)
                if t == 0x83:
                    v = struct.unpack_from('>i',r.d,r.o)[0] if r.o+3<len(r.d) else 0
                    r.adv(4); return ('int32', v)
                return ('ext', t)
            if b in (0xa8,0xac): return ('int', r.ri())
            if b == 0x00: return None
            return ('?', b)
        
        # Read ivars using the typed value reader
        i = 0
        while i < len(te):
            ch = te[i]
            if ch in '@%':
                obj['ivars'].append(('@', read_typed_val()))
            elif ch in 'icslI':
                obj['ivars'].append((ch, read_typed_val()))
            elif ch in 'fd':
                obj['ivars'].append((ch, read_typed_val()))
            elif ch == '*':
                sv = r.rs()
                if sv: strs.add(sv)
                obj['ivars'].append(('*', sv))
            elif ch == ':':
                sv = r.rs()
                if sv: sels.add(sv)
                obj['ivars'].append((':', sv))
            elif ch == '{':
                obj['ivars'].append(('s', None))
                d=1; j=i+1
                while j < len(te) and d > 0:
                    if te[j] == '{': d += 1
                    elif te[j] == '}': d -= 1
                    j += 1
                i = j; continue
            elif ch == '#':
                sv = r.rs()
                if sv: strs.add(sv)
                obj['ivars'].append(('#', sv))
            elif ch == 'B':
                obj['ivars'].append(('B', r.r1()))
            else:
                read_typed_val()
            i += 1
        
        return obj
    
    def read_id_val(r, strs, sels):
        """Read an id/object value. Returns a tuple (type, value)."""
        if r.e(): return ('nil', None)
        b = r.r1()
        
        if b == 0x94:  # Inline class_def
            obj = decode_94_obj(r, strs, sels)
            return ('obj', obj)
        
        if b == 0x95:  # obj_ref with ivars
            ref = r.ri()
            _s = 0
            while not r.e() and _s < 5000:
                _s += 1
                nb = r.d[r.o]
                if nb in (0x98,0x99): r.adv(); break
                # Simple skip
                if 0x01 <= nb <= 0x7f: r.adv()
                elif nb in (0x85,0x92,0x96,0xa2): r.ri()
                elif nb == 0x97:
                    r.adv()
                    t = r.r1()
                    if t in (0x05,): r.adv(4)
                    elif t in (0x0c,0x0e): r.rs()
                    elif t in (0x16,0x81): r.ri()
                    else: pass
                elif nb in (0x88,0x9c,0x9d): r.adv()
                elif nb == 0x94: break
                elif nb == 0x84:
                    r.adv(); tag = r.r1()
                    if tag in (0x01,): r.ri()
                    elif tag in (0x05,0x06,0x07):
                        s2 = r.o; e2 = r.d.find(b']', s2, s2+32)
                        if e2 > s2: r.adv(e2-s2+1)
                        try: sz2 = int(r.d[s2:e2].decode()[1:-2])
                        except: sz2 = 0
                        r.adv(sz2)
                    elif tag == 0x25: r.rs()
                    elif tag == 0x40:
                        while not r.e() and r.d[r.o] not in (0x98,0x99): r.adv()
                        r.adv()
                    elif tag == 0x85: r.ri()
                    else: pass
                else:
                    r.adv()
            return ('or', ref)
        
        if b == 0x85: return ('ref', r.ri())
        if b == 0x92: return ('ref', r.ri())
        if b == 0x96: return ('ref', r.ri())
        if b == 0xa2: return ('ref', r.ri())
        if b in (0x88,0x9c,0x9d): return ('nil', None)
        if b == 0x97:
            t = r.r1()
            if t in (0x01,0x04): return ('nil', None)
            if t == 0x02: return ('bool', True)
            if t == 0x03: return ('bool', False)
            if t == 0x0c: s = r.rs(); strs.add(s) if s else None; return ('class', s)
            if t == 0x0e: s = r.rs(); sels.add(s) if s else None; return ('sel', s)
            if t == 0x84: s = r.rs(); strs.add(s) if s else None; return ('string', s)
            return ('ext', t)
        if b == 0x84:
            tag = r.r1()
            if tag == 0x01: return ('int', r.ri())
            if tag == 0x25:
                s = r.rs()
                if s: strs.add(s)
                return ('string', s)
            if tag == 0x84:
                if r.o < len(r.d) and r.d[r.o] == 0x84: r.adv()
                l = r.ru()
                name = r.rn(l).decode('latin-1',errors='replace') if l>0 else None
                r.ri()  # version
                return ('old_class', name)
            if tag == 0x85: return ('ref', r.ri())
            if tag == 0x86:
                cls = r.rs()
                return ('ref_class', (cls, r.ri()))
            return ('tagged', tag)
        if b == 0x86:
            cls = r.rs()
            return ('ref_class', (cls, r.ri()))
        if 0x01 <= b <= 0x7f:
            return ('ref', b)  # small ints = object references in id context
        if b == 0x83:
            v = struct.unpack_from('>i',r.d,r.o)[0] if r.o+3<len(r.d) else 0
            r.adv(4)
            return ('int32', v)
        if b in (0x7d,0x7e,0x7f):
            return read_id_val(r, strs, sels)
        
        return ('?', b)
    
    # Process arrays
    for a in arrays:
        if a['size'] < 50: continue
        raw = a['raw']
        if len(raw)>=13 and raw[:2]==b'\x04\x0b' and raw[2:13]==b'typedstream':
            r = Reader(raw)
            r.adv(13)
            while r.o < len(raw) and raw[r.o] in (0x81,0xa2):
                if raw[r.o]==0x81: r.adv(2)
                elif raw[r.o]==0xa2: r.adv(1)
                else: break
            scan(r)
    
    result['strings'] = sorted(result['strings'])
    result['selectors'] = sorted(result['selectors'])
    result['floats'] = result['floats'][:50]
    return result


if __name__ == "__main__":
    for path in sys.argv[1:] if len(sys.argv) > 1 else ['EnvelopeMaker.nib', 'Info.nib']:
        result = decode_nib(path)
        print(f"=== {path} ===")
        print(f"  94-objects: {len(result['objects'])}")
        print(f"  Strings: {len(result['strings'])}")
        print(f"  Selectors: {len(result['selectors'])}")
        print(f"  Floats: {len(result['floats'])}")
        for obj in result['objects']:
            print(f"    [{obj['class']}] te={obj['type_enc']}")
            for iv in obj['ivars']:
                print(f"      {iv}")
        out = path.replace('.nib','.decoded.json')
        with open(out,'w') as f:
            json.dump(result, f, indent=2, default=str)
        print(f"  -> {out}")
