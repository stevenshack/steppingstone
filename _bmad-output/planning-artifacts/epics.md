---
stepsCompleted: [1, 2, 3, 4]
inputDocuments:
  - planning-artifacts/prd.md
  - planning-artifacts/architecture.md
  - brainstorming/brainstorming-session-2026-05-12-1541.md
  - docs/NIB_FORMAT.md
workflowType: 'epics'
project_name: 'steppingstone'
user_name: 'Steven'
date: '2026-05-12'
status: 'complete'
completedAt: '2026-05-12'
---

# steppingstone - Epic Breakdown

## Overview

This document provides the complete epic and story breakdown for steppingstone, decomposing the requirements from the PRD and Architecture requirements into implementable stories.

## Requirements Inventory

### Functional Requirements

FR1: The user can supply an i386 NeXTSTEP Mach-O binary to app2source and receive decompiled C/ObjC source
FR2: The pipeline extracts embedded ObjC type encoding strings from the __OBJC segment
FR3: The pipeline extracts resources (nibs, images, fonts, sounds) from binary sections and .app bundles
FR4: The Clang AST fixup tool parses Ghidra C output and removes compiler artifacts
FR5: The Clang AST tool identifies objc_msgSend call sites and rewrites them with properly typed ObjC message expressions
FR6: The pipeline emits hand-augmentable stub annotations for any method that could not be fully type-resolved
FR7: The pipeline resolves C function stub calls to NeXTSTEP library symbols via address-offset mapping
FR8: The pipeline builds a header-derived type database by parsing NeXTSTEP headers via clang -ast-dump
FR9: The type recovery system cross-validates embedded type encodings against header-derived signatures
FR10: Manual type mappings entered by the porter are preserved across pipeline re-runs
FR11: app2source generates one .h/.m file pair per class
FR12: app2source generates a NeXTSTEP-compatible Makefile and PB.project
FR13: app2source copies nibs as raw blobs (Phase 1) / converts to gmodel (Phase 2)
FR14: nextstep2gnustep translates NeXTSTEP API calls to GNUStep equivalents
FR15: nextstep2gnustep generates a GNUStep Makefile compilable on Linux
FR16: The porter can combine app2source + nextstep2gnustep in a single invocation

### Non-Functional Requirements

NFR1: The pipeline fails gracefully on malformed or unsupported input with a clear error message identifying the issue and its location
NFR2: Error messages include actionable context (binary section, method, file) to support the iterative debug loop
NFR3: Partial pipeline output is preserved on failure when possible — a failed Phase 2 does not discard valid Phase 1 output
NFR4: End-to-end decompilation of a mid-size app (WordPerfect-scale) completes within 1 hour on modern hardware
NFR5: The Clang AST fixup tool processes a single file in under 1 minute
NFR6: The toolchain builds and runs on x86 Linux (primary target)
NFR7: Dependencies are limited to well-known packages (GCC, Clang/LLVM, GNUStep runtime, Python)

### Additional Requirements

- **Python-primary architecture:** Pipeline orchestration, metadata extraction, symbol DB, stub management, test harness all in Python
- **uv toolchain:** `pyproject.toml` with uv for project management and package installation
- **File-based intermediate format:** Structured directory with JSON manifest between pipeline steps
- **Independent orchestrator CLI tools:** `app2source` and `nextstep2gnustep` as entry points that compose individual step tools
- **Clang AST fixup as C++ subprocess:** C++/Clang tool invoked from Python via subprocess
- **Stub system:** Inline FIXME comments in generated sources with `.resolved.json` sidecar files
- **JSON-based symbol database:** Simple, git-friendly, inspectable format
- **Two-phase pipeline:** Phase 1 → NeXTSTEP source (GCC-compatible), Phase 2 → GNUStep migration
- **Phase 1 verification gate:** Output must compile on real NeXTSTEP i386 hardware
- **i386 Mach-O only:** No m68k support in Phase 1
- **Modular pipeline steps:** Each tool in `steps/` is an independent module; shared utilities in `lib/`

### UX Design Requirements

N/A — CLI toolchain, no UI design specification.

### FR Coverage Map

FR1: Epic 2 - Binary parsing and decompilation
FR2: Epic 2 - ObjC type encoding extraction
FR3: Epic 2 - Resource extraction
FR4: Epic 2 - Clang AST artifact removal
FR5: Epic 2 - objc_msgSend rewrite
FR6: Epic 2 - Stub annotation emission
FR7: Epic 4 - C function stub resolution
FR8: Epic 4 - Header-derived type database
FR9: Epic 4 - Type encoding cross-validation
FR10: Epic 4 - Manual stub preservation
FR11: Epic 2 - Class file pair generation
FR12: Epic 2 - NeXTSTEP Makefile/PB.project
FR13: Epic 2+3 - Nib copy (Phase 1) / gmodel conversion (Phase 2)
FR14: Epic 3 - NeXTSTEP to GNUStep API translation
FR15: Epic 3 - GNUStep Makefile generation
FR16: Epic 3 - Combined invocation mode

