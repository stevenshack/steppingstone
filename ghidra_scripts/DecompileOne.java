//DecompileOne.java - Decompile a single function at given address
//@category Analysis
import ghidra.app.decompiler.*;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.*;
import ghidra.program.model.address.Address;
import ghidra.util.task.ConsoleTaskMonitor;
import ghidra.app.cmd.disassemble.DisassembleCommand;
import ghidra.app.cmd.function.CreateFunctionCmd;

public class DecompileOne extends GhidraScript {
    @Override
    public void run() throws Exception {
        String addrStr = getScriptArgs().length > 0 ? getScriptArgs()[0] : "0x059368";
        Address addr = currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(Long.parseLong(addrStr.substring(2), 16));
        println("Decompiling function at " + addr);

        DisassembleCommand disCmd = new DisassembleCommand(addr, null, true);
        disCmd.applyTo(currentProgram, monitor);

        CreateFunctionCmd fnCmd = new CreateFunctionCmd(addr);
        fnCmd.applyTo(currentProgram, monitor);

        Function func = currentProgram.getListing().getFunctionAt(addr);
        if (func == null) {
            println("No function at " + addr);
            return;
        }

        DecompInterface decomp = new DecompInterface();
        decomp.openProgram(currentProgram);
        DecompileResults res = decomp.decompileFunction(func, 60, monitor);
        if (res != null && res.getDecompiledFunction() != null) {
            println(res.getDecompiledFunction().getC());
        } else {
            println("Decompilation failed");
        }
        decomp.dispose();
    }
}
