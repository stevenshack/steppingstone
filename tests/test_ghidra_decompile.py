import json
import os
import subprocess
import sys
import tempfile
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from steps.ghidra_decompile import (
    build_address_list,
    parse_decompile_output,
    find_ghidra,
    load_manifest,
    write_address_list,
    format_addr_line,
    sanitize_name,
    write_function_files,
    main,
)

MOCK_MANIFEST = {
    "binary_path": "/tmp/test_binary",
    "architecture": "i386",
    "sections": {"__text": {"vaddr": 4096, "size": 8192, "file_offset": 0}},
    "symbols": [
        {"address": 100, "name": "_main", "type": 0x0E, "section": 1},
        {"address": 200, "name": "_helper", "type": 0x0F, "section": 1},
        {"address": 300, "name": "_debug_sym", "type": 0x1E, "section": 0},
        {"address": 400, "name": "", "type": 0x0E, "section": 1},
    ],
    "objc_classes": [
        {
            "name": "MyClass",
            "methods": [
                {"name": "init", "types": "@12@0:4", "imp": 500},
                {"name": "dealloc", "types": "v12@0:4", "imp": 600},
            ],
        }
    ],
}


def test_build_address_list_includes_symbols_with_type_not_0x1e():
    lines = build_address_list(MOCK_MANIFEST)
    addresses = [addr for addr, _ in lines]
    assert 100 in addresses
    assert 200 in addresses
    assert 300 not in addresses
    assert 400 not in addresses


def test_build_address_list_includes_objc_methods():
    lines = build_address_list(MOCK_MANIFEST)
    labels = [label for _, label in lines]
    assert "[MyClass init]" in labels
    assert "[MyClass dealloc]" in labels


def test_build_address_list_sorted_by_address():
    lines = build_address_list(MOCK_MANIFEST)
    addresses = [addr for addr, _ in lines]
    assert addresses == sorted(addresses)


def test_build_address_list_empty_manifest():
    empty = {"binary_path": "/tmp/t", "symbols": [], "objc_classes": []}
    lines = build_address_list(empty)
    assert lines == []


def test_build_address_list_missing_keys():
    minimal = {"binary_path": "/tmp/t"}
    lines = build_address_list(minimal)
    assert lines == []


def test_format_addr_line():
    assert format_addr_line(100, "_main") == "0x64 _main"
    assert format_addr_line(500, "[MyClass init]") == "0x1f4 [MyClass init]"


def test_write_address_list(tmp_path):
    lines = [(100, "_main"), (500, "[MyClass init]")]
    path = os.path.join(tmp_path, "addrs.txt")
    write_address_list(lines, path)
    with open(path) as f:
        content = f.read()
    assert "0x64 _main\n" in content
    assert "0x1f4 [MyClass init]\n" in content


def test_parse_decompile_output_single_function():
    text = (
        "FUNC_BEGIN 0x64 _main\n"
        "int main(void) {\n"
        "    return 0;\n"
        "}\n"
        "FUNC_END\n"
        "// DECOMPILED 1/1 functions"
    )
    funcs = parse_decompile_output(text)
    assert len(funcs) == 1
    (addr_str, name), code = funcs[0]
    assert addr_str == "0x64"
    assert name == "_main"
    assert "return 0;" in code


def test_parse_decompile_output_multiple_functions():
    text = (
        "FUNC_BEGIN 0x64 _main\n"
        "int main(void) { return 0; }\n"
        "FUNC_END\n"
        "FUNC_BEGIN 0xc8 _helper\n"
        "int helper(void) { return 1; }\n"
        "FUNC_END\n"
        "// DECOMPILED 2/2 functions"
    )
    funcs = parse_decompile_output(text)
    assert len(funcs) == 2


def test_parse_decompile_output_no_functions():
    funcs = parse_decompile_output("// DECOMPILED 0/0 functions")
    assert funcs == []


def test_parse_decompile_output_unclosed_begin():
    text = "FUNC_BEGIN 0x64 _main\nint x = 1;\n"
    funcs = parse_decompile_output(text)
    assert len(funcs) == 1
    _, code = funcs[0]
    assert "int x = 1;" in code


def test_parse_decompile_output_code_with_func_begin_text():
    text = (
        "FUNC_BEGIN 0x64 _main\n"
        'printf("FUNC_BEGIN test\\n");\n'
        "FUNC_END\n"
    )
    funcs = parse_decompile_output(text)
    assert len(funcs) == 1
    _, code = funcs[0]
    assert 'printf("FUNC_BEGIN test\\n");' in code


def test_sanitize_name():
    assert sanitize_name("_main") == "main"
    assert sanitize_name("[MyClass init]") == "MyClass_init"
    assert sanitize_name("hello world") == "hello_world"
    assert sanitize_name("") == "unnamed"


