---
stepsCompleted: [1, 2, 3, 4, 5, 6, 7, 8]
inputDocuments:
  - planning-artifacts/prd.md
  - brainstorming/brainstorming-session-2026-05-12-1541.md
  - docs/NIB_FORMAT.md
workflowType: 'architecture'
project_name: 'steppingstone'
user_name: 'Steven'
date: '2026-05-12'
status: 'complete'
completedAt: '2026-05-12'
---

# Architecture Decision Document

This document builds collaboratively through step-by-step discovery. Sections are appended as we work through each architectural decision together.

## Project Context Analysis

### Requirements Overview

**Functional Requirements (16 total):**
- **Binary Analysis & Decompilation (FR1-FR3):** i386 NeXTSTEP Mach-O → decompiled C/ObjC source; extract embedded ObjC type encodings from `__OBJC` segment; extract resources from binary sections and `.app` bundles
- **Source Fixup & Cleansing (FR4-FR6):** Clang AST-based fixup tool parses Ghidra C output and removes compiler artifacts; rewrites `objc_msgSend` call sites with properly typed ObjC message expressions; emits hand-augmentable stub annotations for unresolved methods
- **Symbol & Type Resolution (FR7-FR10):** C function stub resolution via address-offset mapping; header-derived type database via `clang -ast-dump`; cross-validation against embedded type encodings; manual type mappings preserved across re-runs
- **Project Generation (FR11-FR16):** One `.h`/`.m` pair per class; NeXTSTEP-compatible Makefile + PB.project; Phase 1 nib copy / Phase 2 nib→gmodel; API translation from NeXTSTEP to GNUStep; combined single-invocation mode

**Non-Functional Requirements (7 total):**
- **Reliability (NFR1-NFR3):** Graceful failure on malformed input with actionable error context; partial pipeline output preserved on failure
- **Performance (NFR4-NFR5):** End-to-end decompilation of WordPerfect-scale app in under 1 hour; Clang AST fixup processes single file in under 1 minute
- **Portability (NFR6-NFR7):** Toolchain runs on x86 Linux; limited dependencies (GCC, Clang/LLVM, GNUStep runtime, Python)

**Scale & Complexity:**
- Primary domain: CLI tool / decompilation pipeline
- Complexity level: High — novel two-phase architecture with hardware verification loop
- Estimated architectural components: 6-8 major components (binary parser, AST fixup tool, symbol database, type cross-validator, project generator, API translator, resource pipeline, stub system)

### Technical Constraints & Dependencies

- Phase 1 output must compile with GCC on NeXTSTEP (i386) — no modern ObjC features
- Phase 2 output must compile with GNUStep ObjC runtime on Linux — NeXTSTEP ABI compatibility
- Binary formats limited to i386 Mach-O with NeXTSTEP ABI (no m68k in Phase 1)
- Dependencies: Clang/LLVM C++ API (AST fixup tool), Python (metadata extraction), GCC (NeXTSTEP), GNUStep runtime (Linux)
- Verification requires access to real NeXTSTEP i386 hardware (or emulator)

### Cross-Cutting Concerns Identified

- **Type recovery quality** — affects all downstream components; dual-path validation (encodings + headers) mitigates but doesn't eliminate
- **Stub preservation** — hand-augmentable stubs must survive pipeline re-runs; affects file layout and merge strategy
- **Error handling** — partial output preservation on failure impacts every pipeline stage; clear error context required for debug loop
- **Build system matrix** — NeXTSTEP Makefile/PB.project + GNUStep Makefile + combined invocation mode = 3 distinct build configurations
- **Community contribution path** — modular component design to enable independent contribution without central coordination

## Starter Template Evaluation

### Primary Technology Domain

CLI toolchain / decompilation pipeline — Python-oriented architecture

### Foundation Decision

**Primary Language:** Python (all pipeline orchestration, metadata extraction, symbol DB, stub management, test harness)

**Accessory Components:**
- **Clang AST Fixup Tool:** C++ (Clang/LLVM C++ API), invoked as subprocess from Python
- **Generated Output:** NeXTSTEP ObjC/C (Phase 1) / GNUStep ObjC/C (Phase 2)
- **Build System:** Makefiles (target-format-specific), Python script entry points for users

**Toolchain:** `uv` for Python project management and package installation

**Rationale:**
- The pipeline is fundamentally a sequence of transformations with metadata extraction — Python excels at this
- C++/Clang tooling only needed for the AST fixup component (highest-risk, needs structural code manipulation)
- Python makes the pipeline accessible for community contributions (Sam the contributor persona)
- Existing codebase already follows this pattern (Python scripts calling Ghidra, `nm`, etc.)

## Core Architectural Decisions

### Decision Priority Analysis

**Critical Decisions (Block Implementation):**
- Pipeline orchestration model — resolved
- Intermediate format between phases — resolved
- Symbol database format — resolved
- Stub system design — resolved (with deferred refinement on re-run preservation)

