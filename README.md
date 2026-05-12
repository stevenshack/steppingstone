# steppingstone — NeXTSTEP-to-GNUstep Porting Pipeline

Decompile NeXTSTEP ObjC applications via Ghidra and transform the output into compilable GNUstep ObjC source.

## Pipeline

```
pipeline.sh path/to/NeXTSTEP/binary
```

| Step | Script | What it does |
|------|--------|-------------|
| 1 | *(inline)* | Detect architecture, extract i386 slice from fat binary |
| 2a | `dump_objc_metadata.py` | Parse `__OBJC` segment: class names, method names, IMP addresses |
| 2b | `dump_c_symbols.py` | Parse `LC_SYMTAB`: C function symbols (`_main`, `start`, etc.) |
| 3 | Ghidra + `DisableObjCAnalyzer.java` | Headless decompilation of all functions in the merged address list. ObjC1 analyzers disabled via pre-script to prevent crash on NeXTSTEP type encodings. |
| 4 | `dump_class_layout.py` | Extract class hierarchy, ivar layouts (offsets, names, types) |
| 5 | `build_sources.py` | Generate `.m`/`.h`/stubs/GNUmakefile from Ghidra decompiler output |
| 6 | `resolve_selectors.py` | Replace `func_0xADDR` with `objc_msgSend`, `PTR_s_*` with `@selector()` |
| 6b | `resolve_class_refs.py` | Replace `PTR_s_ClassName` with `[ClassName class]`, `PTR_s_sel` with `@selector(sel)` via `__cls_refs` and `__message_refs` |
| 6c | `fixup_decompile.py` | ObjC method signatures, ivar offset → name, `objc_msgSend` → `[receiver message]`, extract C functions from `@implementation` blocks |
| 7 | *(inline)* | Copy headers, stubs, makefile, Info.plist |
| 8 | `nib2gmodel.py` / `fixup_gmodel.py` | Convert nib files to Gorm-compatible gmodels |
| 8b | `extract_app_icon.py` | Extract app icon (`__TEXT/app` section → TIFF) |

### Transformations applied by Step 6c

| Before | After |
|--------|-------|
| `ID EnvelopeApp::appDidInit_(ID param_1,SEL param_2,ID param_3)` | `- (id)appDidInit:(id)sender` |
| `*(undefined1 *)(self + 0xd0) = 0` | `self->strFromField1 = 0` |
| `(*(code *)&SUB_0500387e)(receiver, @selector(setStringValue:), val)` | `[receiver setStringValue:val]` |
| `_main` wrapped in `@implementation EnvelopeMakerDecompiled` | `int main(int argc, const char *argv[])` standalone |
| `extern Class PTR_s_EnvelopeApp_000081d4` | `[EnvelopeApp class]` inline |

## Prerequisites

- JDK 25 (`apt install openjdk-25-jdk-headless`)
- Ghidra 12.0.4 extracted at `<repo_root>/ghidra/` (gitignored)
- `JAVA_HOME` set to `/usr/lib/jvm/java-25-openjdk-amd64`
- GNUstep development libraries (`libgnustep-gui-dev`, etc.)

## Program workspace

```
programs/<AppName>/
├── <AppName>          # Original NeXTSTEP binary (gitignored)
├── analysis/          # Pipeline output (.m, .h, stubs, gmodels, Info.plist, app bundle)
└── ported/            # Ported GNUstep application
```

## Data directory

NeXTSTEP binaries, nibs, and SDK headers are at `~/Code/nextdata/`:

| Directory | Contents |
|-----------|----------|
| `LocalApps/` | 42 NeXTSTEP applications |
| `NextDeveloper/` | Developer SDK: 2.0 headers, examples, demos |
| `NextLibrary/` | System library: fonts, documentation, sounds, colors |

Test nib files (EnvelopeMaker.nib, Info.nib) are in `~/Code/nextdata/LocalApps/EnvelopeMaker.app/`.

## Ghidra ObjC1 fix

The `ObjectiveC1_TypeEncodings.java` parser throws `UnsupportedOperationException` on NeXTSTEP type encoding characters (`%`, `!`, `}`, and unknown chars). The fix in `patches/fix_objc1_type_encodings.patch` returns `Undefined4DataType` or `VoidDataType` instead of throwing, and was compiled into `ghidra/Ghidra/Features/Base/lib/Base.jar` (original backed up as `Base.jar.orig`).

## Remaining gaps

- **Nested msgSend** — `[[self window] display]` not cleanly translated (parenthesization edge case)
- **SUB_ address resolution** — `SUB_0500301a` etc. need NeXTSTEP shared library symbol tables from `/lib` to map to real function names
- **Decompiler artifacts** — `halt_baddata()`, `CONCAT31`, `int3` etc. from Ghidra's m68k decompilation
- **Type encoding** — Ivar type strings not yet used to generate proper ObjC type signatures (all params show as `(id)`)

## Tests

```
python3 -m pytest tests/        # 17 Python tests
cd tests && make verify         # ObjC GNUstep archive round-trip test
```

## Pipeline architecture

```
┌─ Binary ─────────────────────────────┐
│  dump_objc_metadata.py  (ObjC methods)│
│  dump_c_symbols.py       (C symbols)  │
│  dump_class_layout.py   (ivars/types) │
└───────────────────────────────────────┘
                    │ merged address list
                    ▼
┌─ Ghidra ─────────────────────────────┐
│  analyzeHeadless                     │
│    -preScript DisableObjCAnalyzer    │
│    -postScript DecompileBatch        │
└───────────────────────────────────────┘
                    │ raw C decompilation
                    ▼
┌─ Post-processing ────────────────────┐
│  build_sources.py    → raw .m/.h     │
│  resolve_selectors   → @selector()   │
│  resolve_class_refs  → [ClassName]   │
│  fixup_decompile     → ObjC syntax   │
└───────────────────────────────────────┘
                    │ compilable .m
                    ▼
┌─ GNUstep ────────────────────────────┐
│  gcc + libgnustep-gui                │
│    → ported/AppName.app              │
└───────────────────────────────────────┘
```
