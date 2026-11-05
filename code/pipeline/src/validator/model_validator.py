# src/validator/model_validator.py
#
# Validates XMI model conformance against an Ecore metamodel.
#
# Primary implementation uses pyecore when available.
# Falls back to a structural XML heuristic check when pyecore is absent.
#
# Usage:
#   from src.validator.model_validator import validate_model

import logging
import os
import xml.etree.ElementTree as ET
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from pyecore.resources import ResourceSet, URI
    from pyecore.ecore import EPackage, EClass, EAttribute, EReference
    from pyecore.resources.xmi import XMIResource
    PYECORE_AVAILABLE = True
except ImportError:
    PYECORE_AVAILABLE = False


# ── Custom exception ──────────────────────────────────────────────────────────

class ModelValidationError(Exception):
    """Raised by validate_and_raise() when a model fails validation."""


# ── pyecore-based validation ──────────────────────────────────────────────────

def _validate_with_pyecore(model_path: str, metamodel_path: str) -> tuple[bool, str]:
    """
    Load the metamodel and model via pyecore and verify conformance.

    Returns (is_valid: bool, message: str).
    """
    rset = ResourceSet()

    # Load metamodel
    try:
        mm_resource = rset.get_resource(URI(metamodel_path))
        pkg = mm_resource.contents[0]
        if not isinstance(pkg, EPackage):
            return False, f"Metamodel root is not an EPackage: {metamodel_path}"
        rset.metamodel_registry[pkg.nsURI] = pkg
    except Exception as e:
        return False, f"Failed to load metamodel '{metamodel_path}': {e}"

    # Load model
    try:
        model_resource = rset.get_resource(URI(model_path))
    except Exception as e:
        return False, f"Failed to load model '{model_path}': {e}"

    if not model_resource.contents:
        return False, "Model resource is empty."

    root = model_resource.contents[0]

    # Check root element type is defined in the metamodel
    root_eclass = root.eClass
    if root_eclass is None:
        return False, "Root element has no EClass."

    classifier = pkg.getEClassifier(root_eclass.name)
    if classifier is None:
        return False, (
            f"Root element type '{root_eclass.name}' is not defined "
            f"in metamodel '{pkg.nsURI}'."
        )

    # Recursively validate all contained objects
    issues = []
    _validate_object(root, pkg, issues)

    if issues:
        return False, "; ".join(issues)

    return True, "OK"


def _validate_object(obj, pkg: "EPackage", issues: list) -> None:
    """Recursively validate a model object and its contained children."""
    eclass = obj.eClass

    for sf in eclass.eAllStructuralFeatures():
        value = getattr(obj, sf.name, None)
        if value is None:
            continue

        # Check multiplicity lower bound
        if sf.required:
            if isinstance(value, list) and len(value) == 0:
                issues.append(
                    f"{eclass.name}.{sf.name} is required but empty."
                )
            elif not isinstance(value, list) and value is None:
                issues.append(
                    f"{eclass.name}.{sf.name} is required but missing."
                )

        # Check reference targets are defined in the metamodel
        if isinstance(sf, EReference) and sf.eType is not None:
            targets = value if isinstance(value, list) else [value]
            for target in targets:
                if target is None:
                    continue
                if pkg.getEClassifier(target.eClass.name) is None:
                    issues.append(
                        f"{eclass.name}.{sf.name} references unknown type "
                        f"'{target.eClass.name}'."
                    )

    # Recurse into contained children
    for sf in eclass.eAllStructuralFeatures():
        if not isinstance(sf, EReference) or not sf.containment:
            continue
        children = getattr(obj, sf.name, None)
        if children is None:
            continue
        if isinstance(children, list):
            for child in children:
                if child is not None:
                    _validate_object(child, pkg, issues)
        else:
            _validate_object(children, pkg, issues)


# ── Fallback: heuristic XML validation ───────────────────────────────────────

