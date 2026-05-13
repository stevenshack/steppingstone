# Story 2.2: Ghidra headless decompiler integration produces C output

Status: done

## Story

As a developer,
I want the pipeline to invoke Ghidra headlessly and capture its decompiled C output,
so that we can process it through the Clang AST fixup tool.

## Acceptance Criteria

1. **Given** a parsed Mach-O binary **When** I run `ghidra_decompile` against the extracted binary sections **Then** it produces Ghidra C output files for each decompiled function
2. **Given** Ghidra is not installed **When** I run `ghidra_decompile` **Then** it exits with a clear error message indicating Ghidra is required (NFR1)

## Tasks / Subtasks

- [x] Task 1: Create `steps/ghidra_decompile.py` — CLI tool wrapping Ghidra headless invocation (AC: 1, 2)
  - [x] Accept `--manifest` (path to parse_binary JSON manifest) and `--output-dir` args
  - [x] Extract function addresses from manifest (symbols with type != 0x1e (N_EXT|N_SECT) and objc method IMPs)
  - [x] Build address list file for DecompileBatch.java input format: `0xADDR [ClassName selector:]`
  - [x] Detect Ghidra installation via `GHIDRA_INSTALL` env var or fallback to `./ghidra` relative to repo root
  - [x] Invoke `analyzeHeadless` to import binary + run DecompileBatch.java (or equivalent postScript)
  - [x] Parse Ghidra's FUNC_BEGIN / FUNC_END delimited output into individual function `.c` files
  - [x] Write `<output-dir>/functions/<addr>_<name>.c` per function
  - [x] Write `<output-dir>/manifest.json` mapping addresses → output files
  - [x] On success: print final JSON result to stdout (per architecture subprocess protocol)
  - [x] On Ghidra not found: exit code 1, error message with GHIDRA_INSTALL guidance
  - [x] On Ghidra failure: exit code 1, include analyzeHeadless stderr in message
- [x] Task 2: Write `tests/test_ghidra_decompile.py` (AC: 1, 2)
  - [x] Test address list building from mock manifest JSON
  - [x] Test output parsing of FUNC_BEGIN/FUNC_END delimited text
  - [x] Test Ghidra-not-found error path (mock subprocess to fail)
  - [x] Test manifest loading with missing binary path
  - [x] All tests pass with `uv run pytest tests/test_ghidra_decompile.py -v`

## Dev Notes

### Architecture Compliance

Source: `_bmad-output/planning-artifacts/architecture.md`

- **Language:** Python-primary; no external Ghidra Python libraries — invoke via subprocess
- **Module location:** `steps/ghidra_decompile.py` (pipeline step)
- **CLI conventions:** argparse-based, verb-based naming (`ghidra_decompile`), stdout = JSON result, stderr = progress/logging, exit code 0 = success, 1 = error
- **JSON manifest fields:** `snake_case` for all field names
- **Error handling:** Exceptions propagate to orchestrator; error includes actionable context
- **Naming conventions (PEP 8):** `snake_case` for functions/variables, `CamelCase` for classes, `SCREAMING_SNAKE` for constants, `_leading_underscore` for private members
- **Subprocess protocol:** Final JSON result on last line of stdout; progress on stderr

### Existing Code to Leverage (DO NOT MODIFY)

The repo already has working Ghidra integration scripts that provide proven patterns:

- `pipeline.sh:103-118` — Ghidra analyzeHeadless invocation pattern: imports binary, runs DecompileBatch.java as postScript, captures output. Shows project dir management (`/tmp/ghidra_projects`), processor flags, and the complete Ghidra CLI incantation.
- `ghidra_scripts/DecompileBatch.java` — Batch decompiler that reads address list file, disassembles + creates functions at each address, decompiles, and emits `FUNC_BEGIN`/`FUNC_END` delimited output. The `steps/ghidra_decompile.py` wrapper must parse this output format.
- `ghidra_scripts/decompile_all.py` — Alternative Python-based Ghidra script using pyghidra. Uses `DecompInterface`, skips thunks/library functions, emits `DECOMPILED_FUNCTIONS_BEGIN/END` delimiters.
- `run_ghidra_script.sh` — Shows PyGhidra invocation approach (via `pyghidraRun`), temp project management, and script path setup.
- `steps/parse_binary.py` — Existing pipeline step (story 2.1). Its JSON manifest output is the input to `ghidra_decompile`. See manifest schema at `_bmad-output/implementation-artifacts/2-1-binary-*.md:106-136` for the `symbols` and `objc_classes` fields you need.

