# nextthunk — NeXTSTEP m68k Userland Emulator + Analysis Pipeline

Two independent projects live in this tree:

1. **`nextthunk.c`** — A self-contained m68k CPU emulator + Mach-O loader + NeXTSTEP system thunker that runs NeXTSTEP/m68k binaries on Linux.
2. **`analyze_app.sh`** — An analysis pipeline using Ghidra to extract ObjC metadata and function addresses from NeXTSTEP universal (m68k/i386) binaries.

---

## 1. nextthunk — m68k Emulator + Thunker

### Architecture

```
nextthunk.c (single file, ~700 lines C)
├── M68K CPU emulator (hand-written)
│   ├── 16-register CPU state (D0-D7, A0-A7, PC, SR)
│   ├── Instruction decoder for all major opcode categories (0-F)
│   ├── Memory: 16MB flat uint8_t array (mem[0x1000000])
│   └── Addressing modes: Dn, An, (An), (An)+, -(An), d16(An), d8(An,Xn), abs.W/L, PC-rel, imm
├── Mach-O loader
│   ├── Parses LC_SEGMENT, LC_SYMTAB, LC_UNIXTHREAD
│   ├── Loads __TEXT, __DATA, __OBJC segments into emulated memory
│   └── Supports both m68k (BE) and i386 (LE) via manual endian handling
├── Thunk system
│   ├── TRAP #15 = __dyld_func_lookup replacement
│   ├── TRAP #14 = native function call dispatch (printf, exit, write)
│   ├── Patches _main's BSR to point to local thunks
│   └── exit via longjmp back to main loop
└── Build: gcc -o nextthunk nextthunk.c
```

### How to use

```sh
cd /home/sshack/Code/nextthunk
./nextthunk hello
# → prints "hello world"
```

### Design decisions

- Entry point is set directly to `_main` (0x3E9A), bypassing the NeXTSTEP dyld startup.
- The BSR to `_printf` at 0x3EA4 is patched to JSR a local thunk at 0x7F0000.
- The thunk does `MOVEQ #0, D0; TRAP #14; RTS` — TRAP #14 invokes the host's `printf`.
- Exit is handled by pushing a thunk return address that calls `exit(0)` via TRAP #14 → `longjmp`.

### Known limitations

- Only tested with the included `hello` binary (a simple C program).
- The hand-written CPU core is incomplete — many instructions are stubbed with `c->halted = 1`.
- Replacing the core with Musashi is recommended for production use.
- Memory is a flat 16MB array; no paging or VM protection.

---

## 2. Ghidra Analysis Pipeline

### Purpose

Extract Objective-C class/method metadata and cross-reference it with Ghidra's function analysis from NeXTSTEP Mach-O binaries.

### Files

| File | Purpose |
|------|---------|
| `analyze_app.sh` | Main pipeline script — extract i386, run ObjC dumper, run Ghidra, merge |
| `dump_objc_metadata.py` | Standalone Python ObjC metadata extractor (no Ghidra dependency) |
| `extract_i386.sh` | Extract i386 slice from universal fat binary |
| `ghidra_scripts/DumpFunctions.java` | Ghidra Java script — list all function addresses and names |
| `ghidra_scripts/DecompileToObjC.java` | Ghidra Java script — decompile functions and annotate ObjC |
| `objcify_output.py` | Post-processor: convert Ghidra decompiler output to ObjC method skeletons |

### Pipeline flow

```
analyze_app.sh LocalApps/WordPerfect.app/WordPerfect
  │
  ├─ Step 1: Extract i386 slice from universal fat binary
  │   → WordPerfect.i386 (1.4MB)
  │
  ├─ Step 2: ObjC metadata (Python)
  │   dump_objc_metadata.py → analysis/objc_metadata.txt
  │     1185 methods found for WordPerfect
  │
  ├─ Step 3: Ghidra headless function analysis
  │   analyzeHeadless -import ... -postScript DumpFunctions.java
  │     → analysis/functions.txt
  │     4895 functions identified
  │
  └─ Step 4: Merge (Python)
      → analysis/annotated.txt
      → analysis/stats.txt
```

### Metadata format

```
analysis/
├── objc_metadata.txt   # Raw ObjC: 0x0046b0 [setPage:]
├── functions.txt       # Ghidra:   0x0046b0 setPage:
├── annotated.txt       # Merged:   0x0046b0 [setPage:]  or 0x05dba4 appDidInit:  // ObjC: [appDidInit:]
└── stats.txt           # Summary counts
```

### The dump_objc_metadata.py design

Parses the NeXTSTEP ObjC runtime structures directly from the Mach-O binary:

1. Reads `__OBJC` segment sections from the Mach-O load commands
2. Finds `__class` section → iterates 40-byte `class_t` entries
3. For each class, reads `method_list` pointer field (offset +28)
4. Follows the method list chain (`{next_ptr, count, methods[]}`)
5. Resolves method names via `__meth_var_names` section

Handles both big-endian (m68k) and little-endian (i386) binaries.

### Ghidra ObjC Analyzer Issue

