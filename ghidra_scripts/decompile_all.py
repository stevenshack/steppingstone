# Decompile all non-library functions and dump with addresses
# Run: analyzeHeadless <proj> <proj_name> -process <binary> -postScript decompile_all.py

from ghidra.app.decompiler import DecompInterface
from ghidra.util.task import ConsoleTaskMonitor

pm = currentProgram
listing = pm.getListing()
monitor = ConsoleTaskMonitor()

decomp = DecompInterface()
decomp.openProgram(pm)

# Skip library/external functions
ext_names = set()
for func in listing.getExternalFunctions():
    ext_names.add(func.getName())

funcs = listing.getFunctions(True)
total = funcs.getFunctionCount()
count = 0

print("DECOMPILED_FUNCTIONS_BEGIN")
for func in funcs:
    name = func.getName()
    addr = func.getEntryPoint()
    
    # Skip external/imported
    if name in ext_names:
        continue
    # Skip thunks
    if func.isThunk():
        continue
    # Skip unnamed
    if name.startswith("FUN_") and func.getBody().getNumAddresses() < 5:
        continue
    
    results = decomp.decompileFunction(func, 30, monitor)
    if results and results.getDecompiledFunction():
        code = results.getDecompiledFunction().getC()
        print(f"@ {addr}")
        print(f"// {name}")
        print(code)
        print()
        count += 1

decomp.dispose()
print(f"DECOMPILED_FUNCTIONS_END // {count} functions")