**Important Decisions (Shape Architecture):**
- Testing & verification strategy — deferred to patterns
- Error handling & partial output — deferred to patterns

### Pipeline Orchestration Model

**Decision:** Independent orchestrator CLI tools (`app2source`, `nextstep2gnustep`) that run individual subprocess tools for each pipeline step.

**Rationale:** Each pipeline step (binary parsing, metadata extraction, AST fixup, project generation) is a standalone CLI tool. The orchestrators compose them, passing file-based intermediate output between steps. This matches the PRD's composable architecture and enables independent contribution (Sam can improve one step without touching others).

### Intermediate Format

**Decision:** File-based passing between each step, structured directory layout with JSON manifest.

**Rationale:** Loose coupling — each step reads/writes files, composable, debuggable, re-runnable. No in-memory pipeline state to manage.

### Symbol Database

**Decision:** JSON files — simple, git-friendly, human-inspectable, natively parseable in Python.

**Rationale:** No need for SQLite overhead at this stage. JSON is trivially diffable, editable, and fits the file-based intermediate format pattern.

### Stub System Design

**Decision:** Inline FIXME comments in generated `.m`/`.h` files with full diagnostic context (class, selector, best-guess types, confidence score). Manual resolutions tracked via `.resolved.json` sidecar files keyed by `"class:selector"`.

**Rationale:** FIXME annotations keep the information where it's actionable. The `.resolved.json` sidecar provides a simple, diff-friendly mechanism for preserving manual fixes across re-runs without complex patch management. Design may evolve as more apps are ported.

## Implementation Patterns & Consistency Rules

### Naming Patterns

**Python Conventions (PEP 8):**
- Functions/variables: `snake_case`
- Classes: `CamelCase`
- Constants: `SCREAMING_SNAKE`
- Private members: `_leading_underscore`

**Pipeline Tool Entry Points:**
- Verb-based: `extract_symbols`, `parse_binary`, `fixup_ast`, `generate_project`
- One entry-point function per tool module, called from CLI wrapper

**JSON Manifest Fields:**
- `snake_case` for all field names
- Consistent keys across all intermediate manifests

**FIXME Annotation Format:**
```
// FIXME(steppingstone): unresolvable -[ClassName selector:]
//   confidence: 0.65
//   best_guess: (int)param1
//   selector_encoding: v@:i
```

### Structure Patterns

**Pipeline Step Organization:**
- Each pipeline step is a single `.py` module in `steps/`
- Shared utilities in `lib/` (symbol_db.py, binary_reader.py, etc.)
- Orchestrator scripts (`app2source`, `nextstep2gnustep`) at repo root
- Tests in `tests/` mirroring the source tree

**Sidecar Placement:**
- `.resolved.json` files stored alongside generated `.m`/`.h` files in the output project

### Communication Patterns

**Subprocess Protocol:**
- Tools communicate via: stdout (JSON result), stderr (progress/logging), exit code (0=success, 1=error)
- Machine-parseable final result always as JSON on last line of stdout
- Errors include actionable context: "file foo.m line 42: unresolved selector"

**Error Handling:**
- Exceptions in Python tools propagate to orchestrator
- Orchestrator catches, logs, and preserves partial output on failure
- Non-zero exit from subprocess tools aborts the pipeline step

## Project Structure & Boundaries

### Complete Project Directory Structure

```
steppingstone/
├── README.md
├── Makefile                    # Top-level: install, test, clean
├── pyproject.toml              # uv project config
├── uv.lock                     # Lockfile (uv)
├── .gitignore
├── app2source/                 # Phase 1 orchestrator (Python entry)
│   ├── __init__.py
│   ├── __main__.py             # CLI: app2source WordPerfect.app ./output
│   └── orchestrator.py
├── nextstep2gnustep/           # Phase 2 orchestrator (Python entry)
│   ├── __init__.py
│   ├── __main__.py             # CLI: nextstep2gnustep ./src ./output
│   └── orchestrator.py
├── steps/                      # Individual pipeline tools
│   ├── __init__.py
│   ├── parse_binary.py         # FR1: Mach-O parsing, section extraction
│   ├── extract_metadata.py     # FR2: ObjC type encodings from __OBJC
│   ├── extract_resources.py    # FR3: nibs, images, fonts, sounds
│   ├── ghidra_decompile.py     # Wraps Ghidra headless
│   ├── fixup_ast.py            # FR4-FR5: Clang AST fixup (subprocess)
│   ├── resolve_symbols.py      # FR7-FR8: symbol DB, header parsing
│   ├── cross_validate_types.py # FR9: encoding vs header validation
│   ├── generate_project.py     # FR11-FR13: .h/.m, Makefile, PB.project
│   ├── translate_api.py        # FR14: NeXTSTEP to GNUStep API mapping
│   └── generate_gnustep.py     # FR15-FR16: GNUStep Makefile + combined mode
├── lib/                        # Shared utilities
│   ├── __init__.py
│   ├── symbol_db.py            # Symbol database (JSON-based)
│   ├── binary_reader.py        # Mach-O section reading
│   ├── type_encoding.py        # ObjC type encoding parser
│   ├── nib_parser.py           # Nib typedstream parsing
│   ├── header_parser.py        # clang -ast-dump wrapper
│   └── stub_manager.py         # FIXME + .resolved.json logic
├── clang-ast-fixup/            # C++ Clang/LLVM tool
│   ├── CMakeLists.txt
│   ├── src/
│   │   ├── main.cpp
│   │   ├── artifact_cleaner.cpp
│   │   ├── ast_walker.cpp
│   │   └── source_emitter.cpp
│   └── include/
│       └── fixup/
└── tests/
    ├── __init__.py
    ├── test_parse_binary.py
    ├── test_symbol_db.py
    ├── test_type_encoding.py
    ├── test_nib_parser.py
    ├── test_stub_manager.py
    ├── fixtures/
    │   └── minimal-app/
    └── integration/
        └── test_pipeline.py
```

