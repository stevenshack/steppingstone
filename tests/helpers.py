import struct
import tempfile
import os

from lib.binary_reader import (
    LC_SEGMENT,
    SEGMENT_BASE_SIZE,
    SECTION_SIZE,
    MACHO_HEADER_SIZE,
)


def build_minimal_macho(endian="<", extra_commands=None):
    e = endian
    nsects = 1
    sec_name = b"__text\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
    seg_name = b"__TEXT\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"

    section = sec_name + seg_name
    section += struct.pack(
        f"{e}IIIIIIIII", 4096, 8192, MACHO_HEADER_SIZE, 2, 0, 0, 0, 0, 0
    )

    cmdsize = SEGMENT_BASE_SIZE + nsects * SECTION_SIZE
    segment = struct.pack(f"{e}II", LC_SEGMENT, cmdsize)
    segment += b"__TEXT\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
    segment += struct.pack(
        f"{e}IIIIIIII", 4096, 65536, 0, 65536, 7, 5, nsects, 0
    )
    segment += section

    extra_data = b""
    total_ncmds = 1
    if extra_commands:
        for cmd_data in extra_commands:
            extra_data += cmd_data
            total_ncmds += 1

    sizeofcmds = cmdsize + len(extra_data)

    header = struct.pack(f"{e}I", 0xFEEDFACE)
    header += struct.pack(f"{e}IIIIII", 7, 3, 2, total_ncmds, sizeofcmds, 0)

    return header + segment + extra_data


def write_temp_binary(data):
    tmp = tempfile.NamedTemporaryFile(delete=False)
    tmp.write(data)
    tmp.close()
    return tmp.name
