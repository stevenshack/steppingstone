#!/usr/bin/env python3
"""NeXTSTEP nib parser - FINAL VERSION.
Key insights discovered through reverse engineering:
- 94 class_def: <type_encoding> <ivar_values...> (NO separate version field)
- 84 84 old class_def: <name> <version> <type_encoding_chars> <ivar_values...>
- 97 84 <string> = extended value sub-type 0x84 = tagged string (class name or id)
- @/% type = object: encoded as 0x94(def), 0x95(ref+ivars), 0x85(ref), 0x92(ref), or 97-values
"""

import struct, sys, json, re

class BR:
    def __init__(self, d):
        self.d = d; self.o = 0
    def e(self): return self.o >= len(self.d)
    def r1(self):
        if self.o >= len(self.d): return 0
        v = self.d[self.o]; self.o += 1; return v
    def rn(self, n):
        e = min(self.o+n, len(self.d))
        v = self.d[self.o:e]; self.o = e; return v
    def pk(self): return self.d[self.o] if self.o < len(self.d) else 0

    def ri(self):
        if self.o >= len(self.d): return 0
        b = self.d[self.o]; self.o += 1
        if b == 0x81:
            v = self.d[self.o] if self.o < len(self.d) else 0; self.o += 1
            return v if v < 128 else v-256
        elif b == 0x82:
            v = struct.unpack_from('>h',self.d,self.o)[0] if self.o+1<len(self.d) else 0
            self.o += 2; return v
        elif b == 0x83:
            v = struct.unpack_from('>i',self.d,self.o)[0] if self.o+3<len(self.d) else 0
            self.o += 4; return v
        elif 0x01 <= b <= 0x7f: return b
        elif 0x84 <= b <= 0x87: return b-256
        elif b in (0xa8,0xac): return self.ri()
        elif b == 0x88: return 0
        else: return b

    def ru(self):
        if self.o >= len(self.d): return 0
        b = self.d[self.o]; self.o += 1
        if b == 0x81:
            v = self.d[self.o] if self.o < len(self.d) else 0; self.o += 1; return v
        elif b == 0x82:
            v = struct.unpack_from('>H',self.d,self.o)[0] if self.o+1<len(self.d) else 0
            self.o += 2; return v
        elif b == 0x83:
            v = struct.unpack_from('>I',self.d,self.o)[0] if self.o+3<len(self.d) else 0
            self.o += 4; return v
        elif 0x01 <= b <= 0x7f: return b
        elif b == 0x84:
            n = self.d[self.o] if self.o < len(self.d) else 0; self.o += 1
            if n == 0x01: return self.ri()
            return n
        else: return 0

    def rs(self):
        l = self.ru()
        if l <= 0 or self.o+l > len(self.d): return None
        s = self.d[self.o:self.o+l].decode('latin-1',errors='replace')
        self.o += l; return s

    def rtype_enc(self):
        """Read type encoding string from stream.
        Format: either direct printable chars, or 84 <len> <chars>"""
        b = self.pk()
        if b == 0x84:
            self.o += 1
            l = self.r1()
            return self.rn(l).decode('latin-1',errors='replace') if l > 0 else ''
        elif 0x21 <= b <= 0x7c:
            chars = []
            while self.o < len(self.d) and 0x21 <= self.d[self.o] <= 0x7c:
                chars.append(chr(self.d[self.o])); self.o += 1
            return ''.join(chars)
        return ''

    def skip_ts(self):
        while self.o+13 <= len(self.d):
            if self.d[self.o:self.o+2]==b'\x04\x0b' and self.d[self.o+2:self.o+13]==b'typedstream':
                self.o += 13
                while self.o < len(self.d):
                    b = self.d[self.o]
                    if b == 0x81: self.o += 2
                    elif b == 0xa2: self.o += 1
                    elif b == 0x84 and self.o+1<len(self.d) and self.d[self.o+1] in (0x01,0x40):
                        n = self.d[self.o+1]
                        if n == 0x01: self.o += 3
                        elif n == 0x40: self.o += 2
                        else: break
                    else: break
            else: break


