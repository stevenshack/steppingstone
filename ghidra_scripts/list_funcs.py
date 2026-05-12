# List all functions and symbols (Jython-compatible)
from ghidra.program.model.listing import Function

pm = currentProgram
listing = pm.getListing()
sym_table = pm.getSymbolTable()

print("SYMBOLS_BEGIN")
syms = sym_table.getAllSymbols(True)
while syms.hasNext():
    sym = syms.next()
    addr = sym.getAddress()
    name = sym.getName()
    print("0x%06x %s" % (addr.getOffset(), name))
print("SYMBOLS_END")

print("\nFUNCTIONS_BEGIN")
funcs = listing.getFunctions(True)
count = 0
while funcs.hasNext():
    func = funcs.next()
    name = func.getName()
    addr = func.getEntryPoint()
    body = func.getBody()
    print("0x%06x %s size=%s" % (addr.getOffset(), name, body.getNumAddresses()))
    count += 1
print("FUNCTIONS_END (%d total)" % count)
