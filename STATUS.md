# Pipeline Status

## Data Directory

NeXTSTEP application binaries, nib files, and SDK headers are at `~/Code/nextdata/`:

| Directory | Contents |
|-----------|----------|
| `LocalApps/` | 42 NeXTSTEP applications (EnvelopeMaker, Create, Diagram, FrameMaker, etc.) |
| `NextDeveloper/` | SDK: headers, examples, demos, palettes, source |
| `NextLibrary/` | System: fonts, adaptors, documentation, sounds, colors, keyboards |

Test nib files are in `~/Code/nextdata/LocalApps/EnvelopeMaker.app/` (EnvelopeMaker.nib, Info.nib).

## What Works

### Ghidra Integration
- Ghidra 12.0.4 installed at `<repo_root>/ghidra/` (gitignored)
- ObjC1 analyzer crash fixed: `ObjectiveC1_TypeEncodings.java` patched to return `Undefined4DataType` instead of throwing on `%`, `!`, `}`, and unknown type encoding chars
- `DisableObjCAnalyzer.java` pre-script available as fallback
- Full Ghidra auto-analysis enabled (removed `-noanalysis`)

### Pipeline Flow (`./pipeline.sh path/to/binary`)

1. **Architecture detection** — auto-detects i386 LE vs m68k BE Mach-O
2. **ObjC metadata dump** — method names + IMP addresses from `__OBJC` segment
3. **C symbol extraction** — `_main`, `start`, and other C functions from `LC_SYMTAB`
4. **Ghidra batch decompilation** — decompiles ObjC methods + C functions via headless Ghidra with ObjC1 analyzer disabled
5. **Class layout extraction** — class hierarchy, ivar names/types/offsets from `__class`
6. **Source generation** — ObjC `.m`/`.h` with class routing
7. **Selector resolution** — `PTR_s_*` -> `@selector()`
8. **Class reference resolution** — `PTR_s_ClassName` -> `[ClassName class]` via `__cls_refs` and `__message_refs`
9. **Decompilation fixup**:
   - Method signatures: `ID Class::method_()` → `- (id)methodName:(id)sender`
   - Ivar names: `*(id *)(self + 0xNN)` → `self->ivarName`
   - msgSend calls: `(*(code *)&SUB_XXX)(r, @selector(m:), a)` → `[r m:a]`
   - C functions: extracted from `@implementation` blocks, `_main` → `int main()`
10. **App icon extraction** — `__TEXT/app` section (TIFF) extracted to analysis/ and app bundle
11. **Nib → gmodel conversion** — preservation and runtime gmodels
12. **App bundle creation** — `.app` directory with binary, Info.plist, gmodels, icon

### Binary Decompilation (EnvelopeMaker)
- 17 functions decompiled (16 ObjC methods + `_main`)
- All ivar offsets replaced with named access (21 ivars across 2 classes)
- All `objc_msgSend` calls translated to `[receiver message]` syntax
- All `extern Class PTR_s_*` references resolved (1 class + 25 selectors)
- `_main` emitted as standalone `int main()` with `NSApplicationMain`
- Zero compiler errors in generated stubs

### Nib Struct Tests
- 17 Python tests covering nib file parsing, selector/outlet extraction, type encoding mapping
- ObjC archive round-trip test (creates NSWindow/NSTextField/NSButton/NSMenu, archives via NSArchiver, loads back)

## Not Working / Remaining Gaps

### Decompilation Quality
- **Nested objc_msgSend** — `[[self window] display]` produces garbled output from the regex-based translator
- **Decompiler artifacts** — `halt_baddata()`, `CONCAT31`, `int3`, `CONCAT44` macros from Ghidra's m68k decompilation
- **SUB_ address resolution** — functions like `SUB_0500301a` (string copy) and `func_0x050024b0` can't be named without NeXTSTEP shared library symbol tables from `/lib`
- **All params typed as `(id)`** — ivar type encoding strings are not used to generate proper ObjC type signatures yet
- **Ghidra C output, not true ObjC** — the decompiler emits C; the fixup pipeline does regex-based transforms, not AST-level understanding

### Nib Struct Parsing
- **Nib roundtrip** — raw nib bytes are copied as `NSData`, not actually parsed and reconstructed; there is no true round-trip
- **WindowTemplate struct** — frame coordinates, title, styleMask not decoded from nib byte arrays
- **MenuTemplate struct** — menu items with titles, key equivalents, actions not extracted
- **Control/Button/TextField frames** — positions and sizes not parsed from nib struct data
- **Outlet/action connections** — not resolved from nib data into usable form
- **Runtime gmodel** — still uses guessed positions instead of actual nib layout data

### Pipeline Gaps
- **Categories** — `__cat_cls_meth`/`__cat_inst_meth` sections not parsed (low impact, most apps don't use them)
- **Protocols** — `__protocol` section not parsed
- **`LC_LOADFVMLIB`** — loaded library paths known but no symbol resolution without the actual `.shlib` files
- **Ivar type strings** — stored in `__inst_var_def`/`__meth_var_types` but only offsets are used, not types

## What's Needed Next

### Short Term
- Parse nib struct data directly (WindowTemplate frame/title, MenuTemplate items, control frames) from `[Nc]` byte arrays using known struct layouts
- Resolve outlet/action connections by parsing `NSNibOutletConnector` objects in the typedstream
- Add NeXTSTEP shared library symbol resolution when `/lib` files are available
- Clean up Ghidra decompiler artifacts (`halt_baddata`, CONCAT macros) in the fixup pass

### Medium Term
- Generate proper ObjC type signatures from ivar type encoding strings (not just `(id)`)
- Handle nested `objc_msgSend` in the translator (parenthesized receiver expressions)
- Support multiple architecture slices in a single pipeline run
- Extract `__protocol` and category metadata

### Long Term
- Full typedstream-based nib conversion to GNUstep gmodel with correct frames and connections
- Display PostScript → GNUstep drawing backend
- `nextthunk` m68k emulator integration for dynamic analysis