## Epic List

### Epic 1: Foundation & Developer Setup
Scaffold the project structure, toolchain, and core infrastructure so contributors can clone and start building immediately.
**FRs covered:** None directly (enables all FRs)

### Story 1.1: Project scaffold with uv

As a developer,
I want the project to have a working Python environment with uv and the defined directory structure,
So that I can clone the repo, run `uv sync`, and start building pipeline components immediately.

**Acceptance Criteria:**

**Given** an empty project directory
**When** I run `uv sync`
**Then** a virtual environment is created with all declared dependencies installed

**Given** the project structure
**When** I list the root directory
**Then** I see directories: app2source/, nextstep2gnustep/, steps/, lib/, clang-ast-fixup/, tests/

**Given** I run `uv run app2source --help`
**Then** it prints usage information and exits with code 0

**Given** I run `uv run nextstep2gnustep --help`
**Then** it prints usage information and exits with code 0

### Epic 2: Binary Decompilation to NeXTSTEP Source (Phase 1)
Decompile i386 NeXTSTEP Mach-O binaries into authentic, compilable NeXTSTEP ObjC/C source with proper project structure, ready for hardware verification.
**FRs covered:** FR1, FR2, FR3, FR4, FR5, FR6, FR11, FR12, FR13 (Phase 1)

### Story 2.1: Binary parser extracts sections and metadata from a NeXTSTEP Mach-O file

As a developer,
I want the binary parser to extract all sections, symbol tables, and ObjC metadata from an i386 Mach-O file,
So that downstream pipeline stages have the raw data they need to decompile.

**Acceptance Criteria:**

**Given** a valid i386 NeXTSTEP Mach-O binary
**When** I run `parse_binary` against it
**Then** it outputs a JSON manifest listing all load commands, segments, and sections

**Given** a Mach-O binary with an `__OBJC` segment
**When** I run `parse_binary`
**Then** the extracted metadata includes ObjC class names, method lists, and type encoding strings

**Given** a corrupted or non-Mach-O file
**When** I run `parse_binary`
**Then** it exits with a non-zero code and prints an actionable error message (NFR1)

### Story 2.2: Ghidra headless decompiler integration produces C output

As a developer,
I want the pipeline to invoke Ghidra headlessly and capture its decompiled C output,
So that we can process it through the Clang AST fixup tool.

**Acceptance Criteria:**

**Given** a parsed Mach-O binary
**When** I run `ghidra_decompile` against the extracted binary sections
**Then** it produces Ghidra C output files for each decompiled function

**Given** Ghidra is not installed
**When** I run `ghidra_decompile`
**Then** it exits with a clear error message indicating Ghidra is required (NFR1)

### Story 2.3: Clang AST fixup tool cleans Ghidra output and reconstructs ObjC syntax

As a developer,
I want Ghidra's C output to be structurally cleaned by the Clang AST tool, with `objc_msgSend` calls rewritten as proper ObjC message expressions,
So that the decompiled source is authentic, compilable NeXTSTEP ObjC.

**Acceptance Criteria:**

**Given** Ghidra C output containing `objc_msgSend` calls
**When** I run `fixup_ast` against it
**Then** the output replaces `objc_msgSend` with proper `[receiver message]` syntax (FR5)

**Given** a method that could not be fully type-resolved
**When** `fixup_ast` processes it
**Then** the output includes a FIXME annotation with confidence score and best-guess types (FR6)

**Given** Ghidra artifact patterns like `halt_baddata()` or `CONCAT31`
**When** `fixup_ast` runs the regex prepass
**Then** those artifacts are removed from the output (FR4)

### Story 2.4: Project generator produces compilable NeXTSTEP source tree

As a developer,
I want the pipeline to output one `.h`/`.m` file pair per class with a Makefile and PB.project,
So that the decompiled program can be compiled on real NeXTSTEP hardware.

**Acceptance Criteria:**

**Given** cleaned ObjC source
**When** I run `generate_project` in Phase 1 mode
**Then** it creates one `.h`/`.m` pair per class (FR11)

**Given** the generated project
**When** I inspect the output directory
**Then** it contains a Makefile and PB.project for NeXTSTEP (FR12)

**Given** the source binary had nib resources
**When** I run `generate_project` in Phase 1 mode
**Then** nibs are copied as raw blobs into the output project (FR13)

