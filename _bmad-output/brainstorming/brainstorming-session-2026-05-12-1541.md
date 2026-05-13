---
stepsCompleted: [1, 2, 3, 4]
inputDocuments: []
session_topic: 'Decompilation tool that converts NeXTStep binary applications into GNUStep source code'
session_goals: 'Decompile compiled NeXTStep applications and generate equivalent GNUStep source code that can be compiled into native GNUStep applications running on x86 Linux'
selected_approach: 'ai-recommended'
techniques_used: ['First Principles Thinking', 'Morphological Analysis', 'Cross-Pollination']
ideas_generated: ['pipeline-split-phase1-phase2', 'nextstep-hardware-verification-loop', 'clang-ast-fixup-tool-5-subproblems', 'regex-cleaning-prepass', 'clang-ast-dump-header-parser', 'dual-path-symbol-database', 'clang-cpp-api-ast-writer', 'clang-source-emission', 'objc-type-encodings', 'retdec-clean-compile', 'darling-symbol-trampoline', 'c2rust-ast-visitor-pattern', 'one-class-per-file-pair', 'resource-extraction-binary-and-loose', 'nib-copy-directly-phase1', 'pbproject-and-makefile-generation', 'graceful-degradation-confidence-scoring', 'hand-augmentable-stubs', 'disassembly-fallback-reference', 'library-symbol-resolution']
context_file: ''
session_active: false
workflow_completed: true
---

# Brainstorming Session Results

**Facilitator:** Steven
**Date:** 2026-05-12

## Session Overview

**Topic:** Decompilation tool that converts NeXTStep binary applications into GNUStep source code
**Goals:** Decompile compiled NeXTStep applications and generate equivalent GNUStep source code that can be compiled into native GNUStep applications running on x86 Linux

### Session Setup

_Steven is building a tool to take a compiled NeXTStep application (e.g., EnvelopeMaker, WordPerfect, FrameMaker), decompile it, and produce equivalent GNUStep source code. The generated source would then compile as a native GNUStep application on x86 Linux. This is a decompilation/recompilation pipeline — not emulation or runtime compatibility._

_The project "Steppingstone"/"nextthunk" already has a working 12-step pipeline using Ghidra for decompilation, Python for metadata extraction and fixup, and nib-to-gmodel conversion. Key gaps exist in decompilation quality, API name resolution, and type-accurate code generation._

## Technique Selection

**Approach:** AI-Recommended Techniques
**Analysis Context:** NeXTStep binary decompilation with focus on generating compilable GNUStep source code

**Recommended Techniques:**

- **First Principles Thinking:** Strip away assumptions about what's possible in decompilation and rebuild from fundamental truths about Mach-O binaries, Objective-C runtime structures, and NeXTStep frameworks.
- **Morphological Analysis:** Systematically decompose the translation pipeline into all sub-problems (binary parsing, class reconstruction, API mapping, code generation, resource conversion) and enumerate approaches for each.
- **Cross-Pollination:** Mine proven patterns from adjacent domains — static recompilation tools, transpilers, API translation layers (Wine, Darling), and existing decompilation frameworks.

**AI Rationale:** This is a greenfield systems architecture problem with no existing reference implementation. The sequence moves from fundamentals through structured decomposition to precedent mining.

## Technique Execution Results

### First Principles Thinking

**Interactive Focus:** Pipeline architecture redesign and problem decomposition

**Key Breakthroughs:**

1. **Pipeline split into two phases:**
   - **Phase 1:** NeXTStep binary → NeXTStep project (`.m`/`.h` files, `Makefile`, `PB.project`, nibs, resources) — authentic NeXTStep source that compiles on real NeXTSTEP hardware
   - **Phase 2:** NeXTStep project → GNUStep project — API translation, nib→gmodel, build system conversion
   - This separates the *decompilation problem* from the *migration problem*, each solvable independently

2. **Verification loop:** Decompile → recompile on real NeXTSTEP hardware → compare binaries — far stronger than "does it compile in GNUstep?"

3. **Nibs become zero-work in Phase 1:** Copy directly as blobs, no typedstream decoding or gmodel conversion needed until Phase 2

4. **APIs stay native:** NeXTStep API calls not translated during decompilation — Phase 2 handles that separately

5. **Library symbol resolution required:** Must resolve stub calls to actual NeXTStep API names. Full symbol tables available from original library files (`/lib`, `/NeXTLibrary`, `/NeXTDeveloper`)

6. **Clang AST-level fixup (Option 2 chosen):** Replace Ghidra's regex-based `fixup_decompile.py` with a tool that parses Ghidra C output through Clang, walks the AST, and rewrites `objc_msgSend` calls with proper types from a header-derived database

