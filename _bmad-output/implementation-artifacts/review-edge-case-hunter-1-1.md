# Edge Case Hunter — Code Review: Story 1-1

You receive the diff below AND read access to the project at `/home/sshack/Code/steppingstone`.

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

Walk every branching path and boundary condition. Check for:
- Invalid inputs and edge cases
- File/path edge cases (empty paths, missing directories, permission issues, etc.)
- CLI argument edge cases
- System interaction edge cases
- Missing handling of boundary conditions in the diff
- Cross-platform compatibility issues
- Any unhandled exceptions or silent failures

Only report unhandled edge cases — do not report things that are properly handled.

Output findings as a Markdown list. Each finding: one-line title, severity (Critical/High/Medium/Low), and evidence from the diff or project.
