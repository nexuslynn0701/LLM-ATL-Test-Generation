// ATLRunnerMulti.java
// Multi-output ATL EMFVM runner for transformations such as Ant2Maven.
// Usage:
//   java ATLRunnerMulti
//     <source_model.xmi>
//     <source_metamodel.ecore>
//     <trace_metamodel.ecore>
//     <source_mm_name>
//     <trace_mm_name>
//     <transformation.asm>
//     <trace_output.xmi>
//     (<out_model_name> <target_mm_name> <target_metamodel.ecore> <output_model.xmi>)+

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
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class ATLRunnerMulti {
    static class OutputSpec {
        String outName;
        String mmName;
        String mmPath;
        String outPath;
        IReferenceModel refModel;
        IModel model;
    }

    public static void main(String[] args) {
        if (args.length < 11 || ((args.length - 7) % 4 != 0)) {
            System.err.println("Usage: java ATLRunnerMulti "
                    + "<source_model.xmi> <source_metamodel.ecore> <trace_metamodel.ecore> "
                    + "<source_mm_name> <trace_mm_name> <transformation.asm> <trace_output.xmi> "
                    + "(<out_model_name> <target_mm_name> <target_metamodel.ecore> <output_model.xmi>)+");
            System.exit(1);
        }

        String sourceModelPath     = args[0];
        String sourceMetamodelPath = args[1];
        String traceMetamodelPath  = args[2];
        String sourceMMName        = args[3];
        String traceMMName         = args[4];
        String transformationPath  = args[5];
        String traceOutputPath     = args[6];

        List<OutputSpec> outputs = new ArrayList<OutputSpec>();
        for (int i = 7; i < args.length; i += 4) {
            OutputSpec spec = new OutputSpec();
            spec.outName = args[i];
            spec.mmName  = args[i + 1];
            spec.mmPath  = args[i + 2];
            spec.outPath = args[i + 3];
            outputs.add(spec);
        }

        try {
            ILauncher launcher   = new EMFVMLauncher();
            ModelFactory factory = new EMFModelFactory();
            IInjector injector   = new EMFInjector();
            IExtractor extractor = new EMFExtractor();

            IReferenceModel sourceMM = factory.newReferenceModel();
            injector.inject(sourceMM, new File(sourceMetamodelPath).toURI().toString());

            IReferenceModel traceMM = factory.newReferenceModel();
            injector.inject(traceMM, new File(traceMetamodelPath).toURI().toString());

            IModel sourceModel = factory.newModel(sourceMM);
            injector.inject(sourceModel, new File(sourceModelPath).toURI().toString());

            IModel traceModel = factory.newModel(traceMM);

            for (OutputSpec spec : outputs) {
                spec.refModel = factory.newReferenceModel();
                injector.inject(spec.refModel, new File(spec.mmPath).toURI().toString());
                spec.model = factory.newModel(spec.refModel);
            }

            launcher.initialize(new HashMap<String, Object>());
            launcher.addInModel(sourceModel, "IN", sourceMMName);
            for (OutputSpec spec : outputs) {
                launcher.addOutModel(spec.model, spec.outName, spec.mmName);
            }
            launcher.addOutModel(traceModel, "TM", traceMMName);

            Map<String, Object> parameters = new HashMap<String, Object>();
            parameters.put("allowInterModelReferences", Boolean.TRUE);

            launcher.launch(
                ILauncher.RUN_MODE,
                new NullProgressMonitor(),
                parameters,
                new FileInputStream(new File(transformationPath))
            );

            for (OutputSpec spec : outputs) {
                new File(spec.outPath).getParentFile().mkdirs();
                extractor.extract(spec.model, new File(spec.outPath).toURI().toString());
            }
            new File(traceOutputPath).getParentFile().mkdirs();
            extractor.extract(traceModel, new File(traceOutputPath).toURI().toString());

            EMFModelFactory emfFactory = (EMFModelFactory) factory;
            emfFactory.unload((EMFModel) sourceModel);
            emfFactory.unload((EMFModel) traceModel);
            emfFactory.unload((EMFReferenceModel) sourceMM);
            emfFactory.unload((EMFReferenceModel) traceMM);

            for (OutputSpec spec : outputs) {
                emfFactory.unload((EMFModel) spec.model);
                emfFactory.unload((EMFReferenceModel) spec.refModel);
            }

            System.out.println("SUCCESS");
            System.out.println("  Source model : " + sourceModelPath);
            System.out.println("  Trace model  : " + traceOutputPath);
            for (OutputSpec spec : outputs) {
                System.out.println("  Output " + spec.outName + " : " + spec.outPath);
            }

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
