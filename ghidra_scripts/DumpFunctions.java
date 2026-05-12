//DumpFunctions.java - List all function addresses and names
//@category Analysis

import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.Function;

public class DumpFunctions extends GhidraScript {
    @Override
    public void run() throws Exception {
        Function func = getFirstFunction();
        int count = 0;
        println("FUNCTIONS_BEGIN");
        while (func != null) {
            String name = func.getName();
            long addr = func.getEntryPoint().getOffset();
            println(String.format("0x%06x %s", addr, name));
            count++;
            func = getFunctionAfter(func);
        }
        println("FUNCTIONS_END (" + count + " total)");
    }
}
