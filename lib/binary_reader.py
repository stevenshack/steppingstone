import struct

MAGIC_FEEDFACE = 0xFEEDFACE
MAGIC_FAT = 0xFEEDFACF
LC_SEGMENT = 0x01
LC_SYMTAB = 0x02
LC_THREAD = 0x05
LC_UNIXTHREAD = 0x06

SECTION_SIZE = 68
SEGMENT_BASE_SIZE = 56
NLIST_SIZE = 12
MACHO_HEADER_SIZE = 28

OBJC_METHOD_ENTRY_SIZE = 12
OBJC_CLASS_SIZE = 40
OBJC_METHOD_LIST_HEADER_SIZE = 8

MAX_NCMDS = 1024
MAX_NSECTS = 256


class MachOError(Exception):
    pass


def read_macho_header(path):
    with open(path, "rb") as f:
        data = f.read()

    if len(data) < MACHO_HEADER_SIZE:
        raise MachOError(f"{path}: file too small ({len(data)} bytes)")

    magic_le = struct.unpack_from("<I", data, 0)[0]
    if magic_le == MAGIC_FEEDFACE:
        endian = "<"
    elif magic_le == MAGIC_FAT:
        raise MachOError(
            f"{path}: fat binary (magic 0x{magic_le:08x}) is not supported, "
            "only thin i386 Mach-O is supported"
        )
    else:
        magic_be = struct.unpack_from(">I", data, 0)[0]
        if magic_be == MAGIC_FEEDFACE:
            endian = ">"
        elif magic_be == MAGIC_FAT:
            raise MachOError(
                f"{path}: fat binary (magic 0x{magic_be:08x}) is not supported, "
                "only thin i386 Mach-O is supported"
            )
        else:
            raise MachOError(
                f"{path}: bad magic 0x{magic_le:08x} (expected 0xFEEDFACE)"
            )

    magic = MAGIC_FEEDFACE
    cputype = struct.unpack_from(f"{endian}I", data, 4)[0]
    cpusubtype = struct.unpack_from(f"{endian}I", data, 8)[0]
    filetype = struct.unpack_from(f"{endian}I", data, 12)[0]
    ncmds = struct.unpack_from(f"{endian}I", data, 16)[0]
    sizeofcmds = struct.unpack_from(f"{endian}I", data, 20)[0]
    flags = struct.unpack_from(f"{endian}I", data, 24)[0]

    return {
        "data": data,
        "endian": endian,
        "magic": magic,
        "cputype": cputype,
        "cpusubtype": cpusubtype,
        "filetype": filetype,
        "ncmds": ncmds,
        "sizeofcmds": sizeofcmds,
        "flags": flags,
    }


def iter_load_commands(data, endian, path=""):
    ncmds = struct.unpack_from(f"{endian}I", data, 16)[0]
    offset = MACHO_HEADER_SIZE
    ncmds = min(ncmds, MAX_NCMDS)
    for _ in range(ncmds):
        if offset + 8 > len(data):
            raise MachOError(
                f"{path}: truncated file: load command header out of range"
            )
        cmd = struct.unpack_from(f"{endian}I", data, offset)[0]
        cmdsize = struct.unpack_from(f"{endian}I", data, offset + 4)[0]
        if cmdsize < 8 or offset + cmdsize > len(data):
            raise MachOError(
                f"{path}: truncated file: load command at offset {offset} "
                f"has invalid cmdsize {cmdsize}"
            )
        yield cmd, cmdsize, offset
        offset += cmdsize


def index_sections(data, endian):
    sections = {}
    for cmd, cmdsize, offset in iter_load_commands(data, endian):
        if cmd == LC_SEGMENT:
            nsects = struct.unpack_from(f"{endian}I", data, offset + 48)[0]
            nsects = min(nsects, MAX_NSECTS)
            so = offset + SEGMENT_BASE_SIZE
            for _ in range(nsects):
                if so + SECTION_SIZE > len(data):
                    raise MachOError("truncated file: section header out of range")
                sname = data[so : so + 16].rstrip(b"\x00").decode("latin-1")
                saddr = struct.unpack_from(f"{endian}I", data, so + 32)[0]
                ssize = struct.unpack_from(f"{endian}I", data, so + 36)[0]
                sfoff = struct.unpack_from(f"{endian}I", data, so + 40)[0]
                sections[sname] = (saddr, ssize, sfoff)
                so += SECTION_SIZE
    return sections


