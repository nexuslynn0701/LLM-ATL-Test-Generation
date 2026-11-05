"""
openllm_extraction.py — Dual-pathway XMI extraction for OpenLLM experiments.

Shared between smoke_test_openllm.py (diagnostic probe) and
run_openllm_ladder.py (formal experiment).

Pathways:
  1. Strict:  extract_xml_block(raw, "source_model") → <source_model> envelope
  2. Recovery: detect + strip single markdown code fence → recovered XMI
     (gated by well-formed check, DOCTYPE/ENTITY block, single-document,
      expected root element validation)

Recovery rules (deterministic, no content modification):
  - Only a single ```xml or ``` fence with nothing but whitespace outside
  - No DOCTYPE / ENTITY declarations
  - Single XML document inside fence
  - Python XML well-formed parse success
  - Root element matches expected namespace + local name for the subject

All status fields are recorded per attempt so that primary and
sensitivity analyses are both computable from the CSV.
"""

import re
import xml.etree.ElementTree as ET
from pathlib import Path


# ═══════════════════════════════════════════════════════════════════════════════
# Subject → expected root element mapping
# ═══════════════════════════════════════════════════════════════════════════════

EXPECTED_ROOT = {
    "BibTeX2DocBook": {
        "namespace": "http://BibTeX/1.0",
        "local_name": "BibTeXFile",
        "qname": "{http://BibTeX/1.0}BibTeXFile",
    },
    "CPL2SPL": {
        "namespace": "http://cpl/1.0",
        "local_name": "CPLModel",
        "qname": "{http://cpl/1.0}CPLModel",
    },
    "UML2ER": {
        "namespace": "http://SimpleUML",
        "local_name": "Package",
        "qname": "{http://SimpleUML}Package",
    },
    "Ecore2Maude": {
        "namespace": "http://ecore",
        "local_name": "EPackage",
        "qname": "{http://ecore}EPackage",
    },
    "Ant2Maven": {
        "namespace": "Ant",
        "local_name": "Project",
        "qname": "{Ant}Project",
    },
    "Grafcet2PetriNet": {
        "namespace": "Grafcet",
        "local_name": "Grafcet",
        "qname": "{Grafcet}Grafcet",
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
# Status constants
# ═══════════════════════════════════════════════════════════════════════════════

# Overall smoke classification
SMOKE_PASS_STRICT           = "PASS_STRICT"
SMOKE_PASS_RECOVERABLE_ONLY = "PASS_RECOVERABLE_ONLY"
SMOKE_FAIL                  = "FAIL"

# Strict output-format compliance
STRICT_CONTRACT_PASS             = "PASS_FORMAT_COMPLIANT"
STRICT_CONTRACT_FAIL             = "FAIL_FORMAT_NONCOMPLIANT"
STRICT_FAIL_MISSING_WRAPPER      = "MISSING_SOURCE_MODEL_WRAPPER"
STRICT_FAIL_MALFORMED_XML        = "MALFORMED_XML_INSIDE_WRAPPER"
STRICT_FAIL_NO_XML               = "NO_XML_DETECTED"
STRICT_FAIL_API_ERROR            = "API_ERROR"

# Recovery attempt
RECOVERY_NOT_ATTEMPTED                  = "NOT_ATTEMPTED_STRICT_PASSED"
RECOVERY_ATTEMPTED_NO_FENCE             = "ATTEMPTED_NO_FENCE_DETECTED"
RECOVERY_ATTEMPTED_MULTIPLE_FENCES      = "ATTEMPTED_MULTIPLE_FENCES_DETECTED"

# Recovery failure reasons (after fence candidate found)
RECOVERY_FAIL_XML_MALFORMED             = "RECOVERY_FAIL_XML_MALFORMED"
RECOVERY_FAIL_DOCTYPE_FORBIDDEN         = "RECOVERY_FAIL_FORBIDDEN_DOCTYPE"
RECOVERY_FAIL_MULTIPLE_DOCUMENTS        = "RECOVERY_FAIL_MULTIPLE_DOCUMENTS"
RECOVERY_FAIL_UNEXPECTED_ROOT           = "RECOVERY_FAIL_UNEXPECTED_ROOT"

# Recovery success
RECOVERY_RECOVERABLE                    = "RECOVERABLE_CODE_FENCE_XML"

# Extraction pathway
PATHWAY_STRICT    = "strict"
PATHWAY_RECOVERED = "recovered"
PATHWAY_NONE      = "none"

# Analysis eligibility
PRIMARY_ELIGIBLE     = True
PRIMARY_INELIGIBLE   = False
SENSITIVITY_ELIGIBLE = True
SENSITIVITY_INELIGIBLE = False

# Run scope
RUN_SCOPE_PRE_GATE  = "PRE_GATE_DIAGNOSTIC_DO_NOT_ANALYZE"
RUN_SCOPE_GATE_OK   = "GATE_PASSED"


# ═══════════════════════════════════════════════════════════════════════════════
# Core extraction
# ═══════════════════════════════════════════════════════════════════════════════

def _detect_fence_candidate(text: str) -> dict:
    """
    Detect a single markdown code fence in text.

    Returns:
      found: bool
      count: int          — number of ``` occurrences
      content: str | None — inner content if exactly one fence
      fence_lang: str | None — language tag if present (e.g. "xml")
    """
    matches = list(re.finditer(r'^```', text, re.MULTILINE))
    count = len(matches)

    if count == 0:
        return {"found": False, "count": 0, "content": None, "fence_lang": None}

    if count != 2:
        # 0 fences = no fence detected
        # 1 fence = unclosed
        # >2 fences = ambiguous (multiple code blocks)
        return {"found": True, "count": count, "content": None, "fence_lang": None}

    # Exactly 2 fences: extract content between them
    opening = matches[0]
    closing = matches[-1]

    # Extract language tag from opening fence line
    open_line = text[opening.start():text.find('\n', opening.start())]
    lang_match = re.match(r'^```(\w*)\s*$', open_line)
    fence_lang = (lang_match.group(1) or None) if lang_match else None

    # Get content between fences
    content_start = text.find('\n', opening.start()) + 1
    content_end = closing.start()
    inner = text[content_start:content_end].strip()

    # Check nothing outside fences except whitespace
    before = text[:opening.start()].strip()
    after = text[closing.end():].strip()
    if before or after:
        return {"found": True, "count": count, "content": None, "fence_lang": None,
                "noise_outside": True}

    return {"found": True, "count": count, "content": inner, "fence_lang": fence_lang}


def _check_xml_safety(xml_text: str) -> dict:
    """
    Security and structure checks on candidate XML.

    Returns:
      safe: bool
      reason: str | None
    """
    # Forbid DOCTYPE/ENTITY
    if re.search(r'<!DOCTYPE\s', xml_text, re.IGNORECASE):
        return {"safe": False, "reason": RECOVERY_FAIL_DOCTYPE_FORBIDDEN}
    if re.search(r'<!ENTITY\s', xml_text, re.IGNORECASE):
        return {"safe": False, "reason": RECOVERY_FAIL_DOCTYPE_FORBIDDEN}

    # Count XML declarations / root elements → single document check
    decl_count = len(re.findall(r'<\?xml\s', xml_text))
    if decl_count > 1:
        return {"safe": False, "reason": RECOVERY_FAIL_MULTIPLE_DOCUMENTS}

    return {"safe": True, "reason": None}


XMI_NS = "http://www.omg.org/XMI"

def _resolve_model_root(root_element) -> tuple:
    """
    Resolve the effective model root element.

    If the XML root is <xmi:XMI>, returns the first child element's
    qname and local name (the model root). Otherwise returns the
    XML root's own qname and local name.

    Returns (qname: str, local: str).
    """
    tag = root_element.tag
    if "}" in tag:
        ns_end = tag.index("}") + 1
        root_ns = tag[1:ns_end - 1]
        root_local = tag[ns_end:]
    else:
        root_ns = ""
        root_local = tag

    # If root is xmi:XMI, unwrap to first child
    if root_ns == XMI_NS and root_local == "XMI":
        children = list(root_element)
        if children:
            child = children[0]
            child_tag = child.tag
            if "}" in child_tag:
                c_ns_end = child_tag.index("}") + 1
                child_local = child_tag[c_ns_end:]
                child_qname = child_tag
            else:
                child_local = child_tag
                child_qname = child_tag
            return child_qname, child_local

    return tag, root_local


def _parse_xml(xml_text: str) -> dict:
    """
    Parse XML and extract root element info.

    Handles both direct model root (e.g. <BibTeX:BibTeXFile>) and
    XMI-wrapped root (<xmi:XMI><Grafcet:Grafcet>).

    Returns:
      well_formed: bool
      root_qname: str | None   — Clark notation {ns}local (model root)
      root_local: str | None   — local name of model root
      root_ns: str | None      — namespace of model root
      error: str | None
    """
    try:
        root = ET.fromstring(xml_text)
        model_qname, model_local = _resolve_model_root(root)

        if "}" in model_qname:
            ns_end = model_qname.index("}") + 1
            root_ns = model_qname[1:ns_end - 1]
        else:
            root_ns = ""

        return {
            "well_formed": True,
            "root_qname": model_qname,
            "root_local": model_local,
            "root_ns": root_ns,
            "error": None,
        }
    except ET.ParseError as e:
        return {
            "well_formed": False,
            "root_qname": None,
            "root_local": None,
            "root_ns": None,
            "error": str(e),
        }


def classify_extraction(
    raw_content: str,
    subject: str | None = None,
) -> dict:
    """
    Classify an LLM response by extraction pathway.

    Parameters
    ----------
    raw_content : str
        Raw LLM response text.
    subject : str | None
        Dataset name (e.g. "BibTeX2DocBook"). Used for root element validation.
        If None, root validation is skipped.

    Returns
    -------
    dict with all extraction/classification fields.
    """
    from src.generator.test_generator import extract_xml_block

    expected = EXPECTED_ROOT.get(subject) if subject else None

    result = {
        # Strict pathway
        "strict_contract_status": STRICT_CONTRACT_FAIL,
        "strict_failure_reason": STRICT_FAIL_NO_XML,
        "strict_extraction_path": "",
        
        "strict_xml": None,          # convenience: raw content inside <source_model>
        "recovered_xml": None,       # convenience: raw fenced content (before validation)
        # Recovery pathway
        # Recovery pathway
        "recovery_attempted": False,
        "recovery_rule": "",
        "recovery_status": "",
        "recovered_xmi_path": "",
        
        "recovered_xml_well_formed": False,
        "recovered_root_tag": "",
        "recovered_atl_runtime_status": "",
        # Resolution
        "extraction_pathway": PATHWAY_NONE,
        "usable_xml": None,
        
        # Eligibility
        "primary_analysis_eligible": PRIMARY_INELIGIBLE,
        "sensitivity_analysis_eligible": SENSITIVITY_INELIGIBLE,
    }

    # ═══════════════════════════════════════════════════════════════════════════
    # Pathway 1: Strict (<source_model> envelope)
    # ═══════════════════════════════════════════════════════════════════════════
    strict = extract_xml_block(raw_content, "source_model")
    result["strict_xml"] = strict.strip() if strict else None
    strict_valid = False

    if strict is not None and len(strict.strip()) > 0:

        parse = _parse_xml(strict.strip())
        if parse["well_formed"]:
            # Check root if subject provided
            if expected:
                root_ok = (parse["root_qname"] == expected["qname"])
            else:
                root_ok = True

            if root_ok:
                result["strict_contract_status"] = STRICT_CONTRACT_PASS
                result["strict_failure_reason"] = ""
                result["recovery_attempted"] = False
                result["recovery_rule"] = "not_needed_strict_passed"
                result["recovery_status"] = RECOVERY_NOT_ATTEMPTED
                result["extraction_pathway"] = PATHWAY_STRICT
                result["usable_xml"] = strict.strip()
                result["recovered_xml_well_formed"] = True
                result["recovered_root_tag"] = parse["root_local"]
                strict_valid = True
            else:
                result["strict_contract_status"] = STRICT_CONTRACT_FAIL
                result["strict_failure_reason"] = RECOVERY_FAIL_UNEXPECTED_ROOT
                result["recovered_root_tag"] = parse["root_local"]
                result["recovery_attempted"] = False
                result["recovery_rule"] = "strict_wrong_root_not_attempted"
                result["recovery_status"] = RECOVERY_NOT_ATTEMPTED
                result["extraction_pathway"] = PATHWAY_STRICT
        else:
            result["strict_contract_status"] = STRICT_CONTRACT_FAIL
            result["strict_failure_reason"] = STRICT_FAIL_MALFORMED_XML
            result["recovered_xml_well_formed"] = False
            result["recovery_attempted"] = False
            result["recovery_rule"] = "strict_malformed_not_attempted"
            result["recovery_status"] = RECOVERY_NOT_ATTEMPTED
            result["extraction_pathway"] = PATHWAY_STRICT

        # Still save strict XML path (even if malformed) for provenance
        result["usable_xml"] = strict.strip()

    def _set_strict_fail(reason):
        """Set strict_failure_reason only if not already set by strict pathway."""
        current = result.get("strict_failure_reason", "")
        if current in ("", STRICT_FAIL_NO_XML):
            result["strict_failure_reason"] = reason

    # ═══════════════════════════════════════════════════════════════════════════
    # Pathway 2: Envelope recovery (markdown fence stripping)
    # ═══════════════════════════════════════════════════════════════════════════
    if not strict_valid:
        result["recovery_attempted"] = True

        fence = _detect_fence_candidate(raw_content)

        if not fence["found"]:
            result["recovery_rule"] = "no_fence"
            result["recovery_status"] = RECOVERY_ATTEMPTED_NO_FENCE
            # Only set strict_failure_reason if strict didn't already find something
            if result["strict_failure_reason"] in ("", STRICT_FAIL_NO_XML):
                result["strict_failure_reason"] = STRICT_FAIL_NO_XML
            return result

        if fence["content"] is None:
            fence_count = fence.get("count", 0)
            if fence_count > 2:
                result["recovery_rule"] = f"multiple_fences_count_{fence_count}"
                result["recovery_status"] = RECOVERY_ATTEMPTED_MULTIPLE_FENCES
            elif fence_count == 1:
                result["recovery_rule"] = "single_unclosed_fence"
                result["recovery_status"] = RECOVERY_ATTEMPTED_NO_FENCE
            elif fence.get("noise_outside"):
                result["recovery_rule"] = "fence_with_noise_outside"
                result["recovery_status"] = RECOVERY_ATTEMPTED_NO_FENCE
            else:
                result["recovery_rule"] = "fence_parse_failed"
                result["recovery_status"] = RECOVERY_ATTEMPTED_NO_FENCE
            _set_strict_fail(STRICT_FAIL_MISSING_WRAPPER)
            return result

        # Check fence language — allow xml or no lang tag
        lang = fence.get("fence_lang", "")
        if lang and lang.lower() not in ("xml", ""):
            result["recovery_rule"] = f"wrong_fence_lang_{lang}"
            result["recovery_status"] = RECOVERY_ATTEMPTED_NO_FENCE
            _set_strict_fail(STRICT_FAIL_MISSING_WRAPPER)
            return result

        candidate = fence["content"]
        result["recovered_xml"] = candidate
        result["recovery_rule"] = "single_fence_xml"

        # Strip <source_model> wrapper if present inside fence
        # (Gemma sometimes outputs ```\n<source_model>\n...\n</source_model>\n```)
        from src.generator.test_generator import extract_xml_block as _extract
        inner_strict = _extract(candidate, "source_model")
        if inner_strict is not None and len(inner_strict.strip()) > 0:
            candidate = inner_strict.strip()
            result["recovery_rule"] = "single_fence_xml_with_inner_wrapper"

        # Security check
        safety = _check_xml_safety(candidate)
        if not safety["safe"]:
            result["recovery_status"] = safety["reason"]
            _set_strict_fail(STRICT_FAIL_MISSING_WRAPPER)
            return result

        # Parse
        parse = _parse_xml(candidate)
        if not parse["well_formed"]:
            result["recovery_status"] = RECOVERY_FAIL_XML_MALFORMED
            result["recovered_xml_well_formed"] = False
            _set_strict_fail(STRICT_FAIL_MISSING_WRAPPER)
            return result

        result["recovered_xml_well_formed"] = True
        result["recovered_root_tag"] = parse["root_local"]

        # Root element check
        if expected and parse["root_qname"] != expected["qname"]:
            result["recovery_status"] = RECOVERY_FAIL_UNEXPECTED_ROOT
            _set_strict_fail(STRICT_FAIL_MISSING_WRAPPER)
            # Still provide the XML for manual inspection
            return result

        # ── Recovery SUCCESS ──
        result["recovery_status"] = RECOVERY_RECOVERABLE
        _set_strict_fail(STRICT_FAIL_MISSING_WRAPPER)
        result["extraction_pathway"] = PATHWAY_RECOVERED
        result["usable_xml"] = candidate

    # ═══════════════════════════════════════════════════════════════════════════
    # Eligibility
    # ═══════════════════════════════════════════════════════════════════════════
    # primary = strict extraction succeeded AND well-formed AND expected root
    # (ATL success is checked later; set tentative here)
    result["primary_analysis_eligible"] = (
        PRIMARY_ELIGIBLE if strict_valid else PRIMARY_INELIGIBLE
    )

    # sensitivity = primary OR (recovered AND well-formed AND expected root)
    sensitivity_ok = strict_valid or (
        result["recovery_status"] == RECOVERY_RECOVERABLE
        and result["recovered_xml_well_formed"]
    )
    result["sensitivity_analysis_eligible"] = (
        SENSITIVITY_ELIGIBLE if sensitivity_ok else SENSITIVITY_INELIGIBLE
    )

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# Convenience re-exports (for smoke test compatibility)
# ═══════════════════════════════════════════════════════════════════════════════

def recover_fenced_xml(text: str) -> str | None:
    """Legacy wrapper: return recovered content or None."""
    fence = _detect_fence_candidate(text)
    if fence["found"] and fence["content"] is not None:
        return fence["content"]
    return None


def check_xml_wellformed(xml_text: str) -> dict:
    """Legacy wrapper: return well-formed check result."""
    parse = _parse_xml(xml_text)
    return {
        "well_formed": parse["well_formed"],
        "error": parse["error"],
        "root_tag": parse["root_local"],
    }


# ═══════════════════════════════════════════════════════════════════════════════
# CSV field list (for multi_config_results.csv)
# ═══════════════════════════════════════════════════════════════════════════════

EXTRACTION_CSV_FIELDS = [
    "strict_contract_status",
    "strict_failure_reason",
    "strict_extraction_path",
    
    "recovery_attempted",
    "recovery_rule",
    "recovery_status",
    "recovered_xmi_path",
    
    "recovered_xml_well_formed",
    "recovered_root_tag",
    "recovered_atl_runtime_status",
    "extraction_pathway",
    "primary_analysis_eligible",
    "sensitivity_analysis_eligible",
    
    
]
