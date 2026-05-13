# Story 2.1: Binary parser extracts sections and metadata from a NeXTSTEP Mach-O file

Status: done

## Story

As a developer,
I want the binary parser to extract all sections, symbol tables, and ObjC metadata from an i386 Mach-O file,
so that downstream pipeline stages have the raw data they need to decompile.

## Acceptance Criteria

1. **Given** a valid i386 NeXTSTEP Mach-O binary **When** I run `parse_binary` against it **Then** it outputs a JSON manifest listing all load commands, segments, and sections
2. **Given** a Mach-O binary with an `__OBJC` segment **When** I run `parse_binary` **Then** the extracted metadata includes ObjC class names, method lists, and type encoding strings
3. **Given** a corrupted or non-Mach-O file **When** I run `parse_binary` **Then** it exits with a non-zero code and prints an actionable error message (NFR1)

## Tasks / Subtasks

- [x] Task 1: Implement `lib/binary_reader.py` — shared Mach-O parsing utilities (AC: 1, 2, 3)
  - [x] `read_macho_header(path)` — validates magic, returns endianness, returns header fields (cpu type, ncmds, etc.)
  - [x] `iter_load_commands(data, endian)` — generator yielding (cmd, cmdsize, offset) for each LC
  - [x] `index_sections(data, endian)` — returns dict mapping section name -> (vaddr, size, file_offset)
  - [x] Error: raise `MachOError` (or equivalent) with actionable message for bad magic, truncated file, etc.
- [x] Task 2: Implement `lib/type_encoding.py` — ObjC type encoding parser (AC: 2)
  - [x] `parse_type_encoding(encoded_str)` — parse ObjC type encoding string into structured representation
  - [x] `TypeEncoding` dataclass with fields for type specifiers, modifiers, and nested types
- [x] Task 3: Implement `steps/parse_binary.py` — the pipeline step CLI tool (AC: 1, 2, 3)
  - [x] CLI: accepts path to Mach-O binary, optional `--output-dir`, optional `--manifest-only` flag
  - [x] Extracts all load commands, segments, and sections into a JSON manifest
  - [x] Extracts LC_SYMTAB symbol table entries (nlist entries, string table)
  - [x] When `__OBJC` segment present: extracts ObjC class names, method lists (selector names, IMP addresses), type encoding strings
  - [x] Output manifest includes: `load_commands`, `segments`, `sections`, `symbols`, `objc_classes`
  - [x] On error: prints actionable message to stderr, exits code 1
  - [x] On success: prints final JSON result to stdout (per architecture subprocess protocol)
- [x] Task 4: Create `tests/test_parse_binary.py` and `tests/test_binary_reader.py` (AC: 1, 2, 3)
  - [x] Unit test for binary_reader: valid Mach-O header detection, endianness detection, section indexing, error cases
  - [x] Unit test for parse_binary: manifest JSON output has expected top-level keys
  - [x] Unit test: ObjC metadata extraction from mock __OBJC data
  - [x] Unit test: non-Mach-O file produces non-zero exit
  - [x] Fixtures: synthetic Mach-O binary (minimal valid header + sections) or use `tests/fixtures/minimal-app/`
  - [x] All tests pass with `uv run pytest tests/test_parse_binary.py tests/test_binary_reader.py`

## Dev Notes

### Architecture Compliance

Source: `_bmad-output/planning-artifacts/architecture.md`

- **Language:** Python-primary; no external libraries for Mach-O parsing (struct module only)
- **Module location:** `steps/parse_binary.py` (pipeline step), `lib/binary_reader.py` (shared), `lib/type_encoding.py` (shared)
- **CLI conventions:** argparse-based, verb-based naming (`parse_binary`), stdout = JSON result, stderr = progress/logging, exit code 0 = success, 1 = error
- **JSON manifest fields:** `snake_case` for all field names
- **Error handling:** Exceptions propagate to orchestrator; error includes actionable context: "file foo.macho: bad magic 0xXXXXXXXX"
- **Naming conventions (PEP 8):** `snake_case` for functions/variables, `CamelCase` for classes, `SCREAMING_SNAKE` for constants, `_leading_underscore` for private members
- **Subprocess protocol:** Final JSON result on last line of stdout; progress on stderr
- **Binary support:** i386 NeXTSTEP only (Fat binaries not handled; m68k not in Phase 1 scope)

