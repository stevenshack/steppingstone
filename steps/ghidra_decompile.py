#!/usr/bin/env python3
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SYM_TYPE_DEBUG_STAB = 0x1E


def find_ghidra():
    ghidra_install = os.environ.get("GHIDRA_INSTALL")
    if ghidra_install:
        ghidra_bin = os.path.join(ghidra_install, "support", "analyzeHeadless")
        if os.path.isfile(ghidra_bin):
            return ghidra_install
    fallback = os.path.join(REPO_ROOT, "ghidra")
    fallback_bin = os.path.join(fallback, "support", "analyzeHeadless")
    if os.path.isfile(fallback_bin):
        return fallback
    return None


def load_manifest(manifest_path):
    if not os.path.isfile(manifest_path):
        print(f"error: {manifest_path}: no such file", file=sys.stderr)
        sys.exit(1)
    with open(manifest_path) as f:
        try:
            manifest = json.load(f)
        except json.JSONDecodeError as e:
            print(f"error: manifest is not valid JSON: {e}", file=sys.stderr)
            sys.exit(1)
    for key in ("binary_path", "symbols", "objc_classes"):
        if key not in manifest:
            print(f"error: manifest missing required key '{key}'", file=sys.stderr)
            sys.exit(1)
    binary_path = manifest.get("binary_path")
    if not isinstance(binary_path, str) or not os.path.isfile(binary_path):
        print(
            f"error: binary_path in manifest not found: {binary_path}",
            file=sys.stderr,
        )
        sys.exit(1)
    return manifest


def build_address_list(manifest):
    lines = []
    for sym in manifest.get("symbols", []):
        addr = sym.get("address")
        name = sym.get("name", "")
        sym_type = sym.get("type", 0)
        if addr is None or not name:
            continue
        if sym_type == SYM_TYPE_DEBUG_STAB:
            continue
        lines.append((addr, name))
    for cls in manifest.get("objc_classes", []):
        cls_name = cls.get("name", "")
        for method in (cls.get("methods") or []):
            imp = method.get("imp")
            method_name = method.get("name", "")
            if imp is not None:
                lines.append((imp, f"[{cls_name} {method_name}]"))
    lines.sort(key=lambda x: x[0])
    return lines


def format_addr_line(addr, label):
    if isinstance(addr, str):
        addr = int(addr, 16)
    return f"0x{addr:x} {label}"


def write_address_list(lines, path):
    with open(path, "w") as f:
        for addr, label in lines:
            f.write(format_addr_line(addr, label) + "\n")


def validate_ghidra_scripts():
    scripts_dir = os.path.join(REPO_ROOT, "ghidra_scripts")
    required = ["DisableObjCAnalyzer.java", "DecompileBatch.java"]
    missing = [s for s in required if not os.path.isfile(os.path.join(scripts_dir, s))]
    if missing:
        print(
            f"error: required Ghidra scripts not found: {', '.join(missing)}",
            file=sys.stderr,
        )
        sys.exit(1)
    return scripts_dir


