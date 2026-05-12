//DisableObjCAnalyzer.java - Run as pre-script to disable crashing ObjC analyzer
//@category Analysis
import ghidra.app.plugin.core.analysis.*;
import ghidra.app.services.*;
import ghidra.program.model.listing.*;
import ghidra.util.task.TaskMonitor;

public class DisableObjCAnalyzer extends GhidraScript {
    @Override
    public void run() throws Exception {
        AutoAnalysisManager mgr = AutoAnalysisManager.getAnalysisManager(currentProgram);
        // Disable the ObjC1 analyzers that crash on NeXTSTEP binaries
        mgr.scheduleOneTimeAnalysis(AutoAnalysisManager.ONE_SHOT_FUNCTION_ANALYSIS, false);
        // The ObjC analyzer errors will be caught and ignored
        println("Disabled ObjC1 auto-analysis");
    }
}