def index_segments(data, endian):
    segments = []
    for cmd, cmdsize, offset in iter_load_commands(data, endian):
        if cmd == LC_SEGMENT:
            segname = data[offset + 8 : offset + 24].rstrip(b"\x00").decode("latin-1")
            vmaddr = struct.unpack_from(f"{endian}I", data, offset + 24)[0]
            vmsize = struct.unpack_from(f"{endian}I", data, offset + 28)[0]
            fileoff = struct.unpack_from(f"{endian}I", data, offset + 32)[0]
            filesize = struct.unpack_from(f"{endian}I", data, offset + 36)[0]
            maxprot = struct.unpack_from(f"{endian}I", data, offset + 40)[0]
            initprot = struct.unpack_from(f"{endian}I", data, offset + 44)[0]
            nsects = struct.unpack_from(f"{endian}I", data, offset + 48)[0]
            nsects = min(nsects, MAX_NSECTS)
            flags = struct.unpack_from(f"{endian}I", data, offset + 52)[0]
            section_names = []
            so = offset + SEGMENT_BASE_SIZE
            for _ in range(nsects):
                if so + SECTION_SIZE > len(data):
                    raise MachOError("truncated file: section header out of range")
                sname = data[so : so + 16].rstrip(b"\x00").decode("latin-1")
                section_names.append(sname)
                so += SECTION_SIZE
            segments.append(
                {
                    "name": segname,
                    "vmaddr": vmaddr,
                    "vmsize": vmsize,
                    "fileoff": fileoff,
                    "filesize": filesize,
                    "maxprot": maxprot,
                    "initprot": initprot,
                    "nsects": nsects,
                    "flags": flags,
                    "sections": section_names,
                }
            )
    return segments


def iter_load_commands_json(data, endian):
    commands = []
    for cmd, cmdsize, offset in iter_load_commands(data, endian):
        if cmd == LC_SEGMENT:
            segname = data[offset + 8 : offset + 24].rstrip(b"\x00").decode("latin-1")
            vmaddr = struct.unpack_from(f"{endian}I", data, offset + 24)[0]
            vmsize = struct.unpack_from(f"{endian}I", data, offset + 28)[0]
            fileoff = struct.unpack_from(f"{endian}I", data, offset + 32)[0]
            filesize = struct.unpack_from(f"{endian}I", data, offset + 36)[0]
            nsects = struct.unpack_from(f"{endian}I", data, offset + 48)[0]
            commands.append(
                {
                    "cmd": cmd,
                    "cmdsize": cmdsize,
                    "description": "LC_SEGMENT",
                    "segname": segname,
                    "vmaddr": vmaddr,
                    "vmsize": vmsize,
                    "fileoff": fileoff,
                    "filesize": filesize,
                    "nsects": nsects,
                }
            )
        elif cmd == LC_SYMTAB:
            symoff = struct.unpack_from(f"{endian}I", data, offset + 8)[0]
            nsyms = struct.unpack_from(f"{endian}I", data, offset + 12)[0]
            stroff = struct.unpack_from(f"{endian}I", data, offset + 16)[0]
            strsize = struct.unpack_from(f"{endian}I", data, offset + 20)[0]
            commands.append(
                {
                    "cmd": cmd,
                    "cmdsize": cmdsize,
                    "description": "LC_SYMTAB",
                    "symoff": symoff,
                    "nsyms": nsyms,
                    "stroff": stroff,
                    "strsize": strsize,
                }
            )
        elif cmd == LC_THREAD:
            commands.append(
                {
                    "cmd": cmd,
                    "cmdsize": cmdsize,
                    "description": "LC_THREAD",
                }
            )
        elif cmd == LC_UNIXTHREAD:
            commands.append(
                {
                    "cmd": cmd,
                    "cmdsize": cmdsize,
                    "description": "LC_UNIXTHREAD",
                }
            )
        else:
            desc = f"LC_0x{cmd:02x}"
            commands.append(
                {
                    "cmd": cmd,
                    "cmdsize": cmdsize,
                    "description": desc,
                }
            )
    return commands


def extract_load_commands(data, endian):
    return list(iter_load_commands_json(data, endian))


