import org.eclipse.m2m.atl.core.IInjector;
import org.eclipse.m2m.atl.core.IModel;
import org.eclipse.m2m.atl.core.IReferenceModel;
import org.eclipse.m2m.atl.core.ModelFactory;
import org.eclipse.m2m.atl.core.emf.EMFInjector;
import org.eclipse.m2m.atl.core.emf.EMFModel;
import org.eclipse.m2m.atl.core.emf.EMFModelFactory;

import org.eclipse.emf.ecore.EObject;
import org.eclipse.emf.ecore.resource.Resource;
import java.io.File;
import java.util.Iterator;

/**
 * Count containment-tree EObjects of source models loaded EXACTLY like the
 * original experiment did (ATL EMFModelFactory + EMFInjector), which is more
 * lenient than a strict XMIResource load.
 *
 * Usage: java AtlModeSizeCount <metamodel.ecore> <model.xmi> [more models...]
 */
public class AtlModeSizeCount {
    public static void main(String[] args) throws Exception {
        ModelFactory factory = new EMFModelFactory();
        IInjector injector = new EMFInjector();
        IReferenceModel mm = factory.newReferenceModel();
        injector.inject(mm, new File(args[0]).getAbsolutePath());

        for (int i = 1; i < args.length; i++) {
            try {
                IModel model = factory.newModel(mm);
                injector.inject(model, new File(args[i]).getAbsolutePath());
                Resource r = ((EMFModel) model).getResource();
                int n = 0;
                for (Iterator<EObject> it = r.getAllContents(); it.hasNext(); ) {
                    it.next();
                    n++;
                }
                int errs = r.getErrors().size();
                System.out.println(args[i] + "\t" + (errs == 0 ? "OK" : "OK_WITH_" + errs + "_ERRORS") + "\t" + n);
            } catch (Exception e) {
                String msg = e.getMessage() == null ? e.toString() : e.getMessage().replace("\t", " ").replace("\n", " ");
                System.out.println(args[i] + "\tFAIL\t" + msg);
            }
        }
    }
}