### Morphological Analysis

**Decomposition of the Clang AST Fixup Tool into 5 sub-problems:**

| # | Sub-problem | Chosen Approach |
|---|-------------|-----------------|
| 1 | Ghidra artifact pre-pass | Aggressive regex cleaning — evolve `fixup_decompile.py` to remove all Ghidra artifacts (`halt_baddata()`, `CONCAT31`, `nullsub_1`, etc.) before Clang sees the file. No compat headers — output must be authentic NeXTStep source. |
| 2 | Header parser | `clang -ast-dump` on NeXTStep developer headers — full type fidelity, handles typedefs, structs, macros. Clang natively understands ObjC method declarations. |
| 3 | Symbol database | Dual-path: address-offset mapping for C calls (via `nm` on libraries), selector-based lookup for ObjC method calls (via selector strings in the decompiled output) |
| 4 | AST walker + type rewrite | Clang C++ API — parse Ghidra C, find `objc_msgSend` call sites, build proper `ObjCMessageExpr` replacement nodes with types from the header DB. Full semantic correctness. |
| 5 | Source emission | Clang source printer + `clang-format` for clean output |

**Additional Phase 1 project generation decisions:**

- One class per `.m`/`.h` file pair
- Resources extracted from both binary sections and loose `.app` bundle files
- Nibs copied directly into the project (no conversion)
- Generate both `PB.project` (for Project Builder) and `Makefile` (for CLI builds)

### Cross-Pollination

**Patterns mined from adjacent domains:**

1. **Objective-C runtime type encodings** (from `__OBJC` segment): NeXTSTEP binaries embed type encoding strings (`@12@0:4`, `{NXRect=ffff}8@0:4`) that encode exact parameter types. Combined with the header DB, this provides two independent sources of type truth for cross-validation.

2. **RetDec's clean-compile → re-decompile loop:** Compile decompiler output through Clang to LLVM IR, run optimization passes, emit fresh C. The compiler is the best code cleaner. Could be applied pre-AST-walk to normalize Ghidra output.

3. **Darling's symbol trampoline mapping:** Darling maps Mach-O stubs to actual implementations by parsing the dyld shared cache's symbol trie. A simpler offline variant applies here — static symbol tables from library files.

4. **c2rust's type-aware RefactoringTool:** c2rust translates C to Rust using Clang's AST — structurally identical to the proposed Option 2 approach (parse C, match AST nodes, build new AST nodes, emit target language).

## Idea Organization and Prioritization

### Thematic Organization

**Theme 1: Pipeline Architecture Redesign**
_Focus: Splitting the monolithic pipeline into two independently solvable phases_

- Pipeline split: Phase 1 → NeXTStep project, Phase 2 → GNUStep project
- Verification loop using real NeXTSTEP hardware
- Nibs copied directly in Phase 1 (zero conversion work)
- APIs stay native through Phase 1

**Theme 2: Clang AST-Based Fixup Tool**
_Focus: Replacing regex-based fixup with structural AST manipulation_

- Ghidra artifact regex pre-pass (evolve `fixup_decompile.py`)
- Header parsing via `clang -ast-dump`
- Dual-path symbol database (address + selector)
- Clang C++ API AST walker with `ObjCMessageExpr` node construction
- Source emission via Clang printer + `clang-format`

**Theme 3: Project Generation**
_Focus: Producing an authentic NeXTStep project from decompiled output_

- One class per `.m`/`.h` file pair
- Resource extraction from binary sections and loose bundle files
- `PB.project` generation for Project Builder
- `Makefile` generation for CLI builds

**Theme 4: Type Recovery**
_Focus: Recovering accurate Objective-C types from binary and headers_

- Library symbol resolution via `nm`/`otool` on original NeXTStep libraries
- Objective-C type encodings from `__OBJC` segment as ground truth
- Cross-validating type encodings against header-derived signatures
- Header DB with full return types, parameter types, and struct definitions

**Theme 5: Cross-Domain Patterns**
_Focus: Proven approaches from other translation/recompilation projects_

- RetDec's compile-to-clean pattern
- Darling's symbol trampoline mapping
- c2rust's AST-based translation architecture
- Type encoding cross-validation (NeXTSTEP-specific advantage)

### Prioritization

**Top 3 High-Impact Ideas:**

1. **Pipeline split into Phase 1 / Phase 2** — Fundamentally changes the architecture. Enables verification loop. Simplifies Phase 1 by deferring all API translation.
2. **Clang AST fixup tool** — Replaces fragile regex patterns with structural code understanding. Closes the biggest quality gap in the current pipeline.
3. **Type encoding exploitation** — Already present in the binary. Provides ground truth types that cross-validate the header DB. High leverage, low implementation cost.

