#!/usr/bin/env python3
"""Extract class hierarchy, ivar layout, and method-to-class mapping
from NeXTSTEP Mach-O (m68k BE or i386 LE). Outputs JSON for the pipeline."""

import struct, sys, os, json

def parse_binary(binpath):
    with open(binpath, "rb") as f:
        data = f.read()

    magic = struct.unpack_from("<I", data, 0)[0]
    if magic == 0xFEEDFACE:
        e = "<"
    elif magic == 0xCEFAEDFE:
        e = ">"
    else:
        print(f"Not Mach-O: magic=0x{magic:08x}", file=sys.stderr)
        return None

    ncmds = struct.unpack_from(f"{e}I", data, 16)[0]
    off = 28
    secs = {}
    for _ in range(ncmds):
        cmd = struct.unpack_from(f"{e}I", data, off)[0]
        cmdsize = struct.unpack_from(f"{e}I", data, off+4)[0]
        if cmd == 1:
            nsects = struct.unpack_from(f"{e}I", data, off+48)[0]
            so = off + 56
            for _ in range(nsects):
                sname = data[so:so+16].rstrip(b"\x00").decode("latin-1")
                saddr = struct.unpack_from(f"{e}I", data, so+32)[0]
                ssize = struct.unpack_from(f"{e}I", data, so+36)[0]
                sfoff = struct.unpack_from(f"{e}I", data, so+40)[0]
                secs[sname] = (saddr, ssize, sfoff)
                so += 68
        off += cmdsize

    def vm2f(vm):
        for sname, (sa, ss, sf) in secs.items():
            if sf and sa <= vm < sa + ss:
                return sf + (vm - sa)
        return 0

    def rd32(off):
        return struct.unpack_from(f"{e}I", data, off)[0]

    def rd_str(vm):
        foff = vm2f(vm)
        if not foff:
            return None
        end = foff
        while end < len(data) and data[end] != 0:
            end += 1
        return data[foff:end].decode("latin-1", errors="replace")

    # Read class name strings from __class_names
    class_names = {}
    if "__class_names" in secs:
        ca, cs, cf = secs["__class_names"]
        pos = cf
        end = cf + cs
        while pos < end:
            null = data.index(b"\x00", pos) if b"\x00" in data[pos:end] else end
            name = data[pos:null].decode("latin-1", errors="replace")
            class_names[ca + (pos - cf)] = name
            pos = null + 1

    # Read selector strings from __meth_var_names
    selectors = {}
    if "__meth_var_names" in secs:
        sa, ss, sf = secs["__meth_var_names"]
        pos = sf
        end = sf + ss
        while pos < end:
            null = data.index(b"\x00", pos) if b"\x00" in data[pos:end] else end
            name = data[pos:null].decode("latin-1", errors="replace")
            selectors[sa + (pos - sf)] = name
            pos = null + 1

    def read_method_list(vm, seen=None):
        if seen is None: seen = set()
        methods = []
        while vm and vm not in seen:
            seen.add(vm)
            mf = vm2f(vm)
            if not mf or mf + 8 > len(data):
                break
            mnext = rd32(mf)
            mcnt = rd32(mf + 4)
            if mcnt < 0 or mcnt > 500000:
                break
            for i in range(mcnt):
                moff = mf + 8 + i * 12
                if moff + 12 > len(data):
                    break
                mn = rd32(moff)       # selector name pointer
                imp = rd32(moff + 8)  # method IMP
                name = selectors.get(mn, "?")
                if name:
                    methods.append((imp, name))
            vm = mnext
        return methods

    # Read __class section: 40-byte entries per class
    classes = []
    imp_to_class = {}
    class_for_offset = {}

    if "__class" in secs:
        ca, cs, cf = secs["__class"]
        nclasses = cs // 40
        for ci in range(nclasses):
            coff = cf + ci * 40
            isa = rd32(coff)
            super_vm = rd32(coff + 4)
            name_vm = rd32(coff + 8)
            version = rd32(coff + 12)
            info = rd32(coff + 16)
            instance_size = rd32(coff + 20)
            ivars_vm = rd32(coff + 24)
            methods_vm = rd32(coff + 28)

            name = class_names.get(name_vm, "?")
            if name == "?":
                continue

            # Read ivars
            ivars = []
            if ivars_vm:
                ivf = vm2f(ivars_vm)
                if ivf and ivf + 4 <= len(data):
                    icount = rd32(ivf)
                    for i in range(icount):
                        ioff = ivf + 4 + i * 12
                        if ioff + 12 > len(data):
                            break
                        iname_vm = rd32(ioff)
                        itype_vm = rd32(ioff + 4)
                        ioffset = rd32(ioff + 8)
                        iname = rd_str(iname_vm) or "?"
                        itype = rd_str(itype_vm) or "?"
                        ivars.append({
                            'name': iname,
                            'type': itype,
                            'offset': ioffset,
                        })

            # Read methods for this class
            methods = read_method_list(methods_vm)

            classes.append({
                'name': name,
                'super_vm': super_vm,
                'instance_size': instance_size,
                'ivars': ivars,
                'methods': [{'imp': imp, 'name': sel} for imp, sel in methods],
            })

            for imp, sel in methods:
                imp_to_class[imp] = name

            offset_map = {}
            for iv in ivars:
                offset_map[iv['offset']] = iv['name']
            class_for_offset[name] = offset_map

    # Resolve superclass names
    # The super_vm points to the metaclass's class pointer.
    # The metaclass for class[i] is at __meta_class + i*40.
    # Metaclass super is at the same offset + 4.
    # The actual class pointer is at __class + i*40.
    class_by_super_vm = {}
    if "__meta_class" in secs:
        ma, ms, mf = secs["__meta_class"]
        for ci in range(len(classes)):
            mcoff = mf + ci * 40
            cls_vm = rd32(mcoff)
            class_by_super_vm[cls_vm] = classes[ci]['name']

    for cls in classes:
        super_name = class_by_super_vm.get(cls['super_vm'], "NSObject")
        cls['superclass'] = super_name

    return {
        'classes': classes,
        'imp_to_class': {str(k): v for k, v in imp_to_class.items()},
        'class_for_offset': class_for_offset,
    }


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <binary> [outdir]")
        sys.exit(1)

    binpath = sys.argv[1]
    outdir = sys.argv[2] if len(sys.argv) > 2 else os.path.dirname(binpath)
    os.makedirs(outdir, exist_ok=True)

    info = parse_binary(binpath)
    if not info:
        sys.exit(1)

    # Write JSON
    json_path = os.path.join(outdir, "class_info.json")
    with open(json_path, "w") as f:
        json.dump(info, f, indent=2)
    print(f"  {len(info['classes'])} classes -> {json_path}")

    # Write text summary
    txt_path = os.path.join(outdir, "class_layout.txt")
    with open(txt_path, "w") as f:
        f.write(f"// Class layout from {os.path.basename(binpath)}\n")
        f.write(f"// {len(info['classes'])} classes\n\n")
        for cls in info['classes']:
            f.write(f"@interface {cls['name']} : {cls['superclass']} {{\n")
            for iv in cls['ivars']:
                objc_t, arr_s = ghidra_type_to_objc(iv['type'])
                f.write(f"    {objc_t} {iv['name']}{arr_s};  // 0x{iv['offset']:03x}\n")
            f.write("}\n")
            for m in cls['methods']:
                f.write(f"  - (void){m['name']};\n")
            f.write("@end\n\n")
    print(f"  -> {txt_path}")

    # Write ObjC header
    h_path = os.path.join(outdir, "class_interfaces.h")
    with open(h_path, "w") as f:
        f.write("// Generated class interfaces\n")
        f.write("#import <Foundation/Foundation.h>\n\n")
        for cls in info['classes']:
            f.write(f"@interface {cls['name']} : {cls['superclass']} {{\n")
            f.write("  @public\n")
            for iv in cls['ivars']:
                objc_t, arr_s = ghidra_type_to_objc(iv['type'])
                f.write(f"    {objc_t} {iv['name']}{arr_s};\n")
            f.write("}\n")
            for m in cls['methods']:
                sig = m['name'].replace(':', ':(id)arg')
                if ':' in sig:
                    parts = sig.split(':arg')
                    sig = parts[0]
                    for i, p in enumerate(parts[1:], 1):
                        sig += f":(id)arg{i}"
                f.write(f"- (void){sig};\n")
            f.write("@end\n\n")
    print(f"  -> {h_path}")