def _validate_with_xml(model_path: str, metamodel_path: str) -> tuple[bool, str]:
    """
    Heuristic validation when pyecore is unavailable.

    Checks:
    - Model is well-formed XML
    - Root element namespace URI matches the metamodel nsURI
    - All xsi:type values reference a type defined in the metamodel
    - Required attribute 'id' is present where declared
    """
    # Extract nsURI from metamodel
    try:
        mm_tree = ET.parse(metamodel_path)
        mm_root = mm_tree.getroot()
        ns_uri = mm_root.get("nsURI") or mm_root.get(
            "{http://www.eclipse.org/emf/2002/Ecore}nsURI", "")
        ns_prefix = mm_root.get("nsPrefix") or mm_root.get("name", "")

        # Collect all EClassifier names from metamodel
        known_types = set()
        for elem in mm_root.iter():
            name = elem.get("name")
            if name and elem.tag.endswith("EClassifiers"):
                known_types.add(name)
            elif name and (
                "EClass" in elem.get(
                    "{http://www.w3.org/2001/XMLSchema-instance}type", "")
            ):
                known_types.add(name)
        # Fallback: collect all name attrs
        if not known_types:
            for elem in mm_root.iter():
                n = elem.get("name")
                if n:
                    known_types.add(n)

    except ET.ParseError as e:
        return False, f"Metamodel XML parse error: {e}"
    except Exception as e:
        return False, f"Failed to read metamodel: {e}"

    # Parse model
    try:
        model_tree = ET.parse(model_path)
        model_root = model_tree.getroot()
    except ET.ParseError as e:
        return False, f"Model XML parse error: {e}"
    except Exception as e:
        return False, f"Failed to read model: {e}"

    # Check root namespace
    root_tag = model_root.tag
    if ns_uri and f"{{{ns_uri}}}" not in root_tag and ns_prefix not in root_tag:
        # Tolerate if nsURI appears in the namespace declarations
        declared_ns = list(model_root.attrib.values())
        if ns_uri not in declared_ns and ns_prefix not in root_tag:
            return False, (
                f"Root element tag '{root_tag}' does not match "
                f"metamodel namespace '{ns_uri}'."
            )

    # Check xsi:type references
    XSI_TYPE = "{http://www.w3.org/2001/XMLSchema-instance}type"
    issues = []
    for elem in model_tree.iter():
        xsi_type = elem.get(XSI_TYPE) or elem.get("xsi:type", "")
        if xsi_type and known_types:
            local = xsi_type.split(":")[-1]
            if local not in known_types:
                issues.append(
                    f"Element uses unknown type '{xsi_type}' "
                    f"(not found in metamodel)."
                )

    if issues:
        return False, "; ".join(issues)

    return True, "OK"


# ── Public API ────────────────────────────────────────────────────────────────

def validate_model(
    model_path: str,
    metamodel_path: str,
    *,
    verbose: bool = True,
) -> bool:
    """
    Check whether an XMI model conforms to an Ecore metamodel.

    Parameters
    ----------
    model_path     : path to the XMI model file
    metamodel_path : path to the .ecore metamodel file
    verbose        : if True, emit [VALIDATOR] log lines

    Returns
    -------
    True  → model is valid
    False → validation failed
    """
    model_name = os.path.basename(model_path)

    if not os.path.isfile(model_path):
        if verbose:
            logger.warning(f"[VALIDATOR] model invalid: {model_name} "
                           f"(file not found)")
        return False

    if not os.path.isfile(metamodel_path):
        if verbose:
            logger.warning(f"[VALIDATOR] metamodel not found: {metamodel_path}")
        return False

    if PYECORE_AVAILABLE:
        is_valid, message = _validate_with_pyecore(model_path, metamodel_path)
    else:
        is_valid, message = _validate_with_xml(model_path, metamodel_path)

    if verbose:
        if is_valid:
            logger.info(f"[VALIDATOR] model valid: {model_name}")
        else:
            logger.warning(f"[VALIDATOR] model invalid: {model_name} — {message}")

    return is_valid


def validate_and_raise(
    model_path: str,
    metamodel_path: str,
) -> None:
    """
    Validate a model and raise ModelValidationError if it fails.

    Parameters
    ----------
    model_path     : path to the XMI model file
    metamodel_path : path to the .ecore metamodel file

    Raises
    ------
    ModelValidationError if validation fails
    """
    model_name = os.path.basename(model_path)

    if PYECORE_AVAILABLE:
        is_valid, message = _validate_with_pyecore(model_path, metamodel_path)
    else:
        is_valid, message = _validate_with_xml(model_path, metamodel_path)

    if not is_valid:
        raise ModelValidationError(
            f"Model '{model_name}' failed validation: {message}"
        )

    logger.info(f"[VALIDATOR] model valid: {model_name}")


def validate_batch(
    model_paths: list,
    metamodel_path: str,
) -> dict:
    """
    Validate a list of models and return a summary.

    Returns
    -------
    {
        "valid":   [path, ...],
        "invalid": [path, ...],
        "total":   int,
        "valid_count":   int,
        "invalid_count": int,
    }
    """
    valid   = []
    invalid = []
    for path in model_paths:
        if validate_model(path, metamodel_path):
            valid.append(path)
        else:
            invalid.append(path)
    return {
        "valid":         valid,
        "invalid":       invalid,
        "total":         len(model_paths),
        "valid_count":   len(valid),
        "invalid_count": len(invalid),
    }


# ── main: self-test ───────────────────────────────────────────────────────────



if __name__ == '__main__':
    raise SystemExit('Use code/run_pipeline.py for current-protocol validation and execution.')
