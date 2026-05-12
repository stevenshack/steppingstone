//DecompileToObjC.java - Decompile all functions and output annotated bodies
//@category Analysis

import ghidra.app.decompiler.*;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.*;
import ghidra.util.task.ConsoleTaskMonitor;

public class DecompileToObjC extends GhidraScript {
    @Override
    public void run() throws Exception {
        ConsoleTaskMonitor monitor = new ConsoleTaskMonitor();
        DecompInterface decomp = new DecompInterface();
        decomp.openProgram(currentProgram);
        
        Listing listing = currentProgram.getListing();
        int total = 0, okay = 0;
        
        Function func = getFirstFunction();
        while (func != null) {
            total++;
            long addr = func.getEntryPoint().getOffset();
            String name = func.getName();
            
            if (!func.isThunk() && !name.startsWith("FUN_") && func.getBody().getNumAddresses() >= 3) {
                try {
                    DecompileResults res = decomp.decompileFunction(func, 60, monitor);
                    if (res != null && res.getDecompiledFunction() != null) {
                        String code = res.getDecompiledFunction().getC();
                        if (code != null && code.length() > 10) {
                            println("FUNC 0x" + Long.toHexString(addr) + " " + name);
                            println(code);
                            println("---");
                            okay++;
                        }
                    }
                } catch (Exception e) {
                    // Skip functions that fail to decompile
                }
            }
            func = getFunctionAfter(func);
        }
        
        decomp.dispose();
        println("DECOMPILED_OBJC_END // " + okay + "/" + total + " functions");
    }
}
