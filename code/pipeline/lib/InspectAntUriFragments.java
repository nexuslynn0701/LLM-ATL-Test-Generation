import java.io.File;
import java.util.ArrayList;
import java.util.List;

import org.eclipse.emf.common.util.TreeIterator;
import org.eclipse.emf.common.util.URI;
import org.eclipse.emf.ecore.EObject;
import org.eclipse.emf.ecore.EPackage;
import org.eclipse.emf.ecore.EStructuralFeature;
import org.eclipse.emf.ecore.resource.Resource;
import org.eclipse.emf.ecore.resource.ResourceSet;
import org.eclipse.emf.ecore.resource.impl.ResourceSetImpl;
import org.eclipse.emf.ecore.xmi.impl.EcoreResourceFactoryImpl;
import org.eclipse.emf.ecore.xmi.impl.XMIResourceFactoryImpl;

public class InspectAntUriFragments {
    private static String containmentPath(EObject obj) {
        List<String> parts = new ArrayList<>();
        EObject cur = obj;

        while (cur != null) {
            String part = cur.eClass().getName();
            EObject parent = cur.eContainer();

            if (parent != null) {
                EStructuralFeature f = cur.eContainingFeature();
                part = f.getName() + ":" + part;
            }

            parts.add(0, part);
            cur = parent;
        }

        return String.join("/", parts);
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            System.err.println("Usage: InspectAntUriFragments <Ant.ecore> <source.xmi>");
            System.exit(2);
        }

        ResourceSet rs = new ResourceSetImpl();
        rs.getResourceFactoryRegistry().getExtensionToFactoryMap()
            .put("ecore", new EcoreResourceFactoryImpl());
        rs.getResourceFactoryRegistry().getExtensionToFactoryMap()
            .put("xmi", new XMIResourceFactoryImpl());

        Resource mm = rs.getResource(
            URI.createFileURI(new File(args[0]).getAbsolutePath()), true);
        EPackage pkg = (EPackage) mm.getContents().get(0);
        rs.getPackageRegistry().put(pkg.getNsURI(), pkg);

        System.out.println("package nsURI=" + pkg.getNsURI());

        Resource source = rs.getResource(
            URI.createFileURI(new File(args[1]).getAbsolutePath()), true);

        List<EObject> objects = new ArrayList<>(source.getContents());
        TreeIterator<EObject> it = source.getAllContents();
        while (it.hasNext()) {
            objects.add(it.next());
        }

        for (EObject obj : objects) {
            String path = containmentPath(obj);
            try {
                String fragment = source.getURIFragment(obj);
                System.out.println("OK   class=" + obj.eClass().getName()
                    + " path=" + path
                    + " fragment=" + fragment);
            } catch (Throwable e) {
                System.out.println("FAIL class=" + obj.eClass().getName()
                    + " path=" + path
                    + " error=" + e);
            }
        }
    }
}