### File Structure Requirements

Expected new/modified files:

```
steppingstone/
├── lib/
│   ├── binary_reader.py          # NEW — Mach-O header, LC iteration, section indexing, symbols
│   ├── type_encoding.py          # NEW — ObjC type encoding parser
│   └── __init__.py               # EXISTING — no change
├── steps/
│   ├── parse_binary.py           # NEW — pipeline step CLI tool
│   └── __init__.py               # EXISTING — no change
└── tests/
    ├── test_parse_binary.py      # NEW
    ├── test_binary_reader.py     # NEW
    └── fixtures/
        └── minimal-app/          # EXISTING — consider adding synthetic test fixture
```

### Existing Code to Leverage

The repo already has working Mach-O parsing scripts that provide proven implementation patterns:

- `dump_objc_metadata.py` — Mach-O magic detection (0xFEEDFACE LE/BE), load command iteration, section indexing, ObjC method list reading (__class, __meth_var_names, method list pointer chains). Uses `struct.unpack_from` with dynamic endianness.
- `dump_c_symbols.py` — LC_SYMTAB parsing, nlist entry reading, section-to-number mapping, string table extraction. Same struct patterns.

These scripts must NOT be deleted or modified. The new `lib/binary_reader.py` and `steps/parse_binary.py` are modular refactors of these patterns into the architecture-defined locations.

### Existing Files to Preserve

DO NOT delete, move, or modify existing files in the repo root — the standalone scripts (`dump_objc_metadata.py`, `dump_c_symbols.py`, etc.) are working tools. The new pipeline modules coexist alongside them.

### Technical Requirements

- **No external dependencies** for Mach-O parsing — use `struct` module only
- **Endianness:** i386 is little-endian; NeXTSTEP Mach-O magic = `0xFEEDFACE` (also check `0xFEEDFACF` for Fat, but reject Fat with actionable error since this story targets thin i386 only)
- **Load command constants:**
  - `LC_SEGMENT = 0x01` — segment with sections
  - `LC_SYMTAB = 0x02` — symbol table
  - `LC_THREAD / LC_UNIXTHREAD = 0x05 / 0x06` — entry point
- **Section struct (68 bytes each inside LC_SEGMENT):** sectname[16], segname[16], addr(4), size(4), offset(4), align(4), reloff(4), nreloc(4), flags(4), reserved(4)
- **Segment struct (56 bytes + section entries):** segname[16], vmaddr(4), vmsize(4), fileoff(4), filesize(4), maxprot(4), initprot(4), nsects(4), flags(4)
- **nlist struct (12 bytes):** n_strx(4), n_type(1), n_sect(1), n_desc(2), n_value(4)
- **ObjC method list:** each entry = 12 bytes: method_name(4), method_types(4), method_imp(4); method lists are linked via `obsolete` field at offset 0 (pointer to next list)
- **Type encodings** stored in `__meth_var_names` section (names) and inline in method list entries

### JSON Manifest Schema

