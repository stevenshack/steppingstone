# Acceptance Auditor — Code Review: Story 1-1

Review this diff against the spec and context docs.

## Spec: Story 1.1 — Project scaffold with uv

### Story
As a developer, I want the project to have a working Python environment with uv and the defined directory structure, so that I can clone the repo, run `uv sync`, and start building pipeline components immediately.

### Acceptance Criteria
1. **Given** the project directory **When** I run `uv sync` **Then** a virtual environment is created with all declared dependencies installed
2. **Given** the project structure **When** I list the root directory **Then** I see directories: `app2source/`, `nextstep2gnustep/`, `steps/`, `lib/`, `clang-ast-fixup/`, `tests/`
3. **Given** the scaffolded project **When** I run `uv run app2source --help` **Then** it prints usage information and exits with code 0
4. **Given** the scaffolded project **When** I run `uv run nextstep2gnustep --help` **Then** it prints usage information and exits with code 0

### Architecture Requirements (from architecture.md)
- Language stack: Python-primary; Clang AST fixup is C++ subprocess
- Toolchain: `uv` for project management — `pyproject.toml` is the single source of truth
- Naming conventions (PEP 8): `snake_case` for functions/variables, `CamelCase` for classes, `SCREAMING_SNAKE` for constants
- Entry point naming: Verb-based — `app2source`, `nextstep2gnustep`
- Subprocess protocol (future): Tools communicate via stdout (JSON result), stderr (progress), exit code

### Technical Requirements
- Python version: >=3.10
- Build system: `pyproject.toml` with setuptools or hatchling backend (uv-compatible)
- CLI framework: `argparse` (stdlib, no extra dependency)
- Entry points format: `app2source = "app2source.__main__:main"` and `nextstep2gnustep = "nextstep2gnustep.__main__:main"`
- `__main__.py` pattern: Define a `main()` function, guarded by `if __name__ == "__main__": main()`
- Orchestrator stubs: `orchestrator.py` defines a `run()` function with keyword-only args, body raises `NotImplementedError`

### Existing Files to Preserve
The repository already contains working scripts and analysis tools in the root directory. Do NOT delete or move: `*.py`, `*.sh`, `*.m`, `*.c`, `patches/`, `ghidra_scripts/`, `docs/`, `tests/`, `README.md`, `STATUS.md`.

## Diff

### pyproject.toml (new)
```toml
[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.build_meta"

[project]
name = "steppingstone"
version = "0.1.0"
description = "Toolchain for migrating NEXTSTEP/OPENSTEP Mach-O applications to GNUstep on Linux"
requires-python = ">=3.10"
license = { text = "MIT" }

dependencies = []

[dependency-groups]
dev = [
    "pytest>=8.0.0",
]

[project.scripts]
app2source = "app2source.__main__:main"
nextstep2gnustep = "nextstep2gnustep.__main__:main"

[tool.setuptools.packages.find]
include = ["app2source*", "nextstep2gnustep*", "steps*", "lib*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

### Makefile (new)
```makefile
.PHONY: install test clean

install:
	uv sync --dev

test:
	uv run pytest

clean:
	rm -rf __pycache__ .pytest_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
```

### app2source/__init__.py (new)
*(empty file)*

### app2source/__main__.py (new)
```python
import argparse
import sys

from app2source.orchestrator import run


def main():
    parser = argparse.ArgumentParser(
        prog="app2source",
        description="Phase 1 pipeline: extract readable source code from a NEXTSTEP/OPENSTEP Mach-O binary.",
    )
    parser.add_argument(
        "macho",
        nargs="?",
        help="path to Mach-O binary to process",
    )
    parser.add_argument(
        "--output-dir", "-o",
        default=".",
        help="output directory for generated source files (default: current directory)",
    )
    args = parser.parse_args()

    if args.macho is None:
        parser.print_help()
        sys.exit(0)

    run(macho_path=args.macho, output_dir=args.output_dir)


if __name__ == "__main__":
    main()
```

### app2source/orchestrator.py (new)
```python
def run(*, macho_path: str, output_dir: str) -> None:
    raise NotImplementedError("Phase 1 pipeline not yet implemented")
```

### nextstep2gnustep/__init__.py (new)
*(empty file)*

### nextstep2gnustep/__main__.py (new)
```python
import argparse
import sys

from nextstep2gnustep.orchestrator import run


def main():
    parser = argparse.ArgumentParser(
        prog="nextstep2gnustep",
        description="Phase 2 pipeline: translate NEXTSTEP/OPENSTEP source tree to compilable GNUstep project.",
    )
    parser.add_argument(
        "source_dir",
        nargs="?",
        help="path to Phase 1 output source directory",
    )
    parser.add_argument(
        "--output-dir", "-o",
        default="gnustep-output",
        help="output directory for GNUstep project (default: gnustep-output)",
    )
    args = parser.parse_args()

    if args.source_dir is None:
        parser.print_help()
        sys.exit(0)

    run(source_dir=args.source_dir, output_dir=args.output_dir)


if __name__ == "__main__":
    main()
```

### nextstep2gnustep/orchestrator.py (new)
```python
def run(*, source_dir: str, output_dir: str) -> None:
    raise NotImplementedError("Phase 2 pipeline not yet implemented")
```

### steps/__init__.py (new)
*(empty file)*

### lib/__init__.py (new)
*(empty file)*

### clang-ast-fixup/CMakeLists.txt (new)
```cmake
cmake_minimum_required(VERSION 3.16)
project(clang-ast-fixup LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
```

## Task

Review this diff against the spec and context docs. Check for:
- Violations of acceptance criteria
- Deviations from spec intent
- Missing implementation of specified behavior
- Contradictions between spec constraints and actual code
- Missing error handling for spec-defined behaviors

Output findings as a Markdown list. Each finding: one-line title, which AC/constraint it violates, and evidence from the diff.
