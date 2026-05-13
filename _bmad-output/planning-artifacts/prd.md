---
stepsCompleted: ['step-01-init', 'step-02-discovery', 'step-02b-vision', 'step-02c-executive-summary', 'step-03-success', 'step-04-journeys', 'step-05-domain', 'step-06-innovation', 'step-07-project-type', 'step-08-scoping', 'step-09-functional', 'step-10-nonfunctional', 'step-11-polish']
releaseMode: phased
classification:
  projectType: developer_tool
  domain: scientific
  complexity: high
  projectContext: greenfield
inputDocuments:
  - brainstorming/brainstorming-session-2026-05-12-1541.md
documentCounts:
  briefs: 0
  research: 0
  brainstorming: 1
  investigations: 0
  projectDocs: 0
workflowType: 'prd'
---

# Product Requirements Document - steppingstone

**Author:** Steven
**Date:** 2026-05-12

## Executive Summary

Steppingstone is a decompilation pipeline that converts compiled NeXTSTEP binaries into authentic, editable GNUStep source code — enabling classic applications like WordPerfect, FrameMaker, Quantrix, and the Mathematica frontend to run natively on modern Linux. The tool decomposes the problem into two independently solvable phases: Phase 1 decompiles the binary to authentic NeXTSTEP source (verifiable by recompilation on real hardware), and Phase 2 migrates that source to GNUStep APIs and build systems.

### What Makes This Special

Decompilation-to-source is chosen over emulation or binary compatibility because it provides permanent maintainability — users get editable source they can fix, extend, and evolve beyond NeXTSTEP's original limitations. The two-phase architecture with a hardware-verified recompilation gate transforms correctness from "does the output look right?" to "does the output produce an identical binary?" No existing toolchain provides this path. The Clang AST-based fixup tool replaces fragile regex post-processing with structural code understanding, and the exploitation of embedded ObjC type encodings from the binary itself provides compiler-grade ground truth for type recovery.

### Project Classification

- **Project Type:** Developer Tool
- **Domain:** Scientific / Research (binary analysis, decompilation, code generation)
- **Complexity:** High
- **Context:** Greenfield
- **Release Mode:** Phased (MVP + Growth)

## Success Criteria

### User Success
- A user can install the toolchain, point it at WordPerfect.app, and get a buildable GNUStep project
- All menus, buttons, keyboard equivalents function identically to the original
- Documents display and print correctly
- Helper apps (wpspell, wp-ascii, wp-rtf) build and integrate as expected

### Business Success
- Open-source release with buildable WordPerfect as proof point
- A handful of users successfully porting their own apps counts as success
- Reproducible pipeline enabling community contributions

### Technical Success
- Behavioral equivalence: decompiled WordPerfect behaves identically to the original under GNUStep — all UI interactions, document operations, and helper app IPC work the same way
- Phase 1 verification: generated NeXTSTEP source compiles on real hardware
- Modular pipeline: each component independently usable (decompiler, fixup tool, project generator)

## Project Scoping & Phased Development

### MVP Strategy & Philosophy
**Approach:** Problem-solving MVP — the minimum that makes WordPerfect runnable under GNUStep. Every feature is driven by: "does WordPerfect need this to launch and function?"
**Resource Requirements:** Solo developer (Steven). Pipeline architecture designed for single-developer velocity.

### MVP Feature Set (Phase 1 + Phase 2)

**Core User Journeys Supported:**
- Maya (end user): runs pipeline against WordPerfect.app, gets working GNUStep binary
- Alex (porter): ports additional apps using the full toolchain
- Sam (contributor): improves individual pipeline components

**Must-Have Capabilities:**
- `app2source` (Phase 1): i386 NeXTSTEP Mach-O → compilable NeXTSTEP ObjC/C source
- `nextstep2gnustep` (Phase 2): NeXTSTEP source → GNUStep project with translated APIs
- Clang AST fixup tool replacing regex-based `fixup_decompile.py`
- Dual-path symbol database (address → name via nm, selector → signature via headers)
- Hand-augmentable stub system (manual fixes preserved across re-runs)
- WordPerfect.app family (main + wpspell, wp-ascii, wp-rtf) builds and runs under GNUStep
- Nib copy-through in Phase 1, nib→gmodel conversion in Phase 2
- Resource extraction and format mapping (Phase 2)

