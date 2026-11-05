import org.eclipse.emf.common.util.TreeIterator;
import org.eclipse.emf.common.util.URI;
import org.eclipse.emf.ecore.EClass;
import org.eclipse.emf.ecore.EClassifier;
import org.eclipse.emf.ecore.EObject;
import org.eclipse.emf.ecore.EPackage;
import org.eclipse.emf.ecore.resource.Resource;
import org.eclipse.emf.ecore.resource.ResourceSet;
import org.eclipse.emf.ecore.resource.impl.ResourceSetImpl;
import org.eclipse.emf.ecore.xmi.impl.EcoreResourceFactoryImpl;
import org.eclipse.emf.ecore.xmi.impl.XMIResourceFactoryImpl;
import org.eclipse.ocl.Query;
import org.eclipse.ocl.ecore.EcoreEnvironmentFactory;
import org.eclipse.ocl.ecore.OCL;
import org.eclipse.ocl.ecore.OCLExpression;
import org.eclipse.ocl.helper.OCLHelper;

import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class OCLAssertionBatchEvaluator {
    private static void registerPackage(EPackage pkg) {
        EPackage.Registry.INSTANCE.put(pkg.getNsURI(), pkg);
        for (EPackage child : pkg.getESubpackages()) registerPackage(child);
    }

    private static void initializeEmptyExtents(
        Map<EClass, Set<EObject>> extents, EPackage pkg
    ) {
        for (EClassifier classifier : pkg.getEClassifiers()) {
            if (classifier instanceof EClass) {
                extents.putIfAbsent((EClass) classifier, new HashSet<EObject>());
            }
        }
        for (EPackage child : pkg.getESubpackages()) {
            initializeEmptyExtents(extents, child);
        }
    }

    private static void addExtent(Map<EClass, Set<EObject>> extents, EObject obj) {
        EClass cls = obj.eClass();
        extents.computeIfAbsent(cls, key -> new HashSet<EObject>()).add(obj);
        for (EClass parent : cls.getEAllSuperTypes()) {
            extents.computeIfAbsent(parent, key -> new HashSet<EObject>()).add(obj);
        }
    }

    private static String clean(Object value) {
        return String.valueOf(value).replace('\t', ' ').replace('\n', ' ');
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 3) {
            System.err.println("Usage: java OCLAssertionBatchEvaluator "
                + "<joint.ecore> <joint.xmi> <assertions.tsv>");
            System.exit(1);
        }

        ResourceSet rs = new ResourceSetImpl();
        rs.getResourceFactoryRegistry().getExtensionToFactoryMap()
            .put("ecore", new EcoreResourceFactoryImpl());
        rs.getResourceFactoryRegistry().getExtensionToFactoryMap()
            .put("xmi", new XMIResourceFactoryImpl());

        Resource mm = rs.getResource(
            URI.createFileURI(new File(args[0]).getAbsolutePath()), true
        );
        for (EObject root : mm.getContents()) {
            if (root instanceof EPackage) registerPackage((EPackage) root);
        }

        Resource model = rs.getResource(
            URI.createFileURI(new File(args[1]).getAbsolutePath()), true
        );
        if (model.getContents().isEmpty()) {
            throw new IllegalArgumentException("Joint model has no root objects");
        }

        Map<EClass, Set<EObject>> extents = new HashMap<EClass, Set<EObject>>();
        for (EObject root : mm.getContents()) {
            if (root instanceof EPackage) {
                initializeEmptyExtents(extents, (EPackage) root);
            }
        }
        for (EObject root : model.getContents()) {
            addExtent(extents, root);
            TreeIterator<EObject> it = root.eAllContents();
            while (it.hasNext()) addExtent(extents, it.next());
        }

        EObject context = model.getContents().get(0);
        OCL ocl = OCL.newInstance(EcoreEnvironmentFactory.INSTANCE);
        ocl.setExtentMap(extents);

        List<String> lines = Files.readAllLines(
            new File(args[2]).toPath(), StandardCharsets.UTF_8
        );

        for (String line : lines) {
            if (line.trim().isEmpty()) continue;
            String[] fields = line.split("\\t", 2);
            String id = fields[0];
            if (fields.length != 2) {
                System.out.println(id + "\tERROR\tmissing expression");
                continue;
            }

            try {
                OCLHelper helper = ocl.createOCLHelper();
                helper.setContext(context.eClass());
                OCLExpression expression =
                    (OCLExpression) helper.createQuery(fields[1]);
                Query query = ocl.createQuery(expression);
                Object value = query.evaluate(context);

                if (Boolean.TRUE.equals(value)) {
                    System.out.println(id + "\tPASS\ttrue");
                } else if (Boolean.FALSE.equals(value)) {
                    System.out.println(id + "\tFAIL\tfalse");
                } else {
                    System.out.println(id + "\tINVALID\t" + clean(value));
                }
            } catch (Exception exc) {
                System.out.println(id + "\tERROR\t" + clean(exc));
            }
        }

        ocl.dispose();
    }
}