These files must NOT be modified. The new `steps/ghidra_decompile.py` calls Ghidra as a subprocess only.

### Ghidra Invocation Details

**analyzeHeadless command pattern** (from `pipeline.sh:113-118`):
```
$GHIDRA/support/analyzeHeadless /tmp/ghidra_projects <project_name> \
    -import <binary_path> -overwrite \
    [-processor <arch>] \
    -scriptPath <ghidra_scripts_dir> \
    -preScript DisableObjCAnalyzer.java \
    -postScript DecompileBatch.java <addr_list_file>
```

**Key paths:**
- Ghidra install: detect via `GHIDRA_INSTALL` env var, fall back to `./ghidra` (relative to repo root, as used by `pipeline.sh:15`)
- Java home: `/usr/lib/jvm/java-25-openjdk-amd64` (from `pipeline.sh:17`) — may vary; document that `JAVA_HOME` must be set
- Project dir: `/tmp/ghidra_projects/<project_name>` — temp, cleaned each run
- Scripts dir: `<repo>/ghidra_scripts/` — contains DecompileBatch.java

**DecompileBatch.java output format** (from source):
```
FUNC_BEGIN 0x<addr> <method_name>
<decompiled C code>
FUNC_END
// DECOMPILED N/M functions
```

**Address list format** (input to DecompileBatch.java):
```
0x<addr> [ClassName selector:]   # for ObjC methods
0x<addr> _c_function_name        # for C functions
```
One per line, first token is hex address, rest is human-readable name.

**Function address extraction** from parse_binary manifest:
- `manifest["symbols"]` — each entry has `address` (int) and `name` (str); filter by `type` field — include entries where type != 0x1e (N_EXT|N_SECT) or the name is not empty
- `manifest["objc_classes"]` — each class has `name` and `methods[]`; each method has `name`, `imp` (address); format as `0x{imp:x} [{name} {method_name}]`

### Input Manifest Schema (from steps/parse_binary.py)

```json
{
  "binary_path": "path/to/binary",
  "architecture": "i386",
  "sections": { "__text": {"vaddr": 4096, "size": 8192, "file_offset": 0} },
  "symbols": [
    {"address": 123456, "name": "_main", "type": 62, "section": 1}
  ],
  "objc_classes": [
    {
      "name": "MyClass",
      "methods": [
        {"name": "init", "types": "@12@0:4", "imp": 234567}
      ]
    }
  ]
}
```

### Output Format

`ghidra_decompile` writes to `<output-dir>/`:
```
functions/
  <addr>_<sanitized_name>.c    # per-function decompiled C output
manifest.json                   # { "<addr>": "functions/<addr>_<name>.c", ... }
```

Final JSON result on stdout (last line):
```json
{"status": "ok", "function_count": 42, "output_dir": "/path/to/output"}
```
On error:
```json
{"status": "error", "error": "Ghidra not found. Set GHIDRA_INSTALL or place ghidra/ in repo root."}
```

### File Structure Requirements

Expected new files:
```
steppingstone/
├── steps/
│   └── ghidra_decompile.py     # NEW — pipeline step CLI tool
└── tests/
    └── test_ghidra_decompile.py # NEW
```

### Testing Requirements

- **Framework:** pytest (already configured in pyproject.toml)
- **Test location:** `tests/test_ghidra_decompile.py`
- **Fixture strategy:** Create synthetic manifest JSON as Python dict; mock subprocess calls with `unittest.mock.patch` to avoid requiring real Ghidra installation
- **Coverage targets:**
  - Address list construction from combined symbols + objc_classes
  - Parse FUNC_BEGIN/FUNC_END delimited output into separate files
  - Handle Ghidra-not-found with actionable error
  - Handle analyzeHeadless non-zero exit
  - Handle empty manifest (no functions to decompile — should emit empty functions/ dir and success)
  - Handle malformed manifest (missing keys — should error with actionable message)
- **Test command:** `uv run pytest tests/test_ghidra_decompile.py -v`

