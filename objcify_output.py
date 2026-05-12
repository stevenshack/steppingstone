#!/usr/bin/env python3
"""Post-process Ghidra decompiler output into ObjC method skeletons."""

import re, sys, os

def objcify(decomp_file, metadata_file, output_file):
    # Read ObjC metadata (method address -> name mapping)
    method_map = {}
    with open(metadata_file) as f:
        for line in f:
            m = re.match(r'0x([0-9a-fA-F]+)\s+\[(.*)\]', line.strip())
            if m:
                addr = int(m.group(1), 16)
                name = m.group(2)
                method_map[addr] = name

    # Read decompiled functions
    with open(decomp_file) as f:
        content = f.read()

    # Parse function blocks
    blocks = re.findall(r'FUNC (0x[0-9a-fA-F]+) (.+?)\n(.*?)\n---', content, re.DOTALL)

    out_lines = []
    for addr_str, func_name, body in blocks:
        addr = int(addr_str, 16)
        body = body.strip()
        
        # Get ObjC method name if available
        objc_name = method_map.get(addr)
        
        # Build method signature
        if objc_name:
            # Parse ObjC method signature
            sig = objc_method_signature(objc_name)
            out_lines.append(sig)
        else:
            # Regular C function
            out_lines.append(f"// Function: {func_name} @ {addr_str}")
            out_lines.append(body)
            out_lines.append("")
            continue
        
        # Clean up and format the body
        lines = body.split("\n")
        
        # Remove empty/trivial bodies
        cleaned = []
        for line in lines:
            line = line.strip()
            if not line or line == "{":
                continue
            if line == "}":
                cleaned.append("}")
                continue
            # Indent body
            cleaned.append("    " + line)
        
        if cleaned:
            out_lines.append("{")
            out_lines.extend(cleaned)
        else:
            out_lines.append("{")
            out_lines.append("}")
        out_lines.append("")
    
    with open(output_file, "w") as f:
        f.write("\n".join(out_lines))
    
    print(f"  {len(blocks)} functions processed -> {output_file}")

def objc_method_signature(sel_name):
    """Convert a selector name like 'setStringValue:' or 'appDidInit' to ObjC signature."""
    # Split on colons to get argument names
    parts = sel_name.split(":")
    parts = [p for p in parts if p]
    
    if len(parts) <= 1:
        # No arguments: - (void)methodName
        return f"- (void){sel_name}"
    else:
        # With arguments: - (void)setStringValue:(id)sender
        sig = "- (void)"
        for i, p in enumerate(parts):
            if i == 0:
                sig += f"{p}:(id)arg{i+1}"
            else:
                sig += f" {p}:(id)arg{i+1}"
        return sig

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print(f"Usage: {sys.argv[0]} <decomp_output.txt> <objc_metadata.txt> <output.m>")
        sys.exit(1)
    objcify(sys.argv[1], sys.argv[2], sys.argv[3])