### Epic 3: API Migration to GNUStep (Phase 2)
Translate NeXTSTEP source to GNUStep APIs, convert resources, and generate buildable GNUStep projects on Linux.
**FRs covered:** FR13 (Phase 2), FR14, FR15, FR16

### Story 3.1: NeXTSTEP API calls are translated to GNUStep equivalents

As a developer,
I want NeXTSTEP framework calls in decompiled source to be translated to their GNUStep equivalents,
So that the source compiles on Linux with the GNUStep ObjC runtime.

**Acceptance Criteria:**

**Given** NeXTSTEP source code with NeXTSTEP API calls
**When** I run `translate_api`
**Then** NeXTSTEP-specific calls are replaced with GNUStep equivalents (FR14)

**Given** the translated source
**When** I compile it with `gcc` and `libgnustep-base`
**Then** it compiles without unresolved symbol errors

### Story 3.2: Nib resources are converted to gmodel format

As a developer,
I want nib files to be converted to GNUStep gmodel format,
So that the UI defined in Interface Builder is preserved in the Linux build.

**Acceptance Criteria:**

**Given** a NeXTSTEP nib file
**When** I run the nib-to-gmodel converter
**Then** it produces a `.gmodel` file loadable by Gorm (FR13 Phase 2)

**Given** a nib with windows, menus, controls, and connections
**When** converted to gmodel
**Then** all UI elements, layouts, and target-action connections are preserved

### Story 3.3: GNUStep project with Makefile is generated and compiles on Linux

As a developer,
I want the pipeline to output a complete GNUStep project with a working Makefile,
So that the result can be compiled with `make` on any Linux system with GNUStep installed.

**Acceptance Criteria:**

**Given** translated ObjC source and gmodel resources
**When** I run `generate_gnustep`
**Then** it produces a directory with Makefile and all source files (FR15)

**Given** the generated project
**When** I run `make` on Linux with GNUStep installed
**Then** it produces a working binary

**Given** Phase 1 output has been generated
**When** I run `nextstep2gnustep` with the Phase 1 output directory
**Then** it produces the same result as running Phase 1 + Phase 2 separately (FR16)

### Epic 4: Quality, Polish & WordPerfect MVP
Refine symbol/type resolution, harden error handling, optimize performance, and verify the full pipeline end-to-end against WordPerfect.
**FRs covered:** FR7, FR8, FR9, FR10
**NFRs covered:** NFR1, NFR2, NFR3, NFR4, NFR5, NFR6, NFR7

### Story 4.1: Symbol/type resolution cross-validates encodings against headers

As a porter,
I want the symbol database to cross-validate embedded ObjC type encodings against header-derived signatures,
So that type recovery is accurate and mismatches are flagged for human review.

**Acceptance Criteria:**

**Given** a binary with embedded type encodings and matching NeXTSTEP headers
**When** I run `cross_validate_types`
**Then** it reports agreement or specific mismatches between the two sources (FR9)

**Given** resolved symbol data
**When** I inspect the JSON symbol database
**Then** it contains address-offset mappings for C functions and selector-based entries for ObjC methods (FR7, FR8)

**Given** a manual type mapping entered by the porter
**When** the pipeline re-runs
**Then** the manual mapping is preserved in `.resolved.json` (FR10)

### Story 4.2: Error handling and graceful failure for all pipeline stages

As a developer,
I want the pipeline to handle errors gracefully at every stage with clear, actionable messages,
So that I can quickly identify and fix issues without losing partial progress.

**Acceptance Criteria:**

**Given** a malformed binary input
**When** any pipeline stage encounters it
**Then** it fails with a clear error message identifying the issue and location (NFR1)

**Given** a Phase 2 failure
**When** the pipeline has already produced Phase 1 output
**Then** the Phase 1 output directory is preserved (NFR3)

**Given** any pipeline error
**When** the error message is displayed
**Then** it includes actionable context (section, method, file) (NFR2)

### Story 4.3: End-to-end WordPerfect MVP

As an end user (Maya),
I want the full pipeline to process WordPerfect.app and produce a working GNUStep binary,
So that I can run WordPerfect natively on Linux.

**Acceptance Criteria:**

**Given** WordPerfect.app for NeXTSTEP
**When** I run `app2source` followed by `nextstep2gnustep`
**Then** I get a buildable GNUStep project

**Given** the compiled GNUStep binary
**When** I launch it on Linux
**Then** all menus, buttons, and keyboard equivalents work identically to the original

**Given** WordPerfect
**When** I open and edit an existing document
**Then** it displays and prints correctly

**Given** helper apps (wpspell, wp-ascii, wp-rtf)
**When** the pipeline processes them
**Then** they build and integrate as expected