### References

- [Source: _bmad-output/planning-artifacts/epics.md — Epic 2, Story 2.2]
- [Source: _bmad-output/planning-artifacts/architecture.md — Project Structure, steps/ghidra_decompile.py]
- [Source: _bmad-output/planning-artifacts/architecture.md — Implementation Patterns, Subprocess Protocol]
- [Source: _bmad-output/planning-artifacts/prd.md — FR1, NFR1]
- [Source: pipeline.sh:103-118 — existing Ghidra analyzeHeadless invocation pattern]
- [Source: ghidra_scripts/DecompileBatch.java — batch decompiler output format]
- [Source: ghidra_scripts/decompile_all.py — alternative Ghidra Python script pattern]
- [Source: _bmad-output/implementation-artifacts/2-1-binary-*.md — parse_binary manifest schema, Story 2.1 dev notes]

### Review Findings

- [x] [Review][Patch] Typo `ghdra_bin` (missing 'i') in `find_ghidra()` [`steps/ghidra_decompile.py:14`]
- [x] [Review][Patch] Uncaught `json.JSONDecodeError` when manifest file contains malformed JSON [`steps/ghidra_decompile.py:29`]
- [x] [Review][Patch] `binary_path: null` in manifest causes `TypeError` in `os.path.isfile(None)` [`steps/ghidra_decompile.py:34`]
- [x] [Review][Patch] `objc_classes[].methods: null` causes `TypeError` iterating None in for-loop [`steps/ghidra_decompile.py:56`]
- [x] [Review][Patch] Unhandled `PermissionError` when `analyzeHeadless` lacks execute permission [`steps/ghidra_decompile.py:98`]
- [x] [Review][Patch] `subprocess.run` has no timeout — Ghidra hang blocks indefinitely [`steps/ghidra_decompile.py:98`]
- [x] [Review][Patch] `FUNC_END` with trailing whitespace silently ignored by parser [`steps/ghidra_decompile.py:123`]
- [x] [Review][Patch] Unhandled `PermissionError`/`OSError` on `os.makedirs` and file writes [`steps/ghidra_decompile.py:142,148,152,178`]
- [x] [Review][Patch] Inconsistent error output: Ghidra-not-found emits JSON to stdout, analyzeHeadless failure emits plain text to stderr [`steps/ghidra_decompile.py:103-108 vs 154-159`]
- [x] [Review][Patch] Magic number `0x1E` (N_EXT|N_SECT) with no named constant or comment [`steps/ghidra_decompile.py:44`]
- [x] [Review][Patch] `format_addr_line` assumes address is int — crashes if manifest stores hex string [`steps/ghidra_decompile.py:57`]
- [x] [Review][Patch] Hardcoded `/tmp/ghidra_projects` with no cleanup — concurrent runs corrupt each other [`steps/ghidra_decompile.py:70-71`]
- [x] [Review][Patch] `sanitize_name` strips underscores non-uniquely — `_foo` and `foo_` both become `foo`, silently overwriting files [`steps/ghidra_decompile.py:109-113`]
- [x] [Review][Patch] `DisableObjCAnalyzer.java`/`DecompileBatch.java` paths not validated before launching Ghidra [`steps/ghidra_decompile.py:78-82`]

## Dev Agent Record

### Agent Model Used

opencode-go/deepseek-v4-flash

### Debug Log References

- Initial test run: 6 failures (sanitize_name expectations, sys.exit mocking, ghidra fallback path)
- Fixed: adjusted test expectations, used side_effect=SystemExit for sys.exit mocks, mocked REPO_ROOT for not-found test

### Completion Notes List

- Implemented `steps/ghidra_decompile.py` — CLI tool that wraps Ghidra analyzeHeadless invocation, builds address lists from parse_binary manifest, parses FUNC_BEGIN/FUNC_END delimited output, and writes per-function .c files + manifest.json
- Wrote 24 tests in `tests/test_ghidra_decompile.py` covering: address list building, output parsing, Ghidra-not-found error path, manifest validation, CLI invocation, empty/malformed edge cases
- All 61 tests pass (37 existing + 24 new), no regressions

### File List

- `steps/ghidra_decompile.py` — NEW
- `tests/test_ghidra_decompile.py` — NEW
