#!/usr/bin/env python3
"""Full NeXTSTEP typedstream parser with nested stream support."""
import struct, sys, os, json

class TypedStream:
    def __init__(self, data, name="root"):
        self.data = data; self.pos = 0; self.name = name
        self.objects = []
        self.current_obj = None
        self.obj_stack = []
    
    def ri(self):
        b = self.data[self.pos]; self.pos += 1
        if b == 0x81: v = self.data[self.pos]; self.pos += 1; return v
        elif b == 0x82: v = struct.unpack_from('>h', self.data, self.pos)[0]; self.pos += 2; return v
        elif b == 0x83: v = struct.unpack_from('>i', self.data, self.pos)[0]; self.pos += 4; return v
        elif 0x01 <= b <= 0x7f: return b
        elif 0x84 <= b <= 0x87: return b - 256
        else: return b
    
    def rs(self):
        l = self.ri()
        if l <= 0: return None
        s = self.data[self.pos:self.pos+l].decode('latin-1', errors='replace')
        self.pos += l; return s
    
    def skip_int(self):
        self.ri()  # Skip int (used when we know the value but don't need it)
    
    def push_obj(self, obj):
        self.objects.append(obj)
        if self.current_obj is not None:
            self.obj_stack.append(self.current_obj)
            self.current_obj['ivars'].append(obj)
        self.current_obj = obj
    
    def pop_obj(self):
        if self.obj_stack:
            self.current_obj = self.obj_stack.pop()
        else:
            self.current_obj = None
    
    def parse(self):
        # Skip header
        if self.data[self.pos:self.pos+2] == b'\x04\x0b':
            self.pos += 2
        if self.data[self.pos:self.pos+11] == b'typedstream':
            self.pos += 11
        if self.data[self.pos:self.pos+11] == b'typedstream':
            self.pos += 11
        
        while self.pos < len(self.data):
            b = self.data[self.pos]; self.pos += 1
            
            # Small positive int
            if 0x01 <= b <= 0x20:
                if self.current_obj:
                    self.current_obj['ivars'].append({'t': 'int', 'v': b})
            elif 0x21 <= b <= 0x7c:
                if self.current_obj:
                    self.current_obj['ivars'].append({'t': 'char', 'v': b})
            elif b == 0x7d: pass
            elif b == 0x81:
                v = self.data[self.pos]; self.pos += 1
                if self.current_obj:
                    self.current_obj['ivars'].append({'t': 'int', 'v': v})
            elif b == 0x82:
                v = struct.unpack_from('>h', self.data, self.pos)[0]; self.pos += 2
                if self.current_obj:
                    self.current_obj['ivars'].append({'t': 'short', 'v': v})
            elif b == 0x83:
                v = struct.unpack_from('>i', self.data, self.pos)[0]; self.pos += 4
                if self.current_obj:
                    self.current_obj['ivars'].append({'t': 'int32', 'v': v})
            elif b == 0x84:
                t = self.data[self.pos]; self.pos += 1
                if t == 0x01:  # int
                    val = self.ri()
                    if self.current_obj:
                        self.current_obj['ivars'].append({'t': 'tag_int', 'v': val})
                elif t == 0x05:  # array declaration follows: [Ntype]
                    decl = self.data[self.pos:self.pos+10]
                    end = decl.find(b']')
                    if end >= 0:
                        decl_str = decl[:end+1].decode('latin-1')
                        self.pos += end + 1
                        # Parse array size and type
                        sz = int(decl_str[1:-2])
                        elem_type = decl_str[-2]
                        raw_pos = self.pos
                        raw_end = raw_pos + sz
                        if raw_end <= len(self.data):
                            raw_data = self.data[raw_pos:raw_end]
                            self.pos = raw_end
                            parsed = None
                            # Check if raw data is a nested typedstream
                            if raw_data[:2] == b'\x04\x0b':
                                nested = TypedStream(raw_data, f"{self.name}.nested[{sz}c]")
                                nested.parse()
                                parsed = nested.objects
                            obj = {
                                't': 'data',
                                'decl': decl_str,
                                'size': sz,
                                'hex': raw_data[:min(32,sz)].hex() if not parsed else '',
                                'nested': parsed
                            }
                            if self.current_obj:
                                self.current_obj['ivars'].append(obj)
                elif t == 0x06:  # array (next byte is length)
                    pass
                elif t == 0x07:  # array (2 bytes length)
                    pass
                elif t == 0x08:  # int tag
                    if self.current_obj:
                        self.current_obj['ivars'].append({'t': 'tag_int', 'v': self.ri()})
                elif t == 0x25:  # string
                    s = self.rs()
                    if self.current_obj:
                        self.current_obj['ivars'].append({'t': 'string', 'v': s})
                elif t == 0x40:  # object start
                    self.push_obj({'t': 'obj', 'class': None, 'ivars': []})
                elif t == 0x84: pass  # continuation
                else:
                    if self.current_obj:
                        self.current_obj['ivars'].append({'t': f'tag_{t}', 'v': hex(t)})
            elif b == 0x85:  # reference
                ref = self.ri()
                if self.current_obj:
                    self.current_obj['ivars'].append({'t': 'ref', 'v': ref})
            elif b == 0x86:  # reference with class
                cls = self.rs()
                ref = self.ri()
                if self.current_obj:
                    self.current_obj['ivars'].append({'t': 'ref_class', 'cls': cls, 'v': ref})
            elif b == 0x88:
                if self.current_obj:
                    self.current_obj['ivars'].append({'t': 'nil'})
            elif b == 0x8c:  # byte array type
                arr_type = self.rs()
                if self.current_obj:
                    self.current_obj['ivars'].append({'t': 'array_type', 'type': arr_type})
            elif b == 0x92:  # reference
                ref = self.ri()
                if self.current_obj:
                    self.current_obj['ivars'].append({'t': 'ref', 'v': ref})
            elif b == 0x93:  # continue
                val = self.ri()
                if self.current_obj:
                    self.current_obj['ivars'].append({'t': 'cont', 'v': val})
            elif b == 0x94:  # class definition
                cls_name = self.rs()
                version = self.ri()
                # Push class definition as an object
                obj = {'t': 'class_def', 'class': cls_name, 'version': version, 'ivars': []}
                self.push_obj(obj)
            elif b == 0x95:  # object with ref
                ref = self.ri()
                self.push_obj({'t': 'obj_ref', 'ref': ref, 'ivars': []})
            elif b == 0x96:  # object ref
                ref = self.ri()
                if self.current_obj:
                    self.current_obj['ivars'].append({'t': 'obj_ref', 'v': ref})
            elif b == 0x97:
                t = self.data[self.pos]; self.pos += 1
                if t == 0x01:  # nil
                    if self.current_obj: self.current_obj['ivars'].append({'t': 'nil'})
                elif t == 0x02:  # YES
                    if self.current_obj: self.current_obj['ivars'].append({'t': 'bool', 'v': True})
                elif t == 0x03:  # NO
                    if self.current_obj: self.current_obj['ivars'].append({'t': 'bool', 'v': False})
                elif t == 0x04:  # nil
                    if self.current_obj: self.current_obj['ivars'].append({'t': 'nil'})
                elif t == 0x05:  # float
                    f = struct.unpack_from('>f', self.data, self.pos)[0]; self.pos += 4
                    if self.current_obj:
                        self.current_obj['ivars'].append({'t': 'float', 'v': f})
                elif t == 0x06:  # double
                    d = struct.unpack_from('>d', self.data, self.pos)[0]; self.pos += 8
                    if self.current_obj: self.current_obj['ivars'].append({'t': 'double', 'v': d})
                elif t == 0x0c:  # class name
                    s = self.rs()
                    if self.current_obj:
                        self.current_obj['ivars'].append({'t': 'class_name', 'v': s})
                elif t == 0x0e:  # selector
                    s = self.rs()
                    if self.current_obj:
                        self.current_obj['ivars'].append({'t': 'sel', 'v': s})
                elif t == 0x14:  # end of ivars
                    pass
                elif t == 0x16:  # int
                    val = self.ri()
                    if self.current_obj: self.current_obj['ivars'].append({'t': 'int', 'v': val})
                else:
                    if self.current_obj: self.current_obj['ivars'].append({'t': f'sub_{t}', 'v': hex(t)})
            elif b == 0x98:
                self.pop_obj()
            elif b == 0x99:
                self.pop_obj()
            elif b == 0x9c:
                if self.current_obj: self.current_obj['ivars'].append({'t': 'nil'})
            elif b == 0x9d:
                if self.current_obj: self.current_obj['ivars'].append({'t': 'nil'})
            elif b == 0xa2:
                val = self.ri()
                if self.current_obj: self.current_obj['ivars'].append({'t': 'ref', 'v': val})
            elif b == 0xa8:
                val = self.ri()
                if self.current_obj: self.current_obj['ivars'].append({'t': 'int', 'v': val})
            elif b == 0xac:
                val = self.ri()
                if self.current_obj: self.current_obj['ivars'].append({'t': 'int', 'v': val})
            elif b == 0x7e or b == 0x7f:
                pass
            elif b == 0x86: pass
            else:
                if self.current_obj:
                    self.current_obj['ivars'].append({'t': 'unk', 'v': hex(b)})

def parse_nib(path):
    with open(path, 'rb') as f:
        data = f.read()
    ts = TypedStream(data, os.path.basename(path))
    ts.parse()
    return ts.objects

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: parse_nib.py <input.nib> <output.json>")
        sys.exit(1)
    objs = parse_nib(sys.argv[1])
    with open(sys.argv[2], 'w') as f:
        json.dump(objs, f, indent=2, default=str)
    print(f"Parsed {len(objs)} objects -> {sys.argv[2]}")
