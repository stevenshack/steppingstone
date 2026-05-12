#!/usr/bin/env python3
"""fixup_gmodel.py - Post-process full Gorm gmodel for runtime loading.
Adds GMModel wrapper, removes IMConnectors (broken library), patches class names.
Preserves the original gmodel for Gorm editing. Output is _runtime.gmodel.
"""

import re, sys, os

def fixup_gmodel(gmodel_path):
    with open(gmodel_path) as f:
        text = f.read()

    output_path = gmodel_path.replace('.gmodel', '_runtime.gmodel')

    # Find key object references from NSIBObjectData
    objs_ref = conns_ref = 'nil'
    for m in re.finditer(r'\bobjects\s*=\s*("[^"]+")', text):
        objs_ref = m.group(1)
    for m in re.finditer(r'\bconnections\s*=\s*("[^"]+")', text):
        conns_ref = m.group(1)

    # Remove IMConnector objects and their references from connections array
    connector_refs = []
    
    # Find all object definitions, one at a time
    obj_pat = re.compile(r'^\s*("[^"]+")\s*=\s*\{.*?\};', re.MULTILINE | re.DOTALL)
    cleaned = []
    last_end = 0
    for m in obj_pat.finditer(text):
        block = m.group(0)
        key = m.group(1)
        if 'IMOutletConnector' in block or 'IMControlConnector' in block:
            connector_refs.append(key)
            # Don't include this block in the output
            continue
        cleaned.append(block)
        last_end = m.end()

    # Rebuild text without connector objects, wrapped in outer braces
    text = '{\n' + '\n'.join(cleaned) + '\n}'

    # Remove connector references from ALL elements lists in the gmodel
    if connector_refs:
        for ref in connector_refs:
            # Remove from elements lists: "elements = (..., ref, ...)"
            text = re.sub(r',\s*' + re.escape(ref), '', text)
            text = re.sub(re.escape(ref) + r'\s*,', '', text)
            text = re.sub(r'\(\s*' + re.escape(ref) + r'\s*\)', '()', text)

    # Add GMModel wrapper at top
    wrapper = (
        '  Version = 1; \n'
        '  RootObject = {\n'
        '    Connections = %s;\n'
        '    Objects = %s;\n'
        '    isa = GMModel;\n'
        '  }; \n'
        '  TopLevelObjects = (RootObject); \n'
    ) % (conns_ref, objs_ref)

    idx = text.find('\n"Object')
    if idx > 0:
        text = text[:idx+1] + wrapper + text[idx+1:]

    # Patch class names for runtime compatibility
    text = text.replace('isa = NSMutableSet', 'isa = GSMutableArray')
    # NSIBObjectData is a Gorm-only class; replace with NSObject for runtime
    text = text.replace('isa = NSIBObjectData', 'isa = GSNibObjectData')

    with open(output_path, 'w') as f:
        f.write(text)

    print(f"  Fixed: {os.path.basename(gmodel_path)} → {os.path.basename(output_path)}")
    print(f"    Removed {len(connector_refs)} connector objects")

if __name__ == "__main__":
    for path in sys.argv[1:] if len(sys.argv) > 1 else ['EnvelopeMaker.gmodel', 'Info.gmodel']:
        if os.path.exists(path):
            fixup_gmodel(path)
        else:
            print(f"  (not found: {path})")