```json
{
  "binary_path": "path/to/binary",
  "format": "mach-o",
  "architecture": "i386",
  "endian": "little",
  "load_commands": [
    {"cmd": 1, "cmdsize": 124, "description": "LC_SEGMENT", "segname": "__TEXT", "vmaddr": 4096, "vmsize": 65536, "fileoff": 0, "filesize": 65536}
  ],
  "segments": [
    {"name": "__TEXT", "vmaddr": 4096, "vmsize": 65536, "fileoff": 0, "filesize": 65536, "sections": ["__text", "__cstring", ...]}
  ],
  "sections": {
    "__text": {"vaddr": 4096, "size": 8192, "file_offset": 0},
    "__cstring": {"vaddr": 12288, "size": 512, "file_offset": 8192}
  },
  "symbols": [
    {"address": 123456, "name": "_main", "type": 62, "section": 1}
  ],
  "objc_classes": [
    {
      "name": "MyClass",
      "methods": [
        {"name": "init", "types": "@12@0:4", "imp": 234567},
        {"name": "myMethod:", "types": "v16@0:4@8", "imp": 234589}
      ]
    }
  ]
}
```

### Testing Requirements

- **Framework:** pytest (already configured in pyproject.toml)
- **Test location:** `tests/test_parse_binary.py`, `tests/test_binary_reader.py`
- **Fixture strategy:** Create a synthetic minimal i386 Mach-O binary as a Python bytes literal in tests (header + one LC_SEGMENT with __text section). This avoids needing real binaries checked in.
- **Coverage targets:**
  - Valid Mach-O header parsing
  - LC_SEGMENT and section iteration
  - LC_SYMTAB symbol extraction
  - ObjC metadata extraction (synthetic __OBJC data)
  - Non-Mach-O file rejection
  - Truncated/corrupted binary handling
- **Test command:** `uv run pytest tests/test_parse_binary.py tests/test_binary_reader.py -v`

### Review Findings

**Patch items (all fixed):**

- [x] [Review][Patch] Unused `sect_to_name` dict in `extract_symbols` [`lib/binary_reader.py:164-172`]
- [x] [Review][Patch] No bounds check on symtab offsets (`stroff`/`strsize`) before slicing [`lib/binary_reader.py:161-162`]
- [x] [Review][Patch] `rd32` factory lacks bounds check [`lib/binary_reader.py:254-258`]
- [x] [Review][Patch] `extract_objc_metadata` class loop lacks per-iteration bounds check [`lib/binary_reader.py:300-303`]
- [x] [Review][Patch] Unterminated `@"..."` raises unhandled ValueError [`lib/type_encoding.py:78`]
- [x] [Review][Patch] Pointer skip length calculation wrong in `parse_type_encoding` [`lib/type_encoding.py:111`]
- [x] [Review][Patch] Struct parsing drops all but first field [`lib/type_encoding.py:137`]
- [x] [Review][Patch] Array skip length calculation wrong in `parse_type_encoding` [`lib/type_encoding.py:148-149`]
- [x] [Review][Patch] Architecture hardcoded to `"i386"` regardless of actual cputype [`steps/parse_binary.py:36`]
- [x] [Review][Patch] `iter_load_commands` ignores `sizeofcmds` from header [`lib/binary_reader.py:46-56`]
- [x] [Review][Patch] Duplicate `_build_minimal_macho` helper across test files [`tests/test_binary_reader.py:39-55`, `tests/test_parse_binary.py:25-42`]
- [x] [Review][Patch] Test uses fragile undocumented magic offsets [`tests/test_binary_reader.py:194-195`]
- [x] [Review][Patch] Union handler doesn't recursively parse content [`lib/type_encoding.py:158-167`]
- [x] [Review][Patch] Struct specifier stores bracket char instead of normalized name [`lib/type_encoding.py:141`]
- [x] [Review][Patch] Missing `b` bit field type specifier [`lib/type_encoding.py:4-21`]
- [x] [Review][Patch] `_vm2f_factory` returns 0 as sentinel (0 is valid file offset) [`lib/binary_reader.py:247,286`]
- [x] [Review][Patch] No cap on `ncmds` (unbounded loop risk) [`lib/binary_reader.py:46-56`]
- [x] [Review][Patch] No cap on `nsects` + missing bounds check in `index_segments` [`lib/binary_reader.py:77-92,110-113`]
- [x] [Review][Patch] `_resolve_name_factory` can raise IndexError [`lib/binary_reader.py:268`]
- [x] [Review][Patch] Dead code: `mcnt < 0` always False (unsigned comparison) [`lib/binary_reader.py:290`]
- [x] [Review][Patch] Array encoding without digit raises unhandled ValueError [`lib/type_encoding.py:132`]
- [x] [Review][Patch] `manifest_only` parameter silently ignored [`steps/parse_binary.py:20`]
- [x] [Review][Patch] Directory passed as binary gives misleading "no such file" error [`steps/parse_binary.py:64-66`]
- [x] [Review][Patch] Fat binary magic `0xFEEDFACF` not detected/rejected with actionable message [`lib/binary_reader.py:41-51`]
- [x] [Review][Patch] Truncated-file errors lack file path in message [`lib/binary_reader.py:72,78,98`]
- [x] [Review][Patch] No positive test case for ObjC metadata extraction
- [x] [Review][Patch] `LC_THREAD`/`LC_UNIXTHREAD` not defined as constants [`lib/binary_reader.py:7`]
- [x] [Review][Patch] Empty modifier-only string silently returns empty list [`lib/type_encoding.py:68-69`]