def ghidra_type_to_objc(enc):
    """Convert ObjC type encoding to (base_type, array_suffix)."""
    if not enc: return ("id", "")
    m = {'@': 'id', '#': 'Class', ':': 'SEL', 'c': 'char', 'C': 'unsigned char',
         's': 'short', 'S': 'unsigned short', 'i': 'int', 'I': 'unsigned int',
         'l': 'long', 'L': 'unsigned long', 'q': 'long long', 'Q': 'unsigned long long',
         'f': 'float', 'd': 'double', 'B': 'BOOL', 'v': 'void', '*': 'char *',
         '?': 'void *', '%': 'void *'}
    if enc[0] in m: return (m[enc[0]], "")
    if enc[0] == '^':
        inner, _ = ghidra_type_to_objc(enc[1:])
        return (inner + " *", "")
    if enc[0] == '[':
        rest = enc[1:]
        num_end = 0
        while num_end < len(rest) and rest[num_end].isdigit():
            num_end += 1
        count = int(rest[:num_end]) if num_end > 0 else 0
        after = rest[num_end:]
        close = after.index(']') if ']' in after else len(after)
        inner, _ = ghidra_type_to_objc(after[:close])
        return (inner, f"[{count}]")
    if enc[0] == '{': return ("void *", "")
    return (enc, "")


if __name__ == "__main__":
    main()
