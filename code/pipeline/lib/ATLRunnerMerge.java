import org.eclipse.core.runtime.NullProgressMonitor;
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
import java.util.HashMap;
import java.util.Map;

public class ATLRunnerMerge {
    public static void main(String[] args) throws Exception {
        if (args.length != 10) {
            System.err.println("Usage: java ATLRunnerMerge "
                + "<in1.xmi> <in1.ecore> <in2.xmi> <in2.ecore> "
                + "<out.ecore> <in1_mm_name> <in2_mm_name> <out_mm_name> "
                + "<merge.asm> <out.xmi>");
            System.exit(1);
        }

        ModelFactory factory = new EMFModelFactory();
        IInjector injector = new EMFInjector();
        IExtractor extractor = new EMFExtractor();

        IReferenceModel in1MM = factory.newReferenceModel();
        IReferenceModel in2MM = factory.newReferenceModel();
        IReferenceModel outMM = factory.newReferenceModel();

        injector.inject(in1MM, new File(args[1]).getAbsolutePath());
        injector.inject(in2MM, new File(args[3]).getAbsolutePath());
        injector.inject(outMM, new File(args[4]).getAbsolutePath());

        IModel in1 = factory.newModel(in1MM);
        IModel in2 = factory.newModel(in2MM);
        IModel out = factory.newModel(outMM);

        injector.inject(in1, new File(args[0]).getAbsolutePath());
        injector.inject(in2, new File(args[2]).getAbsolutePath());

        ILauncher launcher = new EMFVMLauncher();
        launcher.initialize(new HashMap<String, Object>());
        launcher.addInModel(in1, "IN1", args[5]);
        launcher.addInModel(in2, "IN2", args[6]);
        launcher.addOutModel(out, "OUT", args[7]);

        Map<String, Object> parameters = new HashMap<String, Object>();
        parameters.put("allowInterModelReferences", Boolean.TRUE);

        launcher.launch(
            ILauncher.RUN_MODE,
            new NullProgressMonitor(),
            parameters,
            new FileInputStream(new File(args[8]))
        );

        File output = new File(args[9]).getAbsoluteFile();
        output.getParentFile().mkdirs();
        extractor.extract(out, output.getAbsolutePath());

        EMFModelFactory emfFactory = (EMFModelFactory) factory;
        emfFactory.unload((EMFModel) in1);
        emfFactory.unload((EMFModel) in2);
        emfFactory.unload((EMFModel) out);
        emfFactory.unload((EMFReferenceModel) in1MM);
        emfFactory.unload((EMFReferenceModel) in2MM);
        emfFactory.unload((EMFReferenceModel) outMM);

        System.out.println("SUCCESS");
        System.out.println("  Joint model: " + output);
    }
}