**Deferred items:**

- [x] [Review][Defer] Recursion in `read_method_list` — unlikely in real NeXTSTEP binaries [`lib/binary_reader.py:249-274`]
- [x] [Review][Defer] No 32/64-bit check — spec says i386 only [`lib/binary_reader.py:1-321`]
- [x] [Review][Defer] `read_method_list` treats vm==0 as invalid — vm==0 extremely unlikely for method lists [`lib/binary_reader.py:249`]
- [x] [Review][Defer] Duplicate section names silently overwrite — won't happen in valid Mach-O [`lib/binary_reader.py:90`]
- [x] [Review][Defer] `type_encoding.py` not imported — module exists per spec, integration is future concern

### References

- [Source: _bmad-output/planning-artifacts/epics.md — Epic 2, Story 2.1]
- [Source: _bmad-output/planning-artifacts/architecture.md — Project Structure & Boundaries, Implementation Patterns]
- [Source: _bmad-output/planning-artifacts/prd.md — FR1, FR2, NFR1]
- [Source: dump_objc_metadata.py — existing Mach-O parsing patterns]
- [Source: dump_c_symbols.py — existing LC_SYMTAB parsing patterns]

## Dev Agent Record

### Agent Model Used

opencode-go/deepseek-v4-flash

### Debug Log References

- Fixed: struct.pack_into requires bytearray (test helper)
- Fixed: section struct needs 9 uint32 fields (36 bytes) after names, not 8
- Fixed: symbol test padding calculation accounted for file_base offset
- Fixed: Manifest sections converted from tuples to dicts for JSON schema compliance

### Completion Notes List

- Implemented lib/binary_reader.py with Mach-O header parsing, load command iteration, section/segment indexing, symbol table extraction, and ObjC metadata extraction
- Implemented lib/type_encoding.py with TypeEncoding dataclass and parse_type_encoding function supporting specifiers, modifiers, structs, arrays, unions, and pointers
- Implemented steps/parse_binary.py as argparse-based CLI tool producing JSON manifest per architecture subprocess protocol
- Created tests/test_binary_reader.py with 12 tests covering valid/bad/truncated/big-endian headers, load command iteration, section/segment indexing, symbol extraction with LC_SYMTAB, ObjC metadata, and error cases
- Created tests/test_parse_binary.py with 7 tests covering manifest structure, load commands, sections, segments, error handling, CLI exit codes, and CLI success path
- All 19 new tests + 17 existing tests pass (36 total)

### File List

- lib/binary_reader.py (NEW)
- lib/type_encoding.py (NEW)
- steps/parse_binary.py (NEW)
- tests/test_binary_reader.py (NEW)
- tests/test_parse_binary.py (NEW)
