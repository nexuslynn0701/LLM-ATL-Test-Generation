import org.eclipse.emf.common.util.URI;
import org.eclipse.emf.ecore.EObject;
import org.eclipse.emf.ecore.EPackage;
import org.eclipse.emf.ecore.resource.Resource;
import org.eclipse.emf.ecore.resource.ResourceSet;
import org.eclipse.emf.ecore.resource.impl.ResourceSetImpl;
import org.eclipse.emf.ecore.util.EcoreUtil;
import org.eclipse.emf.ecore.xmi.impl.EcoreResourceFactoryImpl;
import org.eclipse.emf.ecore.xmi.impl.XMIResourceFactoryImpl;

import java.util.Collections;
import java.util.HashMap;
import java.util.Iterator;
import java.util.Map;

/**
 * Arbitration tool: strict EMF load + containment-tree EObject count.
 * Args: <metamodel.ecore> <model.xmi> [...more models]
 */
public class EmfSizeCount {
    public static void main(String[] args) throws Exception {
        ResourceSet rs = new ResourceSetImpl();
        rs.getResourceFactoryRegistry().getExtensionToFactoryMap()
          .put("ecore", new EcoreResourceFactoryImpl());
        rs.getResourceFactoryRegistry().getExtensionToFactoryMap()
          .put("*", new XMIResourceFactoryImpl());

        Resource mmRes = rs.getResource(URI.createFileURI(args[0]), true);
        for (EObject o : mmRes.getContents()) {
            if (o instanceof EPackage) {
                EPackage pkg = (EPackage) o;
                // XMI-wrapped ecores (like Grafcet/Ant) expose nested packages
                registerAll(pkg, rs);
            } else if (o instanceof org.eclipse.emf.ecore.xmi.XMIResource) {
                // ignore
            }
        }
        // XMI-wrapped ecore: iterate roots
        for (Iterator<EObject> it = mmRes.getAllContents(); it.hasNext(); ) {
            EObject o = it.next();
            if (o instanceof EPackage && !rs.getPackageRegistry().containsKey(((EPackage) o).getNsURI())) {
                rs.getPackageRegistry().put(((EPackage) o).getNsURI(), (EPackage) o);
            }
        }

        for (int i = 1; i < args.length; i++) {
            Resource r = rs.createResource(URI.createFileURI(args[i]));
            Map<Object, Object> opts = new HashMap<>();
            try {
                r.load(opts);
                EcoreUtil.resolveAll(r);
                if (!r.getErrors().isEmpty()) {
                    System.out.println(args[i] + "\tLOAD_ERRORS(" + r.getErrors().size() + ")\t"
                                       + r.getErrors().get(0).getMessage());
                    continue;
                }
                int reachable = 0;
                for (Iterator<EObject> it = r.getAllContents(); it.hasNext(); ) {
                    it.next();
                    reachable++;
                }
                System.out.println(args[i] + "\tOK\t" + reachable);
            } catch (Exception e) {
                String msg = e.getMessage() == null ? e.toString() : e.getMessage().replace("\t", " ").replace("\n", " ");
                System.out.println(args[i] + "\tEXCEPTION\t" + msg);
            }
        }
    }

    static void registerAll(EPackage pkg, ResourceSet rs) {
        rs.getPackageRegistry().put(pkg.getNsURI(), pkg);
        for (EPackage sub : pkg.getESubpackages()) {
            registerAll(sub, rs);
        }
    }
}
