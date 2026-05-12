#!/bin/bash
# Run a Ghidra Python script on a binary using PyGhidra
# Usage: ./run_ghidra_script.sh <binary> [script.py]

set -e
BIN="$1"
SCRIPT="${2:-/home/sshack/Code/nextthunk/ghidra_scripts/list_funcs.py}"

if [ ! -f "$BIN" ]; then
    echo "Usage: $0 <binary> [script.py]"
    exit 1
fi

GHIDRA="/home/sshack/Code/nextthunk/ghidra"
JAVA_HOME="/usr/lib/jvm/java-25-openjdk-amd64"
export JAVA_HOME

# Import binary into a temp project first if not already done
PROJECT_DIR="/tmp/ghidra_projects"
BIN_NAME=$(basename "$BIN" .i386 | tr '.' '_')

# Check if project already exists
if [ ! -d "${PROJECT_DIR}/${BIN_NAME}.gpr" ]; then
    echo "Importing $BIN..."
    $GHIDRA/support/analyzeHeadless \
        "$PROJECT_DIR" "$BIN_NAME" \
        -import "$BIN" -overwrite -noanalysis \
        2>/dev/null || true
fi

# Now run PyGhidra on the imported binary
echo "Running script on ${BIN_NAME}:${BIN}..."
$GHIDRA/support/pyghidraRun \
    "$PROJECT_DIR/${BIN_NAME}.gpr" \
    "${BIN_NAME}" \
    "$SCRIPT" \
    2>&1 | grep -v "^INFO\|^WARNING\|^\$" | head -80
