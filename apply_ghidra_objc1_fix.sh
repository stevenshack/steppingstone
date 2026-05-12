#!/bin/bash
# Apply the ObjC1 fix patch to a Ghidra 12.0.4 source tree.
# Usage: ./apply_ghidra_objc1_fix.sh /path/to/ghidra-source
set -e

if [ -z "$1" ]; then
    echo "Usage: $0 /path/to/ghidra-source"
    echo "  Patches the ObjC1 type encoder to handle NeXTSTEP type encodings"
    echo "  instead of throwing UnsupportedOperationException."
    exit 1
fi

GHIDRA_SRC="$1"
PATCH_DIR="$(cd "$(dirname "$0")" && pwd)"
PATCH="$PATCH_DIR/ghidra_objc1_fix.patch"

if [ ! -f "$PATCH" ]; then
    echo "Error: patch file not found at $PATCH"
    exit 1
fi

# Apply the patch
cd "$GHIDRA_SRC"
patch -p1 < "$PATCH"
echo "Patch applied successfully."
echo ""
echo "To build: cd $GHIDRA_SRC && gradle buildBase"
