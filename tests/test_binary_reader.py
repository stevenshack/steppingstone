import struct
import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.binary_reader import (
    read_macho_header,
    iter_load_commands,
    index_sections,
    index_segments,
    extract_symbols,
    extract_load_commands,
    extract_objc_metadata,
    MachOError,
    LC_SEGMENT,
    LC_SYMTAB,
    MAGIC_FEEDFACE,
    SEGMENT_BASE_SIZE,
    SECTION_SIZE,
    MACHO_HEADER_SIZE,
    NLIST_SIZE,
    OBJC_CLASS_SIZE,
)

from tests.helpers import build_minimal_macho, write_temp_binary


def test_read_macho_header_valid():
    raw = build_minimal_macho()
    path = write_temp_binary(raw)
    try:
        hdr = read_macho_header(path)
        assert hdr["magic"] == MAGIC_FEEDFACE
        assert hdr["endian"] == "<"
        assert hdr["cputype"] == 7
        assert hdr["cpusubtype"] == 3
        assert hdr["filetype"] == 2
        assert hdr["ncmds"] == 1
    finally:
        os.unlink(path)


def test_read_macho_header_bad_magic():
    raw = struct.pack("<I", 0xDEADBEEF) + b"\x00" * 24
    path = write_temp_binary(raw)
    try:
        with pytest.raises(MachOError, match="bad magic"):
            read_macho_header(path)
    finally:
        os.unlink(path)


def test_read_macho_header_truncated():
    path = write_temp_binary(b"\x00" * 10)
    try:
        with pytest.raises(MachOError, match="too small"):
            read_macho_header(path)
    finally:
        os.unlink(path)


def test_read_macho_header_big_endian():
    raw = build_minimal_macho(endian=">")
    path = write_temp_binary(raw)
    try:
        hdr = read_macho_header(path)
        assert hdr["magic"] == MAGIC_FEEDFACE
        assert hdr["endian"] == ">"
        assert hdr["cputype"] == 7
    finally:
        os.unlink(path)


def test_iter_load_commands():
    raw = build_minimal_macho()
    path = write_temp_binary(raw)
    try:
        hdr = read_macho_header(path)
        cmds = list(iter_load_commands(hdr["data"], hdr["endian"]))
        assert len(cmds) == 1
        cmd, cmdsize, offset = cmds[0]
        assert cmd == LC_SEGMENT
        assert cmdsize == SEGMENT_BASE_SIZE + 1 * SECTION_SIZE
        assert offset == MACHO_HEADER_SIZE
    finally:
        os.unlink(path)


def test_index_sections():
    raw = build_minimal_macho()
    path = write_temp_binary(raw)
    try:
        hdr = read_macho_header(path)
        secs = index_sections(hdr["data"], hdr["endian"])
        assert "__text" in secs
        vaddr, size, foff = secs["__text"]
        assert vaddr == 4096
        assert size == 8192
        assert foff == MACHO_HEADER_SIZE
    finally:
        os.unlink(path)


def test_index_segments():
    raw = build_minimal_macho()
    path = write_temp_binary(raw)
    try:
        hdr = read_macho_header(path)
        segs = index_segments(hdr["data"], hdr["endian"])
        assert len(segs) == 1
        assert segs[0]["name"] == "__TEXT"
        assert segs[0]["vmaddr"] == 4096
        assert segs[0]["sections"] == ["__text"]
    finally:
        os.unlink(path)


def test_extract_load_commands():
    raw = build_minimal_macho()
    path = write_temp_binary(raw)
    try:
        hdr = read_macho_header(path)
        cmds = extract_load_commands(hdr["data"], hdr["endian"])
        assert len(cmds) == 1
        assert cmds[0]["description"] == "LC_SEGMENT"
        assert cmds[0]["segname"] == "__TEXT"
    finally:
        os.unlink(path)


def test_extract_symbols_no_symtab():
    raw = build_minimal_macho()
    path = write_temp_binary(raw)
    try:
        hdr = read_macho_header(path)
        syms = extract_symbols(hdr["data"], hdr["endian"], {})
        assert syms == []
    finally:
        os.unlink(path)


