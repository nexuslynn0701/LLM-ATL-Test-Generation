import org.eclipse.emf.common.util.URI;
import org.eclipse.emf.ecore.EObject;
import org.eclipse.emf.ecore.EReference;
import org.eclipse.emf.ecore.EPackage;
import org.eclipse.emf.ecore.resource.*;
import org.eclipse.emf.ecore.resource.impl.ResourceSetImpl;
import org.eclipse.emf.ecore.util.EcoreUtil;
import org.eclipse.emf.ecore.xmi.impl.EcoreResourceFactoryImpl;
import org.eclipse.emf.ecore.xmi.impl.XMIResourceFactoryImpl;
import java.util.*;

public class EmfDump {
    public static void main(String[] args) throws Exception {
        ResourceSet rs = new ResourceSetImpl();
        rs.getResourceFactoryRegistry().getExtensionToFactoryMap().put("ecore", new EcoreResourceFactoryImpl());
        rs.getResourceFactoryRegistry().getExtensionToFactoryMap().put("*", new XMIResourceFactoryImpl());
        Resource mmRes = rs.getResource(URI.createFileURI(args[0]), true);
        for (Iterator<EObject> it = mmRes.getAllContents(); it.hasNext(); ) {
            EObject o = it.next();
            if (o instanceof EPackage) {
                EPackage p = (EPackage) o;
                if (!rs.getPackageRegistry().containsKey(p.getNsURI())) rs.getPackageRegistry().put(p.getNsURI(), p);
            }
        }
        Resource r = rs.createResource(URI.createFileURI(args[1]));
        r.load(Collections.emptyMap());
        EcoreUtil.resolveAll(r);
        System.out.println("errors: " + r.getErrors().size());
        for (EObject root : r.getContents()) dump(root, 0);
    }
    static void dump(EObject o, int d) {
        System.out.println("  ".repeat(d) + o.eClass().getName());
        for (EReference ref : o.eClass().getEAllContainments()) {
            Object val = o.eGet(ref);
            if (val instanceof Collection) {
                for (Object c : (Collection<?>) val) dump((EObject) c, d + 1);
            } else if (val instanceof EObject) {
                dump((EObject) val, d + 1);
            }
        }
    }
}