### Growth Features (Post-MVP)
- Additional app targets (FrameMaker, Quantrix)
- Community documentation and porting guide
- Header database from community contributions

### Vision (Future)
Mathematica frontend, CI pipeline, packaging — deferred indefinitely.

### Risk Mitigation Strategy
**Technical Risks:** Clang AST tool complexity. Mitigation: test harness from day one, hand-augmentable stubs as fallback.
**Market Risks:** Low — personal/open-source project with modest adoption expectations.
**Resource Risks:** Solo developer. Mitigation: modular architecture enables community contributions without central coordination.

## User Journeys

### Maya — The End User

Maya is a technical writer who used WordPerfect on NeXTSTEP for years. She recently migrated to Linux but none of the modern word processors match her keyboard-driven workflow. She discovers Steppingstone, runs the pipeline against her WordPerfect.app, and it produces a buildable GNUStep project. She opens a 90s-era document, edits with familiar keystrokes, and prints it — everything works as it did on NeXTSTEP. She is productive again and tells two colleagues.

### Alex — The Porter

Alex is a collector of NeXTSTEP software with a copy of FrameMaker.app he wants to revive. He points Steppingstone at it, and the pipeline produces initial source with some `fixup_needed` annotations. He opens the stubs, patches the signatures against the header database, and because the pipeline supports hand-augmentable stubs, his fixes are preserved on re-run. FrameMaker compiles and launches. His experience: an afternoon, not weeks. He contributes his header mappings back to the community.

### Sam — The Contributor

Sam is a systems programmer interested in retrocomputing and decompilation. She finds Steppingstone on GitHub and picks up an open issue — the type encoding cross-validator has false positives for struct-typed method parameters. She extends `dump_objc_metadata.py`, adds tests, and submits a PR. It's merged — the false positive rate drops from 12% to 2%. She becomes a regular contributor.

### Journey Requirements Summary

- **End user** requires: one-command pipeline, working GNUStep runtime, clear install docs
- **Porter** requires: hand-augmentable stubs, header database CLI, preservation of manual fixes
- **Contributor** requires: modular component architecture, test harness, open contribution workflow

## Domain-Specific Requirements

### Target Architecture
- i386 NeXTSTEP binaries only (no m68k support in Phase 1)

### Technical Constraints
- Phase 1 output must compile with GCC on NeXTSTEP (i386)
- Phase 2 output must compile with GNUStep ObjC runtime on Linux
- Binary formats limited to i386 Mach-O with NeXTSTEP ABI

### Resource Handling
- Phase 1: resources (nibs, images, fonts, sounds) copied as raw blobs — no conversion
- Phase 2: nib→gmodel, image format conversion, font remapping handled separately

### Verification
- Phase 1: recompile on real NeXTSTEP i386 hardware, compare behavioral equivalence
- Phase 2: visual/manual verification under GNUStep

## Innovation & Novel Patterns

### Detected Innovation Areas

**Verified Decompilation Loop:** The two-phase pipeline with a hardware recompilation gate is a novel architecture in decompilation. Most decompilers stop at "does it look right?" — this one asks "does it recompile to an identical binary?" The Phase 1/Phase 2 split decomposes a hard problem into two independently solvable, independently verifiable halves.

**Clang AST Fixup Tool:** Replacing Ghidra's fragile regex-based `fixup_decompile.py` with structural AST manipulation via Clang's C++ API. The pipeline uses the binary's own embedded ObjC type encodings as ground truth to cross-validate header-derived type signatures — a technique unique to NeXTSTEP binaries.

**Decompilation-for-Compatibility:** Choosing decompile-to-source over emulation or binary compatibility as the path to run legacy software. This trades immediate time-to-value for permanent maintainability.

### Market Context & Competitive Landscape

No existing toolchain targets this specific problem. Existing NeXTSTEP preservation efforts (Previous, SheepShaver) use emulation/virtualization. Darling provides a GNUStep-based binary compatibility layer but does not decompile. RetDec and Ghidra are general decompilation frameworks but lack ObjC-specific understanding and the two-phase architecture.

