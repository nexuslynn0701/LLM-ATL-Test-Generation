// ATLRunner.java
// Uses EMFVMLauncher + .asm (same approach as SBFL project ATL_EMF_Launcher)

import org.eclipse.core.runtime.NullProgressMonitor;
import org.eclipse.m2m.atl.core.ATLCoreException;
import org.eclipse.m2m.atl.core.IExtractor;
import org.eclipse.m2m.atl.core.IInjector;
import org.eclipse.m2m.atl.core.IModel;
import org.eclipse.m2m.atl.core.IReferenceModel;
import org.eclipse.m2m.atl.core.ModelFactory;
import org.eclipse.m2m.atl.core.emf.EMFExtractor;
import org.eclipse.m2m.atl.core.emf.EMFInjector;
import org.eclipse.m2m.atl.core.emf.EMFModel;
import org.eclipse.m2m.atl.core.emf.EMFModelFactory;
import org.eclipse.m2m.atl.core.emf.EMFReferenceModel;
import org.eclipse.m2m.atl.core.launch.ILauncher;
import org.eclipse.m2m.atl.engine.emfvm.launch.EMFVMLauncher;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileNotFoundException;
import java.util.HashMap;
import java.util.Map;

public class ATLRunner {

    public static void main(String[] args) {

        if (args.length != 9) {
            System.err.println("Usage: java ATLRunner "
                    + "<source_model.xmi> "
                    + "<source_metamodel.ecore> "
                    + "<target_metamodel.ecore> "
                    + "<trace_metamodel.ecore> "
                    + "<source_mm_name> "
                    + "<target_mm_name> "
                    + "<trace_mm_name> "
                    + "<transformation.asm> "
                    + "<output_model.xmi>");
            System.err.println("");
            System.err.println("Example:");
            System.err.println("  java -cp \"lib/*:lib\" ATLRunner "
                    + "source.xmi BibTeX.ecore DocBook.ecore Trace.ecore "
                    + "BibTeX DocBook TMM "
                    + "BibTeX2DocBook.asm output.xmi");
            System.exit(1);
        }

        String sourceModelPath     = args[0];
        String sourceMetamodelPath = args[1];
        String targetMetamodelPath = args[2];
        String traceMetamodelPath  = args[3];
        String sourceMMName        = args[4];
        String targetMMName        = args[5];
        String traceMMName         = args[6];
        String transformationPath  = args[7];
        String outputModelPath     = args[8];

        String traceOutputPath = outputModelPath.replace(".xmi", "_trace.xmi");

        try {
            // ── Initialize launcher (EMF VM, not EMFTVM) ─────────────────
            ILauncher launcher     = new EMFVMLauncher();
            ModelFactory factory   = new EMFModelFactory();
            IInjector injector     = new EMFInjector();
            IExtractor extractor   = new EMFExtractor();

            // ── Load metamodels ───────────────────────────────────────────
            IReferenceModel sourceMM = factory.newReferenceModel();
            injector.inject(sourceMM,
                new File(sourceMetamodelPath).toURI().toString());

            IReferenceModel targetMM = factory.newReferenceModel();
            injector.inject(targetMM,
                new File(targetMetamodelPath).toURI().toString());

            IReferenceModel traceMM = factory.newReferenceModel();
            injector.inject(traceMM,
                new File(traceMetamodelPath).toURI().toString());

            System.out.println("[INFO] Metamodels loaded.");

            // ── Load source model ─────────────────────────────────────────
            IModel sourceModel = factory.newModel(sourceMM);
            injector.inject(sourceModel,
                new File(sourceModelPath).toURI().toString());

            // ── Create output models ──────────────────────────────────────
            IModel targetModel = factory.newModel(targetMM);
            IModel traceModel  = factory.newModel(traceMM);

            // ── Set up transformation ─────────────────────────────────────
            launcher.initialize(new HashMap<String, Object>());
            launcher.addInModel(sourceModel,  "IN",  sourceMMName);
            launcher.addOutModel(targetModel, "OUT", targetMMName);
            launcher.addOutModel(traceModel,  "TM",  traceMMName);

            Map<String, Object> parameters = new HashMap<String, Object>();
            parameters.put("allowInterModelReferences", Boolean.TRUE);

            System.out.println("[INFO] Running transformation: " + transformationPath);

            // ── Execute transformation ────────────────────────────────────
            launcher.launch(ILauncher.RUN_MODE,
                new NullProgressMonitor(),
                parameters,
                new FileInputStream(new File(transformationPath)));

            // ── Save output models ────────────────────────────────────────
            new File(outputModelPath).getParentFile().mkdirs();
            extractor.extract(targetModel, new File(outputModelPath).toURI().toString());
            extractor.extract(traceModel,  new File(traceOutputPath).toURI().toString());

            // ── Unload models ─────────────────────────────────────────────
            EMFModelFactory emfFactory = (EMFModelFactory) factory;
            emfFactory.unload((EMFModel) sourceModel);
            emfFactory.unload((EMFModel) targetModel);
            emfFactory.unload((EMFModel) traceModel);
            emfFactory.unload((EMFReferenceModel) sourceMM);
            emfFactory.unload((EMFReferenceModel) targetMM);
            emfFactory.unload((EMFReferenceModel) traceMM);

            System.out.println("SUCCESS");
            System.out.println("  Source model : " + sourceModelPath);
            System.out.println("  Output model : " + outputModelPath);
            System.out.println("  Trace model  : " + traceOutputPath);

        } catch (ATLCoreException e) {
            System.err.println("[ERROR] ATL core exception.");
            e.printStackTrace();
            System.exit(2);
        } catch (FileNotFoundException e) {
            System.err.println("[ERROR] File not found: " + e.getMessage());
            e.printStackTrace();
            System.exit(2);
        }
    }
}






