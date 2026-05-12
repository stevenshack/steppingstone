//ListAllFuncs.java - Simple function lister using stdout
//@category Analysis

import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.*;

public class ListAllFuncs extends GhidraScript {
    @Override
    public void run() throws Exception {
        int count = 0;
        Function func = getFirstFunction();
        while (func != null) {
            String name = func.getName();
            long addr = func.getEntryPoint().getOffset();
            if (!func.isThunk() && !name.startsWith("FUN_")) {
                System.out.println("FUNC 0x" + Long.toHexString(addr) + " " + name);
                count++;
            }
            func = getFunctionAfter(func);
        }
        System.out.println("FUNCTIONS_END (" + count + " total)");
    }
}
