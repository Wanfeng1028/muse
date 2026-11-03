// Craft Anything: turn off Ghidra's slowest whole-program analysis passes before a target is
// analysed. Each runs the decompiler over every function in the program, which can take hours on
// a big game; decompiling a chosen function later works that function out by itself.
//@category CraftAnything

import ghidra.app.script.GhidraScript;
import java.util.Map;

public class CraftAnythingFastAnalysis extends GhidraScript {
    private static final String[] SLOW = {
        "Decompiler Switch Analysis",
        "Decompiler Parameter ID",
        "Aggressive Instruction Finder",
        "Embedded Media",
    };

    @Override
    public void run() throws Exception {
        Map<String, String> options = getCurrentAnalysisOptionsAndValues(currentProgram);
        for (String name : SLOW) {
            if (options.containsKey(name)) {
                setAnalysisOption(currentProgram, name, "false");
                println("Craft Anything: skipping " + name);
            }
        }
    }
}