def test_extract_symbols_with_symtab():
    e = "<"
    strtable = b"_main\x00_foo\x00"
    nsyms = 2
    nlist_size = nsyms * NLIST_SIZE
    symtab_cmd_size = 24

    segment_size = SEGMENT_BASE_SIZE + 1 * SECTION_SIZE
    file_base = MACHO_HEADER_SIZE + segment_size

    # Place symoff right after the symtab command + minimal padding
    symoff = file_base + symtab_cmd_size + 4
    # Place stroff after nlist entries + padding
    stroff = symoff + nlist_size + 4

    nlist_entries = struct.pack(
        f"{e}IBBhI",
        0, 0x0E, 1, 0, 0x123456,
    )
    nlist_entries += struct.pack(
        f"{e}IBBhI",
        6, 0x0E, 1, 0, 0x234567,
    )
    symtab_cmd = struct.pack(f"{e}II", LC_SYMTAB, symtab_cmd_size)
    symtab_cmd += struct.pack(f"{e}IIII", symoff, nsyms, stroff, len(strtable))

    pad1 = b"\x00" * (symoff - file_base - symtab_cmd_size)
    pad2 = b"\x00" * (stroff - symoff - nlist_size)

    extra_data = symtab_cmd + pad1 + nlist_entries + pad2 + strtable
    raw = build_minimal_macho(extra_commands=[extra_data])
    needed = stroff + len(strtable)
    if len(raw) < needed:
        raw += b"\x00" * (needed - len(raw))

    path = write_temp_binary(raw)
    try:
        hdr = read_macho_header(path)
        secs = index_sections(hdr["data"], hdr["endian"])
        syms = extract_symbols(hdr["data"], hdr["endian"], secs)
        symbol_names = [s["name"] for s in syms]
        assert "_main" in symbol_names, f"got {symbol_names}"
        assert "_foo" in symbol_names, f"got {symbol_names}"
    finally:
        os.unlink(path)


def test_extract_objc_metadata_no_objc():
    raw = build_minimal_macho()
    path = write_temp_binary(raw)
    try:
        hdr = read_macho_header(path)
        secs = index_sections(hdr["data"], hdr["endian"])
        classes = extract_objc_metadata(hdr["data"], hdr["endian"], secs)
        assert classes == []
    finally:
        os.unlink(path)


def test_extract_objc_metadata_with_objc():
    e = "<"

    cls_refs_vaddr = 0x1000
    meth_var_names_vaddr = 0x2000
    class_vaddr = 0x3000

    method_names = b"init\x00myMethod:\x00"
    cls_refs = b"MyClass\x00"

    class_size = OBJC_CLASS_SIZE
    method_list_offset_within_section = class_size
    method_list_vaddr = class_vaddr + method_list_offset_within_section

    method_list_header = struct.pack(f"{e}II", 0, 2)
    method_list_entries = struct.pack(
        f"{e}III", meth_var_names_vaddr, 0, 0x1234,
    )
    method_list_entries += struct.pack(
        f"{e}III", meth_var_names_vaddr + 5, 0, 0x5678,
    )
    method_list_data = method_list_header + method_list_entries

    class_data = (
        b"\x00" * 12
        + struct.pack(f"{e}I", cls_refs_vaddr)
        + b"\x00" * 12
        + struct.pack(f"{e}I", method_list_vaddr)
        + b"\x00" * 4
    )

    payload_offset = MACHO_HEADER_SIZE + SEGMENT_BASE_SIZE + 3 * SECTION_SIZE
    class_file_off = payload_offset + len(method_names) + len(cls_refs)

    def make_section(name, vmaddr, vmsize, fileoff):
        sec = name.ljust(16, b"\x00")
        segname = b"__OBJC\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
        sec += segname
        sec += struct.pack(
            f"{e}IIIIIIIII",
            vmaddr, vmsize, fileoff, 2, 0, 0, 0, 0, 0,
        )
        return sec

    class_section_size = class_size + len(method_list_data)
    sec_class = make_section(b"__class", class_vaddr, class_section_size, class_file_off)
    sec_mvn = make_section(b"__meth_var_names", meth_var_names_vaddr, len(method_names), payload_offset)
    sec_cr = make_section(b"__cls_refs", cls_refs_vaddr, len(cls_refs), payload_offset + len(method_names))

    nsects = 3
    cmdsize = SEGMENT_BASE_SIZE + nsects * SECTION_SIZE
    segname = b"__OBJC\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
    segment = struct.pack(f"{e}II", LC_SEGMENT, cmdsize)
    segment += segname
    segment += struct.pack(
        f"{e}IIIIIIII",
        0x1000, 0x4000, payload_offset,
        len(method_names) + len(cls_refs) + class_section_size,
        7, 5, nsects, 0,
    )
    segment += sec_class + sec_mvn + sec_cr

    header = struct.pack(f"{e}I", 0xFEEDFACE)
    header += struct.pack(f"{e}IIIIII", 7, 3, 2, 1, cmdsize, 0)

    segment_payload = method_names + cls_refs + class_data + method_list_data
    gap = b"\x00" * (payload_offset - MACHO_HEADER_SIZE - cmdsize)

    raw = header + segment + gap + segment_payload

    path = write_temp_binary(raw)
    try:
        hdr = read_macho_header(path)
        secs = index_sections(hdr["data"], hdr["endian"])
        classes = extract_objc_metadata(hdr["data"], hdr["endian"], secs)
        assert len(classes) > 0, f"expected objc classes, got {classes}"
    finally:
        os.unlink(path)


def test_macho_error_raises():
    with pytest.raises(MachOError):
        raise MachOError("test error")