def test_write_function_files(tmp_path):
    functions = [
        (("0x64", "_main"), "int main(void) { return 0; }"),
        (("0xc8", "_helper"), "int helper(void) { return 1; }"),
    ]
    manifest = write_function_files(functions, tmp_path)
    func_dir = os.path.join(tmp_path, "functions")
    assert os.path.isdir(func_dir)
    assert os.path.isfile(os.path.join(func_dir, "0x64_main.c"))
    assert os.path.isfile(os.path.join(func_dir, "0xc8_helper.c"))
    with open(os.path.join(func_dir, "0x64_main.c")) as f:
        assert "int main(void)" in f.read()
    manifest_path = os.path.join(tmp_path, "manifest.json")
    assert os.path.isfile(manifest_path)
    with open(manifest_path) as f:
        data = json.load(f)
    assert data["0x64"] == "functions/0x64_main.c"


def test_write_function_files_empty(tmp_path):
    result = write_function_files([], tmp_path)
    assert result == {}
    func_dir = os.path.join(tmp_path, "functions")
    assert os.path.isdir(func_dir)
    assert len(os.listdir(func_dir)) == 0
    manifest_path = os.path.join(tmp_path, "manifest.json")
    assert os.path.isfile(manifest_path)
    with open(manifest_path) as f:
        assert json.load(f) == {}


def test_find_ghidra_env_var():
    with tempfile.TemporaryDirectory() as tmp:
        ghidra_support = os.path.join(tmp, "support")
        os.makedirs(ghidra_support)
        ah_path = os.path.join(ghidra_support, "analyzeHeadless")
        with open(ah_path, "w") as f:
            f.write("")
        with patch.dict(os.environ, {"GHIDRA_INSTALL": tmp}):
            result = find_ghidra()
            assert result == tmp


def test_find_ghidra_not_found():
    with patch.dict(os.environ, {}, clear=True), \
         patch("steps.ghidra_decompile.REPO_ROOT", "/tmp/nonexistent_repo"):
        result = find_ghidra()
        assert result is None


def test_load_manifest_missing_file(tmp_path):
    path = os.path.join(tmp_path, "nonexistent.json")
    with patch("sys.exit", side_effect=SystemExit) as mock_exit:
        with pytest.raises(SystemExit):
            load_manifest(path)
        mock_exit.assert_called_once_with(1)


def test_load_manifest_missing_keys(tmp_path):
    manifest_path = os.path.join(tmp_path, "bad.json")
    with open(manifest_path, "w") as f:
        json.dump({"foo": "bar"}, f)
    with patch("sys.exit", side_effect=SystemExit) as mock_exit:
        with pytest.raises(SystemExit):
            load_manifest(manifest_path)
        mock_exit.assert_called_once_with(1)


def test_load_manifest_missing_binary_path(tmp_path):
    manifest = dict(MOCK_MANIFEST)
    manifest["binary_path"] = "/nonexistent/binary"
    manifest_path = os.path.join(tmp_path, "manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f)
    with patch("sys.exit", side_effect=SystemExit) as mock_exit:
        with pytest.raises(SystemExit):
            load_manifest(manifest_path)
        mock_exit.assert_called_once_with(1)


def test_load_manifest_success(tmp_path):
    bin_path = os.path.join(tmp_path, "binary")
    with open(bin_path, "w") as f:
        f.write("")
    manifest = dict(MOCK_MANIFEST)
    manifest["binary_path"] = bin_path
    manifest_path = os.path.join(tmp_path, "manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f)
    result = load_manifest(manifest_path)
    assert result["binary_path"] == bin_path


def test_ghidra_not_found_error(capsys):
    test_args = [
        "ghidra_decompile.py",
        "--manifest", "/tmp/fake.json",
        "--output-dir", "/tmp/out",
    ]
    with patch("sys.argv", test_args), \
         patch("steps.ghidra_decompile.find_ghidra", return_value=None), \
         patch("sys.exit", side_effect=SystemExit) as mock_exit:
        with pytest.raises(SystemExit):
            main()
        mock_exit.assert_called_once_with(1)
        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert result["status"] == "error"
        assert "Ghidra not found" in result["error"]


def test_analyze_headless_failure(capsys):
    test_args = [
        "ghidra_decompile.py",
        "--manifest", "/tmp/fake.json",
        "--output-dir", "/tmp/out",
    ]
    with patch("sys.argv", test_args), \
         patch("steps.ghidra_decompile.find_ghidra", return_value="/fake/ghidra"), \
         patch("steps.ghidra_decompile.load_manifest") as mock_load, \
         patch("steps.ghidra_decompile.run_analyze_headless") as mock_run, \
         patch("sys.exit") as mock_exit:
        mock_load.return_value = MOCK_MANIFEST
        mock_run.side_effect = SystemExit(1)
        try:
            main()
        except SystemExit:
            pass
        mock_run.assert_called_once()


def test_cli_invocation_fails_without_manifest():
    script = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "steps",
        "ghidra_decompile.py",
    )
    result = subprocess.run(
        [sys.executable, script],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "usage:" in result.stderr or "required" in result.stderr
