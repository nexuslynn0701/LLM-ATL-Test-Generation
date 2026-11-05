// ATLAsmCompilerRunner.java
// Compile classic ATL .atl files to .asm using Atl2006Compiler.

import org.eclipse.m2m.atl.engine.compiler.CompileTimeError;
import org.eclipse.m2m.atl.engine.compiler.atl2006.Atl2006Compiler;

import java.io.File;
import java.io.FileInputStream;

public class ATLAsmCompilerRunner {

    public static void main(String[] args) throws Exception {

        if (args.length < 1) {
            System.err.println("Usage: java ATLAsmCompilerRunner <file.atl> [output.asm]");
            System.exit(1);
        }

        String atlPath = args[0];
        String asmPath = args.length >= 2
                ? args[1]
                : atlPath.replace(".atl", ".asm");

        File atlFile = new File(atlPath);
        if (!atlFile.exists()) {
            System.err.println("[ERROR] ATL file not found: " + atlPath);
            System.exit(1);
        }

        System.out.println("[INFO] Compiling ATL to ASM");
        System.out.println("[INFO] Input : " + atlPath);
        System.out.println("[INFO] Output: " + asmPath);

        Atl2006Compiler compiler = new Atl2006Compiler();

        CompileTimeError[] errors;
        try (FileInputStream fis = new FileInputStream(atlFile)) {
            errors = compiler.compile(fis, asmPath);
        }

        if (errors != null && errors.length > 0) {
            System.err.println("[WARN] Compilation finished with " + errors.length + " error(s):");
            for (CompileTimeError e : errors) {
                System.err.println("  - " + e);
            }
            System.exit(2);
        }

        File outFile = new File(asmPath);
        if (!outFile.exists()) {
            System.err.println("[ERROR] ASM file was not created: " + asmPath);
            System.exit(3);
        }

        System.out.println("[SUCCESS] Compiled -> " + asmPath);
        System.out.println("[SIZE] " + outFile.length() + " bytes");
    }
}