### Requirements to Structure Mapping

**Binary Analysis & Decompilation (FR1-FR3):**
- `steps/parse_binary.py`, `steps/extract_metadata.py`, `steps/extract_resources.py`
- `lib/binary_reader.py`, `lib/type_encoding.py`

**Source Fixup & Cleansing (FR4-FR6):**
- `steps/fixup_ast.py` (Python wrapper)
- `clang-ast-fixup/` (C++ subprocess tool)

**Symbol & Type Resolution (FR7-FR10):**
- `steps/resolve_symbols.py`, `steps/cross_validate_types.py`
- `lib/symbol_db.py`, `lib/header_parser.py`, `lib/stub_manager.py`

**Project Generation (FR11-FR16):**
- `steps/generate_project.py`, `steps/translate_api.py`, `steps/generate_gnustep.py`

### Integration Points

**Between Stages:** File-based — each step reads intermediate JSON/directory from previous step's output path. The orchestrator manages the working directory and passes paths as CLI arguments.

**Python to C++:** `steps/fixup_ast.py` writes cleaned C source to a temp file, invokes the `clang-ast-fixup` binary, reads the transformed output from stdout.

**Testing:** Unit tests in `tests/` cover individual `lib/` modules. Integration tests in `tests/integration/` run the full pipeline against test fixtures.

## Architecture Validation Results

### Coherence Validation ✅
All decisions are compatible — Python orchestrators calling subprocess tools with file-based JSON passing is internally consistent. Phase boundaries properly isolate the two target platforms (GCC/NeXTSTEP vs GNUStep/Linux).

### Requirements Coverage ✅
All 16 functional requirements map to specific modules in the project structure. Reliability NFRs are addressed by error handling patterns. Performance NFRs are documented as constraints. Portability NFRs satisfied by dependency documentation.

### Implementation Readiness ✅
Decisions are documented with rationale. Project structure is concrete and complete. Patterns cover naming, structure, and communication. Minor gaps are implementation-level, not architectural.

### Gap Analysis
**Minor Gaps (Deferred to Implementation):**
- Logging library choice (stdlib logging vs structlog)
- Test framework (pytest recommended)
- Per-step JSON manifest schema definitions
- CI/CD pipeline configuration

### Architecture Completeness Checklist
- [x] Project context thoroughly analyzed
- [x] Scale and complexity assessed
- [x] Technical constraints identified
- [x] Cross-cutting concerns mapped
- [x] Critical decisions documented with versions
- [x] Technology stack fully specified
- [x] Integration patterns defined
- [x] Performance considerations addressed
- [x] Naming conventions established
- [x] Structure patterns defined
- [x] Communication patterns specified
- [x] Process patterns documented
- [x] Complete directory structure defined
- [x] Component boundaries established
- [x] Integration points mapped
- [x] Requirements to structure mapping complete

### Architecture Readiness Assessment
**Overall Status:** READY FOR IMPLEMENTATION
**Confidence Level:** High

**Key Strengths:**
- Two-phase architecture with hardware verification gate is novel and de-risks the problem
- Python-primary design maximizes accessibility for community contributions
- Modular pipeline steps enable independent testing and iteration
- File-based intermediate format makes every stage debuggable and re-runnable

**Areas for Future Enhancement:**
- CI/CD pipeline for automated decompilation testing
- Pre-built toolchain distribution (pip install steppingstone)
- Community header database contribution workflow

### Implementation Handoff
**AI Agent Guidelines:**
- Follow all architectural decisions exactly as documented
- Use implementation patterns consistently across all components
- Respect project structure and boundaries
- Refer to this document for all architectural questions

**First Implementation Priority:** Scaffold project structure — create directories, `app2source`/`nextstep2gnustep` entry points, `pyproject.toml` with uv, and top-level `Makefile`.