def run_analyze_headless(ghidra_path, binary_path, addr_list_path):
    analyze_headless = os.path.join(ghidra_path, "support", "analyzeHeadless")
    scripts_dir = validate_ghidra_scripts()
    project_dir = tempfile.mkdtemp(prefix="ghidra_projects_")
    project_name = "step_decomp"

    cmd = [
        analyze_headless,
        project_dir,
        project_name,
        "-import",
        binary_path,
        "-overwrite",
        "-scriptPath",
        scripts_dir,
        "-preScript",
        "DisableObjCAnalyzer.java",
        "-postScript",
        "DecompileBatch.java",
        addr_list_path,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except PermissionError:
        err = {
            "status": "error",
            "error": f"analyzeHeadless at {analyze_headless} is not executable",
        }
        print(json.dumps(err))
        sys.exit(1)
    except subprocess.TimeoutExpired:
        err = {
            "status": "error",
            "error": "analyzeHeadless timed out after 600 seconds",
        }
        print(json.dumps(err))
        sys.exit(1)
    except OSError as e:
        err = {"status": "error", "error": f"failed to execute analyzeHeadless: {e}"}
        print(json.dumps(err))
        sys.exit(1)
    finally:
        shutil.rmtree(project_dir, ignore_errors=True)

    if result.returncode != 0:
        msg = f"analyzeHeadless failed (exit {result.returncode})"
        if result.stderr:
            msg += "\n" + result.stderr.strip()
        err = {"status": "error", "error": msg}
        print(json.dumps(err))
        sys.exit(1)

    return result.stdout


def parse_decompile_output(raw_text):
    functions = []
    current_func = None
    current_lines = []
    for line in raw_text.splitlines():
        stripped = line.rstrip()
        if stripped.startswith("FUNC_BEGIN "):
            if current_func is not None:
                functions.append((current_func, "\n".join(current_lines)))
            rest = stripped[len("FUNC_BEGIN "):].strip()
            parts = rest.split(" ", 1)
            addr_str = parts[0]
            name = parts[1] if len(parts) > 1 else ""
            current_func = (addr_str, name)
            current_lines = []
        elif stripped == "FUNC_END":
            if current_func is not None:
                functions.append((current_func, "\n".join(current_lines)))
            current_func = None
            current_lines = []
        elif current_func is not None:
            current_lines.append(line)
    if current_func is not None:
        functions.append((current_func, "\n".join(current_lines)))
    return functions


def sanitize_name(name):
    safe = "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in name)
    return safe.strip("_") or "unnamed"


def write_function_files(functions, output_dir):
    func_dir = os.path.join(output_dir, "functions")
    try:
        os.makedirs(func_dir, exist_ok=True)
    except PermissionError as e:
        print(f"error: cannot create {func_dir}: {e}", file=sys.stderr)
        sys.exit(1)
    manifest_map = {}
    used_names = set()
    for (addr_str, name), code in functions:
        safe = sanitize_name(name)
        fname = f"{addr_str}_{safe}.c"
        while fname in used_names:
            safe += "_"
            fname = f"{addr_str}_{safe}.c"
        used_names.add(fname)
        fpath = os.path.join(func_dir, fname)
        try:
            with open(fpath, "w") as f:
                f.write(code)
        except PermissionError as e:
            print(f"error: cannot write {fpath}: {e}", file=sys.stderr)
            sys.exit(1)
        manifest_map[addr_str] = f"functions/{fname}"
    manifest_path = os.path.join(output_dir, "manifest.json")
    try:
        with open(manifest_path, "w") as f:
            json.dump(manifest_map, f, indent=2)
    except PermissionError as e:
        print(f"error: cannot write {manifest_path}: {e}", file=sys.stderr)
        sys.exit(1)
    return manifest_map


def main():
    parser = argparse.ArgumentParser(
        description="Invoke Ghidra headless decompiler and produce C output"
    )
    parser.add_argument("--manifest", required=True, help="Path to parse_binary JSON manifest")
    parser.add_argument("--output-dir", required=True, help="Directory for output files")
    args = parser.parse_args()

    ghidra_path = find_ghidra()
    if ghidra_path is None:
        err = {
            "status": "error",
            "error": (
                "Ghidra not found. "
                "Set GHIDRA_INSTALL or place ghidra/ in repo root."
            ),
        }
        print(json.dumps(err))
        sys.exit(1)

    manifest = load_manifest(args.manifest)
    try:
        os.makedirs(args.output_dir, exist_ok=True)
    except PermissionError as e:
        print(f"error: cannot create output dir {args.output_dir}: {e}", file=sys.stderr)
        sys.exit(1)

    lines = build_address_list(manifest)
    addr_list_path = os.path.join(args.output_dir, "addr_list.txt")
    write_address_list(lines, addr_list_path)

    binary_path = manifest["binary_path"]
    raw_output = run_analyze_headless(ghidra_path, binary_path, addr_list_path)

    functions = parse_decompile_output(raw_output)
    write_function_files(functions, args.output_dir)

    result = {
        "status": "ok",
        "function_count": len(functions),
        "output_dir": os.path.abspath(args.output_dir),
    }
    print(json.dumps(result))


if __name__ == "__main__":
    main()
