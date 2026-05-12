//DecompileBatch.java - Decompile all functions at given addresses
//@category Analysis
import ghidra.app.decompiler.*;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.*;
import ghidra.program.model.address.Address;
import ghidra.util.task.ConsoleTaskMonitor;
import ghidra.app.cmd.disassemble.DisassembleCommand;
import ghidra.app.cmd.function.CreateFunctionCmd;
import java.io.*;
import java.util.*;

public class DecompileBatch extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length < 1) {
            println("ERROR: Usage: DecompileBatch.java <addr_file>");
            return;
        }
        String addrFile = args[0];
        List<String> addrs = new ArrayList<>();
        BufferedReader br = new BufferedReader(new FileReader(addrFile));
        String line;
        while ((line = br.readLine()) != null) {
            line = line.trim();
            if (!line.isEmpty() && !line.startsWith("#")) {
                addrs.add(line);
            }
        }
        br.close();

        DecompInterface decomp = new DecompInterface();
        decomp.openProgram(currentProgram);
        int ok = 0;

        for (String lineStr : addrs) {
            if (monitor.isCancelled()) break;
            String[] parts = lineStr.split(" ", 2);
            String addrStr = parts[0];
            String methodName = parts.length > 1 ? parts[1] : "";
            long addrVal = Long.parseLong(addrStr.startsWith("0x") ? addrStr.substring(2) : addrStr, 16);
            Address addr = currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(addrVal);

            if (currentProgram.getListing().getFunctionAt(addr) == null) {
                DisassembleCommand disCmd = new DisassembleCommand(addr, null, true);
                disCmd.applyTo(currentProgram, monitor);
                CreateFunctionCmd fnCmd = new CreateFunctionCmd(addr);
                fnCmd.applyTo(currentProgram, monitor);
            }

            Function func = currentProgram.getListing().getFunctionAt(addr);
            if (func == null) continue;

            DecompileResults res = decomp.decompileFunction(func, 60, monitor);
            if (res != null && res.getDecompiledFunction() != null) {
                String code = res.getDecompiledFunction().getC();
                if (code != null) {
                    println("FUNC_BEGIN 0x" + addrStr + " " + methodName);
                    println(code);
                    println("FUNC_END");
                    ok++;
                }
            }
        }

        decomp.dispose();
        println("// DECOMPILED " + ok + "/" + addrs.size() + " functions");
    }
}
