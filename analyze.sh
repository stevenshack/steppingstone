#!/bin/bash
# analyze.sh - Extract i386 slice and run Ghidra headless analysis
# Usage: ./analyze.sh LocalApps/OpenWrite.app/OpenWrite

set -e
BIN="$1"
if [ -z "$BIN" ] || [ ! -f "$BIN" ]; then
    echo "Usage: $0 <path-to-universal-binary>"
    echo "  Scans all apps if given a directory"
    exit 1
fi

GHIDRA_HOME="/home/sshack/Code/nextthunk/ghidra"
SCRIPT_DIR="/home/sshack/Code/nextthunk/ghidra_scripts"
PROJECT_DIR="/tmp/ghidra_projects"
JAVA_HOME="/usr/lib/jvm/java-25-openjdk-amd64"
export JAVA_HOME

mkdir -p "$PROJECT_DIR" "$SCRIPT_DIR"

analyze_one() {
    local app_path="$1"
    local app_name=$(basename "$app_path")
    local app_dir=$(dirname "$app_path")
    
    echo ""
    echo "============================================"
    echo "Analyzing: $app_name"
    echo "============================================"
    
    # Extract i386 slice
    local i386_path="${app_dir}/${app_name}.i386"
    python3 -c "
import struct
with open('$app_path', 'rb') as f:
    data = f.read()
magic = struct.unpack_from('>I', data, 0)[0]
if magic == 0xCAFEBABE:
    narchs = struct.unpack_from('>I', data, 4)[0]
    for i in range(narchs):
        off = 8 + i * 20
        cputype = struct.unpack_from('>I', data, off)[0]
        foff = struct.unpack_from('>I', data, off+8)[0]
        fsz = struct.unpack_from('>I', data, off+12)[0]
        cpusub = struct.unpack_from('>I', data, off+4)[0]
        arch_map = {7: 'i386', 6: 'm68k', 11: 'hppa', 14: 'sparc'}
        a = arch_map.get(cputype, f'cpu={cputype}')
        print(f'  [{i}] {a} (sub=0x{cpusub:x}) off=0x{foff:x} sz=0x{fsz:x}')
        if cputype == 7:
            with open('$i386_path', 'wb') as out:
                out.write(data[foff:foff+fsz])
            print(f'  -> Extracted i386 ({fsz} bytes)')
    if not os.path.exists('$i386_path'):
        print('  No i386 slice found')
        raise SystemExit(1)
elif magic == 0xCEFAEDFE:
    print('  Already i386')
    # copy as-is
    import shutil
    shutil.copy('$app_path', '$i386_path')
else:
    print(f'  Not a universal binary (magic=0x{magic:08x})')
    raise SystemExit(1)
"
    
    # Run Ghidra headless
    echo ""
    echo "Running Ghidra headless analysis..."
    proj_name="${app_name}_analysis"
    
    # Remove old project if exists
    rm -rf "${PROJECT_DIR}/${proj_name}.rep" "${PROJECT_DIR}/${proj_name}.gpr" 2>/dev/null
    
    $GHIDRA_HOME/support/analyzeHeadless \
        "$PROJECT_DIR" \
        "$proj_name" \
        -import "$i386_path" \
        -overwrite \
        -noanalysis \
        -postScript dump_objc.py \
        2>&1 | tail -20
    
    echo ""
    echo "Done. Project at: ${PROJECT_DIR}/${proj_name}.gpr"
}

# Handle single binary or scan directory
if [ -f "$BIN" ]; then
    analyze_one "$BIN"
elif [ -d "$BIN" ]; then
    for app in "$BIN"/*.app; do
        name=$(basename "$app" .app)
        exe="$app/$name"
        if [ -f "$exe" ]; then
            # Check if universal (has i386)
            if file "$exe" | grep -q "universal"; then
                analyze_one "$exe"
            fi
        fi
    done
fi