def find_arrays(data):
    arrays = []
    i = 0
    while i < len(data):
        if data[i]==0x84 and i+2<len(data) and data[i+1] in (0x05,0x06,0x07):
            start = i+2
            end = data.find(b']', start, start+32)
            if end > start and data[start]==ord('['):
                decl = data[start:end+1].decode('latin-1',errors='replace')
                try: sz = int(decl[1:-2])
                except: sz = 0
                raw = data[end+1:end+1+sz] if end+1+sz <= len(data) else data[end+1:]
                arrays.append({'decl':decl,'size':sz,'raw':raw})
                i = end+1+sz
                continue
        i += 1
    return arrays


def extract_all(raw):
    """Extract ALL objects, strings, selectors from typedstream data.
    Returns (objects_list, metadata_dict)."""
    r = BR(raw)
    r.skip_ts()
    
    objects = []
    strings = set()
    selectors = set()
    floats = []
    
    def rval():
        """Read one value from typedstream."""
        nonlocal strings, selectors, floats
        if r.e(): return None
        
        b = r.r1()
        
        # Small integers
        if 0x01 <= b <= 0x7f:
            return ('i', b)
        
        # Fillers
        if b in (0x7d,0x7e,0x7f):
            return rval()
        
        # Multi-byte integers
        if b == 0x81:
            v = r.r1() if not r.e() else 0
            v = v if v < 128 else v-256
            return ('i', v)
        if b == 0x82:
            v = struct.unpack_from('>h',r.d,r.o)[0] if r.o+1<len(r.d) else 0
            r.o += 2; return ('s', v)
        if b == 0x83:
            v = struct.unpack_from('>i',r.d,r.o)[0] if r.o+3<len(r.d) else 0
            r.o += 4; return ('i4', v)
        
        # 0x84 = tagged value
        if b == 0x84:
            return rtagged()
        
        # References
        if b == 0x85: return ('r', r.ri())
        if b == 0x86:
            cls = r.rs()
            return ('rc', (cls, r.ri()))
        if b == 0x92: return ('r', r.ri())
        if b == 0x93: return ('ct', r.ri())
        if b == 0x96: return ('ov', r.ri())
        if b == 0xa2: return ('r', r.ri())
        
        # Nil markers
        if b in (0x88,0x9c,0x9d): return ('n', None)
        
        # Array type
        if b == 0x8c: return ('at', r.rs())
        
        # 0x94 = class_def (NO version field - type_encoding is followed directly by ivars)
        if b == 0x94:
            te = r.rtype_enc()
            if not te:
                return ('obj', {'c':'','te':'','iv':[]})
            iv = []
            i = 0
            while i < len(te):
                ch = te[i]
                if ch == '@' or ch == '%':
                    # Object: could be inline class_def, ref, or nil
                    v = rval()
                    if v is not None:
                        strings.add(str(v))
                    iv.append(('@', v))
                elif ch == 'i':
                    iv.append(('i', r.ri()))
                elif ch == 'f':
                    # Check for 97 05 prefix
                    if r.o+1 < len(r.d) and r.d[r.o] == 0x97 and r.d[r.o+1] == 0x05:
                        r.o += 2
                        v = struct.unpack_from('>f',r.d,r.o)[0] if r.o+3<len(r.d) else 0
                        r.o += 4
                        floats.append(v)
                        iv.append(('f', v))
                    else:
                        iv.append(('f', r.ri()))
                elif ch == '*':
                    s = r.rs()
                    if s: strings.add(s)
                    iv.append(('*', s))
                elif ch == ':':
                    s = r.rs()
                    if s: selectors.add(s)
                    iv.append((':', s))
                elif ch == '{':
                    iv.append(('s', None))
                    # Skip struct members
                    nesting = 1
                    j = i+1
                    while j < len(te) and nesting > 0:
                        if te[j] == '{': nesting += 1
                        elif te[j] == '}': nesting -= 1
                        j += 1
                    # Read struct values
                    ii = i+1
                    while ii < j-1:
                        sc = te[ii]
                        if sc in '@%': rval()
                        elif sc == 'i': r.ri()
                        elif sc == 'f':
                            if r.o+1 < len(r.d) and r.d[r.o] == 0x97 and r.d[r.o+1] == 0x05:
                                r.o += 2; r.o += 4
                            else: r.ri()
                        elif sc == '*': r.rs()
                        elif sc == '{':
                            d=1; k=ii+1
                            while k < len(te) and d>0:
                                if te[k]=='{': d+=1
                                elif te[k]=='}': d-=1
                                k+=1
                            ii = k; continue
                        ii += 1
                    i = j
                    continue
                elif ch == '#':
                    v = rval()
                    if v: strings.add(str(v))
                    iv.append(('#', v))
                else:
                    rval()
                i += 1
            return ('obj', {'c':te, 'te':te, 'iv':iv})
        
        # 0x95 = obj_ref with ivars
        if b == 0x95:
            ref = r.ri()
            iv = read_until_end()
            return ('or', (ref, iv))
        
        # 0x97 = extended value
        if b == 0x97:
            if r.e(): return ('n', None)
            t = r.r1()
            if t == 0x01: return ('n', None)
            if t == 0x02: return ('b', True)
            if t == 0x03: return ('b', False)
            if t == 0x04: return ('n', None)
            if t == 0x05:
                v = struct.unpack_from('>f',r.d,r.o)[0] if r.o+3<len(r.d) else 0
                r.o += 4; floats.append(v); return ('f', v)
            if t == 0x06:
                v = struct.unpack_from('>d',r.d,r.o)[0] if r.o+7<len(r.d) else 0
                r.o += 8; return ('d', v)
            if t == 0x0c:
                s = r.rs(); strings.add(s) if s else None; return ('cn', s)
            if t == 0x0e:
                s = r.rs(); selectors.add(s) if s else None; return ('sl', s)
            if t == 0x14: return ('ie', None)
            if t == 0x16: return ('i', r.ri())
            if t == 0x81: return ('i', r.ri())
            if t == 0x82:
                v = struct.unpack_from('>h',r.d,r.o)[0] if r.o+1<len(r.d) else 0
                r.o += 2; return ('s', v)
            # 0x84 sub-type: tagged string (class name reference)
            if t == 0x84:
                s = r.rs()
                if s: strings.add(s)
                return ('cn', s)
            return ('x', t)
        
        # End markers
        if b in (0x98,0x99):
            return ('end', None)
        
        # Other
        if b in (0xa8,0xac): return ('i', r.ri())
        if b == 0x00: return None
        return ('?', b)
    
    def rtagged():
        tag = r.r1()
        if tag == 0x01: return ('i', r.ri())
        if tag in (0x05,0x06,0x07):
            start = r.o
            end = r.d.find(b']', start, start+32)
            if end < 0: return ('e', 'unterm_bracket')
            decl = r.d[start:end+1].decode('latin-1',errors='replace')
            r.o = end + 1
            try: sz = int(decl[1:-2])
            except: sz = 0
            raw = r.rn(sz)
            result = ('arr', {'d':decl,'sz':sz})
            if len(raw)>=13 and raw[:2]==b'\x04\x0b' and raw[2:13]==b'typedstream':
                nr = BR(raw)
                nr.skip_ts()
                items = []
                while not nr.e():
                    v = val_or_none(nr)
                    if v is None: break
                    items.append(v)
                result[1]['n'] = items
            else:
                result[1]['h'] = raw.hex()
            return result
        if tag == 0x25:
            s = r.rs()
            if s: strings.add(s)
            return ('s', s)
        if tag == 0x40:
            return ('ano', read_until_end())
        if tag == 0x84:
            # Old class_def
            if r.pk() == 0x84: r.o += 1
            l = r.ru()
            name = r.rn(l).decode('latin-1',errors='replace') if l>0 else None
            ver = r.ri()
            te = r.rtype_enc()
            return ('obj', {'c':name,'ver':ver,'te':te,'iv':[]})
        if tag == 0x85: return ('r', r.ri())
        if tag == 0x86:
            cls = r.rs()
            return ('rc', (cls, r.ri()))
        return ('t', (tag, r.ri()))
    
    def read_until_end():
        iv = []
        while not r.e():
            b = r.d[r.o]
            if b in (0x98,0x99): r.o += 1; return iv
            if b == 0x00: return iv
            if b == 0x04 and r.o+2<=len(r.d) and r.d[r.o:r.o+2]==b'\x04\x0b':
                return iv
            v = rval()
            if v is None: return iv
            if v[0] in ('end','ie'): return iv
            iv.append(v)
        return iv
    
    def val_or_none(br):
        """rval but returns None at boundaries."""
        old_o = br.o
        v = rval()
        if v is None: return None
        if v[0] == 'end': br.o = old_o; return None
        return v
    
    while not r.e():
        v = val_or_none(r)
        if v is None: break
        objects.append(v)
    
    return objects, {
        'strings': sorted(strings),
        'selectors': sorted(selectors),
        'floats': floats,
    }


