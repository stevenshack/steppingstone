import json
import sys
import os
import subprocess

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from steps.parse_binary import parse_binary
from lib.binary_reader import (
    MachOError,
)

from tests.helpers import build_minimal_macho, write_temp_binary


def test_parse_binary_manifest_has_expected_keys():
    raw = build_minimal_macho()
    path = write_temp_binary(raw)
    try:
        manifest = parse_binary(path)
        assert "binary_path" in manifest
        assert "format" in manifest
        assert manifest["format"] == "mach-o"
        assert "architecture" in manifest
        assert "endian" in manifest
        assert "load_commands" in manifest
        assert "segments" in manifest
        assert "sections" in manifest
        assert "symbols" in manifest
        assert "objc_classes" in manifest
    finally:
        os.unlink(path)


def test_parse_binary_load_commands_content():
    raw = build_minimal_macho()
    path = write_temp_binary(raw)
    try:
        manifest = parse_binary(path)
        assert len(manifest["load_commands"]) == 1
        lc = manifest["load_commands"][0]
        assert lc["description"] == "LC_SEGMENT"
        assert lc["segname"] == "__TEXT"
    finally:
        os.unlink(path)


def test_parse_binary_sections_content():
    raw = build_minimal_macho()
    path = write_temp_binary(raw)
    try:
        manifest = parse_binary(path)
        assert "__text" in manifest["sections"]
        sec = manifest["sections"]["__text"]
        assert sec["vaddr"] == 4096
        assert sec["size"] == 8192
    finally:
        os.unlink(path)


def test_parse_binary_segments_content():
    raw = build_minimal_macho()
    path = write_temp_binary(raw)
    try:
        manifest = parse_binary(path)
        assert len(manifest["segments"]) == 1
        seg = manifest["segments"][0]
        assert seg["name"] == "__TEXT"
        assert seg["sections"] == ["__text"]
    finally:
        os.unlink(path)


def test_parse_binary_non_macho_exits_error():
    path = write_temp_binary(b"not a mach-o binary at all")
    try:
        try:
            parse_binary(path)
            assert False, "expected MachOError"
        except MachOError:
            pass
    finally:
        os.unlink(path)


def test_parse_binary_cli_non_zero_exit():
    path = write_temp_binary(b"garbage data here")
    try:
        script = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "steps",
            "parse_binary.py",
        )
        result = subprocess.run(
            [sys.executable, script, path],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0
        assert "error:" in result.stderr
    finally:
        os.unlink(path)


def test_parse_binary_cli_success():
    raw = build_minimal_macho()
    path = write_temp_binary(raw)
    try:
        script = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "steps",
            "parse_binary.py",
        )
        result = subprocess.run(
            [sys.executable, script, path],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        manifest = json.loads(result.stdout)
        assert manifest["format"] == "mach-o"
    finally:
        os.unlink(path)
