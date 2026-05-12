# Dump ObjC class/method metadata and decompile all methods
# Run with: analyzeHeadless <project> <binary> -scriptPath <dir> -postScript dump_objc.py

import os
import json

# Get current program info
from ghidra.program.model.listing import Function
from ghidra.program.model.symbol import SourceType
from ghidra.app.decompiler import DecompInterface
from ghidra.util.task import ConsoleTaskMonitor

pm = currentProgram
addr_factory = pm.getAddressFactory()
listing = pm.getListing()
monitor = ConsoleTaskMonitor()

# Collect ObjC metadata
objc_data = {
    "classes": [],
    "methods": [],
    "selectors": []
}

# Parse __OBJC segment
objc_block = pm.getMemory().getBlock("__OBJC")
if objc_block:
    print("Found __OBJC segment")
    try:
        # Try to get ObjC info from Ghidra's built-in analyzer
        from ghidra.app.plugin.core.analysis.AutoAnalysisManager import AutoAnalysisManager
        mgr = AutoAnalysisManager.getAnalysisManager(currentProgram)
        mgr.reAnalyzeAll(monitor)
    except:
        print("  Running deferred analysis...")
    
    # Read class names from __objc_classnames if Ghidra parsed them
    # Otherwise fall back to reading the section directly
    
    # Try the ObjC data type
    try:
        # Read class names section
        class_names_block = pm.getMemory().getBlock("__OBJC___class_names")
        if class_names_block is None:
            # Try alternate naming
            for block in pm.getMemory().getBlocks():
                if "__class_names" in block.getName():
                    class_names_block = block
                    break
        
        if class_names_block:
            print(f"\nClass names block: {class_names_block.getName()}")
            data = class_names_block
            # Read null-terminated strings
            addr = data.getStart()
            end = data.getEnd()
            while addr.compareTo(end) < 0:
                s = getDataAt(addr)
                if s and hasattr(s, 'getDefaultValueRepresentation'):
                    val = s.getDefaultValueRepresentation()
                    if val and val != "''":
                        pass  # Ghidra may not have parsed these as strings
                addr = addr.add(1)
    except Exception as e:
        print(f"  Class name scan error: {e}")

# Fallback: read raw binary data from the file
try:
    mem = pm.getMemory()
    objc_info = {}
    
    # Find __OBJC segment  
    for block in mem.getBlocks():
        bname = block.getName()
        if "OBJC" in bname or "objc" in bname:
            print(f"  Block: {bname} @ {block.getStart()} size {block.getSize()}")
    
    # Try reading from __DATA or __OBJC segment
    import java.lang
    from ghidra.program.model.data import StringDataType
    
    # Scan for selector names in read-only data
    from ghidra.util.search import MemorySearch
    
except Exception as e:
    print(f"Memory scan error: {e}")

# Decompile all functions
print("\n=== DECOMPILED FUNCTIONS ===")
decomp = DecompInterface()
decomp.openProgram(pm)

funcs = listing.getFunctions(True)
count = 0
for func in funcs:
    if count > 200:  # limit output for now
        print(f"  ... ({funcs.getFunctionCount() - 200} more functions)")
        break
    name = func.getName()
    body = func.getBody()
    
    # Skip library/stub functions
    if name.startswith("_") and not name.startswith("_objc"):
        continue
    if name.startswith("FUN_"):
        continue
    
    # Decompile
    results = decomp.decompileFunction(func, 60, monitor)
    if results and results.getDecompiledFunction():
        code = results.getDecompiledFunction().getC()
        # Print first 3 lines
        lines = code.split("\n")
        print(f"\n--- {name} @ {func.getEntryPoint()} ---")
        for line in lines[:5]:
            print(f"  {line}")
        if len(lines) > 5:
            print(f"  ... ({len(lines)} lines total)")
    count += 1

decomp.dispose()
print(f"\nDecompiled {count} functions")
