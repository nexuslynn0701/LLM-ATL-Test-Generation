// ATLCompilerRunner.java
// 将 .atl 源文件编译为 .emftvm，使用 AtlToEmftvmCompiler API

import org.eclipse.emf.ecore.resource.Resource;
import org.eclipse.emf.ecore.resource.ResourceSet;
import org.eclipse.emf.ecore.resource.impl.ResourceSetImpl;
import org.eclipse.emf.ecore.xmi.impl.EcoreResourceFactoryImpl;
import org.eclipse.emf.ecore.xmi.impl.XMIResourceFactoryImpl;
import org.eclipse.m2m.atl.emftvm.compiler.AtlResourceFactoryImpl;
import org.eclipse.m2m.atl.emftvm.compiler.AtlToEmftvmCompiler;
import org.eclipse.m2m.atl.emftvm.impl.resource.EMFTVMResourceFactoryImpl;
import org.eclipse.m2m.atl.engine.compiler.CompileTimeError;

import java.io.File;
import java.io.FileInputStream;

public class ATLCompilerRunner {

    public static void main(String[] args) throws Exception {

        if (args.length < 1) {
            System.err.println("Usage: java ATLCompilerRunner <file.atl> [output.emftvm]");
            System.exit(1);
        }

        String atlPath    = args[0];
        String emftvmPath = args.length >= 2
                ? args[1]
                : atlPath.replace(".atl", ".emftvm");

        File atlFile = new File(atlPath);
        if (!atlFile.exists()) {
            System.err.println("[ERROR] ATL file not found: " + atlPath);
            System.exit(1);
        }

        System.out.println("[INFO] Compiling : " + atlPath);
        System.out.println("[INFO] Output    : " + emftvmPath);

        Resource.Factory.Registry reg = Resource.Factory.Registry.INSTANCE;
        reg.getExtensionToFactoryMap().put("ecore",  new EcoreResourceFactoryImpl());
        reg.getExtensionToFactoryMap().put("xmi",    new XMIResourceFactoryImpl());
        reg.getExtensionToFactoryMap().put("emftvm", new EMFTVMResourceFactoryImpl());
        reg.getExtensionToFactoryMap().put("atl",    new AtlResourceFactoryImpl());

        AtlToEmftvmCompiler compiler = new AtlToEmftvmCompiler();

        CompileTimeError[] errors;
        try (FileInputStream fis = new FileInputStream(atlFile)) {
            errors = compiler.compile(fis, emftvmPath);
        }

        if (errors != null && errors.length > 0) {
            System.err.println("[WARN] Compilation finished with " + errors.length + " error(s):");
            for (CompileTimeError e : errors) {
                System.err.println("  - " + e);
            }
            System.exit(2);
        }

        File outFile = new File(emftvmPath);
        if (!outFile.exists()) {
            System.err.println("[ERROR] Output file was not created: " + emftvmPath);
            System.exit(3);
        }

        System.out.println("[SUCCESS] Compiled -> " + emftvmPath);
        System.out.println("[SIZE]    " + outFile.length() + " bytes");
    }
}