NeXTSTEP uses an older ObjC1 runtime format. Ghidra's built-in `ObjectiveC1_ClassAnalyzer` crashes during auto-analysis because its `ObjectiveC1_TypeEncodings.java` throws `UnsupportedOperationException` on `}` characters in type encodings.

**Attempted fix:** Patched the compiled `.class` file to return `null` instead of throwing. This suppressed the first crash but triggered cascading `NullPointerException` in `ObjectiveC1_Utilities.java` which doesn't null-check the return value. Reverted.

**To properly fix:** Clone the Ghidra source, modify `ObjectiveC1_TypeEncodings.java` to return a default DataType (e.g., `UndefinedDataType`) instead of throwing, add null-check in `ObjectiveC1_Utilities.java`, rebuild, and deploy.

### Decompiler limitation

Even with full Ghidra analysis, the decompiler produces empty bodies for most functions. This is because NeXTSTEP binaries use prebinding — many functions are just JMP stubs into the shared library (`libNeXT_s.C.shlib`). Custom methods implemented in the binary itself DO have real code at their addresses, visible in the disassembly view.

---

## 3. Running the pipeline

### Prerequisites

- JDK 25 installed (`apt install openjdk-25-jdk-headless`)
- Ghidra 12.0.4 extracted at `<repo_root>/ghidra/` (gitignored)
- `JAVA_HOME` set in the scripts (currently points to `/usr/lib/jvm/java-25-openjdk-amd64`)

### Program workspace structure

Each program being ported has its own directory under `programs/<AppName>/`:

```
programs/EnvelopeMaker/
├── EnvelopeMaker          # Original NeXTSTEP m68k binary
├── analysis/              # Pipeline output (decompiled source, class layouts, stubs)
└── ported/                # Ported GNUstep application

### Usage

```sh
# Full analysis
./analyze_app.sh LocalApps/WordPerfect.app/WordPerfect
# Output in LocalApps/WordPerfect.app/analysis/

# ObjC metadata only (fast, no Ghidra needed)
python3 dump_objc_metadata.py path/to/binary.i386 output_dir/

# Ghidra function listing only
JAVA_HOME=/usr/lib/jvm/java-25-openjdk-amd64 \
  ghidra/support/analyzeHeadless \
  /tmp/ghidra_projects MyProject \
  -import binary.i386 -overwrite \
  -scriptPath ghidra_scripts \
  -postScript DumpFunctions.java

# Extract i386 slice only
./extract_i386.sh path/to/universal/binary
```

---

## 4. Test results: WordPerfect.app

| Metric | Count |
|--------|-------|
| Binary size | 1.4 MB (i386 slice) |
| Ghidra functions identified | 4,895 |
| ObjC class names | ~150 classes |
| ObjC method names | 1,185 |
| Methods implemented in binary | 1,185 (all in __TEXT range) |

---

## 6. Data Directory

NeXTSTEP binaries, nibs, and SDK headers are at `~/Code/nextdata/`:

| Directory | Contents |
|-----------|----------|
| `LocalApps/` | 42 NeXTSTEP applications (EnvelopeMaker.app, Create.app, etc.) |
| `NextDeveloper/` | Developer SDK: 2.0 headers, example code, demos |
| `NextLibrary/` | System library: fonts, documentation, sounds, colors |

The test nib files (EnvelopeMaker.nib, Info.nib) are in `~/Code/nextdata/LocalApps/EnvelopeMaker.app/`.

## 5. Next steps for future work

### Short term
- Fix the Ghidra ObjC analyzer properly by rebuilding from source
- Use PyGhidra for scripting instead of Java (more maintainable)
- Add decompiler output for specific custom methods (not shared library stubs)

### Medium term
- Drop Musashi into `nextthunk.c` to replace the hand-written CPU core
- Implement `__dyld_func_lookup` properly — run the real startup code
- Add ~30 Mach trap stubs to support basic Foundation calls
- Route `objc_msgSend` → GNUstep for ObjC method dispatch

### Long term
- Full `objc_msgSend` trampoline: unpack m68k args, translate to GNUstep ABI
- Nib loading support: convert NeXTSTEP nib format to GNUstep-compatible
- Display PostScript → GNUstep drawing backend
- Port the Mach-O loader to use Musashi's memory callbacks instead of the flat array

### Architecture for GNUstep bridge

```
nextthunk (Musashi + Mach-O loader)
  │
  ├─ m68k CPU (Musashi)
  ├─ Paged memory (mmap-backed)
  ├─ Mach trap stubs (~30)
  ├─ __dyld_func_lookup provider
  │
  └─ objc_msgSend trampoline
       ├─ reads receiver/selector/args from m68k stack
       ├─ translates to native calling convention
       ├─ calls GNUstep runtime
       └─ returns result to m68k registers
```

The GNUstep bridge is the hardest part — NeXTSTEP's ObjC ABI differs from modern GNUstep (4-byte pointers, different `class_t`/`method_t` layouts, different `objc_msgSend` calling convention). Each message send needs marshalling.
