//DisableObjCAnalyzer.java - Run as pre-script to disable the crashing
//NeXTSTEP ObjC1 analyzers before Ghidra auto-analysis begins.
//@category Analysis

import ghidra.app.plugin.core.analysis.AutoAnalysisManager;
import ghidra.app.services.Analyzer;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.Program;
import ghidra.util.task.TaskMonitor;

public class DisableObjCAnalyzer extends GhidraScript {
    @Override
    public void run() throws Exception {
        AutoAnalysisManager mgr = AutoAnalysisManager.getAnalysisManager(currentProgram);
        if (mgr == null) {
            println("ERROR: Could not get AutoAnalysisManager");
            return;
        }

        String[] crashy = {
            "ObjectiveC1 Class Analyzer",
            "ObjectiveC1 Type Encodings",
        };

        int disabled = 0;
        for (Analyzer a : mgr.getAnalyzers()) {
            for (String name : crashy) {
                if (a.getName().equals(name)) {
                    mgr.setAnalyzerEnabled(name, false);
                    println("Disabled: " + name);
                    disabled++;
                }
            }
        }

        if (disabled == 0) {
            println("Warning: Could not find ObjC1 analyzers to disable");
            // Fallback: list all analyzers for debugging
            for (Analyzer a : mgr.getAnalyzers()) {
                println("  Available analyzer: " + a.getName());
            }
        }
    }
}