def dump(v, indent=0):
    pfx = '  '*indent
    if v is None: print(f"{pfx}nil"); return
    tt, val = v
    if tt == 'obj':
        c = val.get('c','?'); te = val.get('te','')
        print(f"{pfx}[{c}] te=\"{te}\"")
        for iv in val.get('iv',[]):
            t2, v2 = iv
            if t2 == '@':
                print(f"{pfx}  @", end='')
                dump(v2, 0)
            else:
                print(f"{pfx}  {t2} {v2}")
    elif tt == 'arr':
        d = val.get('d','?')
        sz = val.get('sz',0)
        if 'n' in val:
            print(f"{pfx}[arr({sz}B)]")
            for iv in val['n']: dump(iv, indent+1)
        else:
            print(f"{pfx}[arr {d} ({sz}B)]")
    elif tt in ('i','s','i4'): print(f"{pfx}{tt} {val}")
    elif tt == 'f': print(f"{pfx}f {val}")
    elif tt == 'r': print(f"{pfx}r {val}")
    elif tt == 'ov': print(f"{pfx}ov {val}")
    elif tt == 'or': print(f"{pfx}or({val[0]})"); [dump(iv,indent+1) for iv in val[1]]
    elif tt == 'cn': print(f"{pfx}cn \"{val}\"")
    elif tt == 'sl': print(f"{pfx}sel \"{val}\"")
    elif tt == 's': print(f"{pfx}s \"{val}\"")
    elif tt == 'n': print(f"{pfx}nil")
    elif tt == 'b': print(f"{pfx}b {val}")
    elif tt == '*': print(f"{pfx}* \"{val}\"")
    elif tt == 'ano': print(f"{pfx}anon"); [dump(iv,indent+1) for iv in val]
    else: print(f"{pfx}[{tt}] {val}")


if __name__ == "__main__":
    for path in ['EnvelopeMaker.nib', 'Info.nib']:
        with open(path,'rb') as f:
            data = f.read()
        arrays = find_arrays(data)
        print(f"=== {path} ({len(data)} bytes) ===")
        for a in arrays:
            if a['size'] > 50:
                objs, meta = extract_all(a['raw'])
                print(f"\n  [{a['decl']}] ({a['size']}B) → {len(objs)} values")
                print(f"  Strings ({len(meta['strings'])}): {meta['strings'][:30]}")
                print(f"  Selectors ({len(meta['selectors'])}): {meta['selectors']}")
                print(f"  Floats: {meta['floats'][:20]}")
                for o in objs[:10]:
                    dump(o, 4)
                if len(objs) > 10:
                    print(f"  ... {len(objs)-10} more")