### Validation Approach

Phase 1: decompile WordPerfect, recompile on real NeXTSTEP i386 hardware, verify behavioral equivalence. Phase 2: the same source builds under GNUStep, launches, and passes acceptance criteria — all menus work, documents display and print correctly, helper apps integrate.

### Risk Mitigation

Main risk: decompilation quality for complex ObjC patterns is unknown until tested on real apps. Mitigation: WordPerfect MVP surfaces gaps early. Hand-augmentable stubs degrade gracefully — even imperfect decompilation produces a modifiable starting point. Phase 1 value (usable NeXTSTEP source) is delivered independently of Phase 2.

## Developer Tool Specific Requirements

### Project-Type Overview
Steppingstone ships as two standalone CLI tools — `app2source` (Phase 1: binary → NeXTSTEP source) and `nextstep2gnustep` (Phase 2: NeXTSTEP source → GNUStep project) — installed via `git clone && make`.

### Technical Architecture Considerations
- Language matrix: Phase 1 generates NeXTSTEP ObjC/C (GCC-compatible), Phase 2 translates to GNUStep ObjC runtime APIs
- API surface: two CLI entry points with composable intermediate output
- Dependencies: managed organically as implementation reveals them
- Documentation: README-driven with usage examples for each tool
- Example app: a minimal NeXTSTEP binary for end-to-end verification (deferred to epic planning)

### Implementation Considerations
- Phase 1 and Phase 2 independently usable (Phase 2 should work on hand-written NeXTSTEP source)
- Clang AST fixup tool is highest-risk component — test harness from day one
- Hand-augmentable stub preservation critical for porter workflow

## Functional Requirements

### Binary Analysis & Decompilation
- FR1: The user can supply an i386 NeXTSTEP Mach-O binary to app2source and receive decompiled C/ObjC source
- FR2: The pipeline extracts embedded ObjC type encoding strings from the __OBJC segment
- FR3: The pipeline extracts resources (nibs, images, fonts, sounds) from binary sections and .app bundles

### Source Fixup & Cleansing
- FR4: The Clang AST fixup tool parses Ghidra C output and removes compiler artifacts
- FR5: The Clang AST tool identifies objc_msgSend call sites and rewrites them with properly typed ObjC message expressions
- FR6: The pipeline emits hand-augmentable stub annotations for any method that could not be fully type-resolved

### Symbol & Type Resolution
- FR7: The pipeline resolves C function stub calls to NeXTSTEP library symbols via address-offset mapping
- FR8: The pipeline builds a header-derived type database by parsing NeXTSTEP headers via clang -ast-dump
- FR9: The type recovery system cross-validates embedded type encodings against header-derived signatures
- FR10: Manual type mappings entered by the porter are preserved across pipeline re-runs

### Project Generation
- FR11: app2source generates one .h/.m file pair per class
- FR12: app2source generates a NeXTSTEP-compatible Makefile and PB.project
- FR13: app2source copies nibs as raw blobs (Phase 1) / converts to gmodel (Phase 2)
- FR14: nextstep2gnustep translates NeXTSTEP API calls to GNUStep equivalents
- FR15: nextstep2gnustep generates a GNUStep Makefile compilable on Linux
- FR16: The porter can combine app2source + nextstep2gnustep in a single invocation

## Non-Functional Requirements

### Reliability
- NFR1: The pipeline fails gracefully on malformed or unsupported input with a clear error message identifying the issue and its location
- NFR2: Error messages include actionable context (binary section, method, file) to support the iterative debug loop
- NFR3: Partial pipeline output is preserved on failure when possible — a failed Phase 2 does not discard valid Phase 1 output

### Performance
- NFR4: End-to-end decompilation of a mid-size app (WordPerfect-scale) completes within 1 hour on modern hardware
- NFR5: The Clang AST fixup tool processes a single file in under 1 minute

### Portability
- NFR6: The toolchain builds and runs on x86 Linux (primary target)
- NFR7: Dependencies are limited to well-known packages (GCC, Clang/LLVM, GNUStep runtime, Python)