def extract_symbols(data, endian, sections):
    symtab = None
    for cmd, cmdsize, offset in iter_load_commands(data, endian):
        if cmd == LC_SYMTAB:
            symoff = struct.unpack_from(f"{endian}I", data, offset + 8)[0]
            nsyms = struct.unpack_from(f"{endian}I", data, offset + 12)[0]
            stroff = struct.unpack_from(f"{endian}I", data, offset + 16)[0]
            strsize = struct.unpack_from(f"{endian}I", data, offset + 20)[0]
            symtab = (symoff, nsyms, stroff, strsize)
            break

    if symtab is None:
        return []

    symoff, nsyms, stroff, strsize = symtab

    if stroff + strsize > len(data):
        stroff = min(stroff, len(data))
        strsize = min(strsize, len(data) - stroff)
    strtable = data[stroff : stroff + strsize]
    symbols = []

    for i in range(nsyms):
        entry_off = symoff + i * NLIST_SIZE
        if entry_off + NLIST_SIZE > len(data):
            break
        n_strx = struct.unpack_from(f"{endian}I", data, entry_off)[0]
        n_type = struct.unpack_from(f"{endian}B", data, entry_off + 4)[0]
        n_sect = struct.unpack_from(f"{endian}B", data, entry_off + 5)[0]
        n_value = struct.unpack_from(f"{endian}I", data, entry_off + 8)[0]

        sym_name = ""
        if n_strx < len(strtable):
            end = strtable.find(b"\x00", n_strx)
            if end == -1:
                end = len(strtable)
            sym_name = strtable[n_strx:end].decode("latin-1", errors="replace")

        symbols.append(
            {
                "address": n_value,
                "name": sym_name,
                "type": n_type,
                "section": n_sect,
            }
        )

    return symbols


def _vm2f_factory(sections):
    def vm2f(vm):
        for sname, (sa, ss, sf) in sections.items():
            if sf and sa <= vm < sa + ss:
                return sf + (vm - sa)
        return None

    return vm2f


def _rd32_factory(data, endian):
    def rd32(off):
        if off + 4 > len(data):
            raise MachOError(f"truncated file: cannot read 4 bytes at offset {off}")
        return struct.unpack_from(f"{endian}I", data, off)[0]

    return rd32


def _resolve_name_factory(data, sections):
    def resolve_name(vm, sec_name):
        if sec_name in sections:
            sa, ss, sf = sections[sec_name]
            if sa <= vm < sa + ss:
                nf = sf + (vm - sa)
                end = nf
                data_len = len(data)
                limit = min(sf + ss, data_len)
                while end < limit and data[end] != 0:
                    end += 1
                return data[nf:end].decode("latin-1", errors="replace")
        return "?"

    return resolve_name


def extract_objc_metadata(data, endian, sections):
    vm2f = _vm2f_factory(sections)
    rd32 = _rd32_factory(data, endian)
    resolve_name = _resolve_name_factory(data, sections)

    def read_method_list(vm, seen):
        if vm in seen or not vm:
            return []
        seen.add(vm)
        mf = vm2f(vm)
        if mf is None or mf + OBJC_METHOD_LIST_HEADER_SIZE > len(data):
            return []
        mnext = rd32(mf)
        mcnt = rd32(mf + 4)
        if mcnt > 500000:
            return []
        methods = []
        for i in range(mcnt):
            moff = mf + OBJC_METHOD_LIST_HEADER_SIZE + i * OBJC_METHOD_ENTRY_SIZE
            if moff + OBJC_METHOD_ENTRY_SIZE > len(data):
                break
            mn = rd32(moff)
            mt = rd32(moff + 4)
            imp = rd32(moff + 8)
            name = resolve_name(mn, "__meth_var_names")
            types = resolve_name(mt, "__meth_var_types") if mt else ""
            methods.append({"name": name, "types": types, "imp": imp})
        if mnext:
            methods.extend(read_method_list(mnext, seen))
        return methods

    classes = []
    if "__class" in sections:
        ca, cs, cf = sections["__class"]
        data_len = len(data)
        for ci in range(cs // OBJC_CLASS_SIZE):
            coff = cf + ci * OBJC_CLASS_SIZE
            if coff + OBJC_CLASS_SIZE > data_len:
                break
            class_name_vm = rd32(coff + 12)
            ml_vm = rd32(coff + 28)
            class_name = resolve_name(class_name_vm, "__cls_refs")
            if not class_name or class_name == "?":
                class_name = resolve_name(class_name_vm, "__class")
            methods = read_method_list(ml_vm, set())
            if methods or class_name != "?":
                classes.append({"name": class_name, "methods": methods})

    return classes