**Quick Wins:**

- Library symbol resolution via `nm` — libraries are available, symbols are intact, the data is ready
- Nib copy-directly strategy for Phase 1 — eliminates the broken nib→gmodel step from Phase 1 entirely
- Resource extraction from `.app` bundle — mostly file copy operations

**Breakthrough Concept:**

The Phase 1 / Phase 2 split enables a **verified decompilation loop**: decompile NeXTStep binary to source, recompile on real NeXTSTEP hardware, compare behavior. This transforms the problem from "does the output look right?" to "does the output produce an identical binary?" — a far stronger correctness standard.

### Action Plans

**Priority 1: Pipeline Split into Phase 1 / Phase 2**

- **Why this matters:** De-risks the entire project by separating concerns. Each phase becomes independently testable.
- **Immediate next steps:**
  1. Define the Phase 1 output specification (file layout, build system format, resource conventions)
  2. Modify `pipeline.sh` to stop after Phase 1 emission (skip nib→gmodel, skip GNUstep build)
  3. Adjust `build_sources.py` to emit NeXTStep-era API calls and Makefile instead of GNUstep
  4. Test on EnvelopeMaker: does the Phase 1 output compile and run on real NeXTSTEP hardware?
- **Resources:** NeXTSTEP developer headers, `/NeXTDeveloper`, `/NeXTLibrary` for symbols
- **Timeline:** 1-2 weeks for initial Phase 1 pipeline
- **Success indicators:** Generated `.m`/`.h` files compile on NeXTSTEP with `make`, linked `.app` matches original behavior

**Priority 2: Clang AST Fixup Tool**

- **Why this matters:** Replaces the weakest link (regex fixup) with structural code understanding
- **Immediate next steps:**
  1. Build the Ghidra artifact regex pre-pass — catalog every artifact pattern from EnvelopeMaker output
  2. Write the header parser using `clang -ast-dump` on NeXTStep developer headers
  3. Build the dual-path symbol database (addresses from `nm`, selectors from headers)
  4. Prototype the Clang C++ AST walker with a single `objc_msgSend` rewrite case
  5. Integrate type encodings from `__OBJC` for cross-validation
- **Resources:** Clang/LLVM C++ tooling, NeXTStep headers, existing `fixup_decompile.py` as reference
- **Timeline:** 4-6 weeks for functional tool
- **Success indicators:** Clean ObjC method signatures in output with correct parameter types

**Priority 3: Type Encoding Exploitation**

- **Why this matters:** Free ground truth already in the binary. Cross-validates and corrects header-derived types.
- **Immediate next steps:**
  1. Extend `dump_objc_metadata.py` to also extract type encoding strings from method descriptors
  2. Parse NeXTSTEP type encoding format (`@` = id, `:` = SEL, `{NXRect=ffff}` = struct)
  3. Build type encoding → header signature matcher for cross-validation
- **Resources:** Existing `dump_objc_metadata.py`, type encoding format docs (already partially decoded in nib work)
- **Timeline:** 2-3 days
- **Success indicators:** For each method, two independent type sources agree or flag mismatches

## Session Summary and Insights

**Key Achievements:**

- **Pipeline architecture redesigned** from monolithic (NeXTStep → GNUstep) to two-phase (NeXTStep → NeXTStep project → GNUstep project), enabling a verification loop on real hardware
- **Clang AST fixup tool designed** with 5 sub-problems and chosen approaches for each, replacing regex-based post-processing
- **Type recovery strategy identified** using both header-derived signatures and binary-embedded type encodings for cross-validation
- **Cross-domain patterns mined** from RetDec, Darling, c2rust, and NeXTSTEP's own ObjC type encoding system

**Key Insights:**

- The biggest architectural win is the Phase 1 / Phase 2 split — it transforms the problem from "one big jump" into "two solvable problems with a verification gate between them"
- NeXTSTEP's ObjC type encodings are an under-exploited resource that provides compiler-grade ground truth
- The Clang AST approach (Option 2) is the right level of investment — it stays within Python/C++ tooling you already use, sidesteps Ghidra's ObjC blind spots, and produces authentic source

**Session Reflections:**

The session started with a broad goal (NeXTStep binary to GNUStep source) and, through First Principles, revealed that the real problem needed splitting. Morphological Analysis broke the new architecture into concrete sub-problems with specific technical approaches. Cross-Pollination surfaced patterns from existing tools that directly apply. The user's deep knowledge of the existing pipeline and access to NeXTSTEP hardware, libraries, and headers gives this project advantages most decompilation efforts lack.
