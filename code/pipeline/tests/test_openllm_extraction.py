#!/usr/bin/env python3
"""
test_openllm_extraction.py — 6-category constructed-input unit test for
dual-pathway extraction (criterion 10).

Categories:
  1. STRICT        — valid <source_model> envelope, well-formed, correct root
  2. RECOVERABLE   — single ```xml fence, well-formed, correct root
  3. MALFORMED     — single fence, XML parse error (unclosed tag)
  4. MULTI_FENCE   — multiple ``` fences in output
  5. DOCTYPE       — single fence, XML contains <!DOCTYPE ...>
  6. WRONG_ROOT    — single fence, well-formed XML but wrong root element

Run:
  python3 tests/test_openllm_extraction.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.llm.openllm_extraction import (
    classify_extraction,
    STRICT_CONTRACT_PASS,
    STRICT_CONTRACT_FAIL,
    STRICT_FAIL_NO_XML,
    STRICT_FAIL_MISSING_WRAPPER,
    STRICT_FAIL_MALFORMED_XML,
    RECOVERY_RECOVERABLE,
    RECOVERY_FAIL_XML_MALFORMED,
    RECOVERY_FAIL_UNEXPECTED_ROOT,
    RECOVERY_FAIL_DOCTYPE_FORBIDDEN,
    RECOVERY_ATTEMPTED_MULTIPLE_FENCES,
    PATHWAY_STRICT,
    PATHWAY_RECOVERED,
    PATHWAY_NONE,
    PRIMARY_ELIGIBLE,
    PRIMARY_INELIGIBLE,
    SENSITIVITY_ELIGIBLE,
    SENSITIVITY_INELIGIBLE,
)

SUBJECT = "BibTeX2DocBook"

# ── Helper: valid BibTeXFile XMI for BibTeX2DocBook ───────────────────────────

VALID_XMI = """<BibTeX:BibTeXFile xmi:version="2.0" xmlns:xmi="http://www.omg.org/XMI" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:BibTeX="http://BibTeX/1.0">
  <entries xsi:type="BibTeX:Book" id="book1" title="Test" year="2023" publisher="Pub"/>
</BibTeX:BibTeXFile>"""

MALFORMED_XMI = """<BibTeX:BibTeXFile xmi:version="2.0" xmlns:xmi="http://www.omg.org/XMI" xmlns:BibTeX="http://BibTeX/1.0">
  <entries xsi:type="BibTeX:Book" id="book1" title="Test" year="2023">
</BibTeX:BibTeXFile>"""

WRONG_ROOT_XMI = """<Other:Something xmi:version="2.0" xmlns:xmi="http://www.omg.org/XMI" xmlns:Other="http://other/ns">
  <entry/>
</Other:Something>"""

DOCTYPE_XMI = """<?xml version="1.0"?>
<!DOCTYPE BibTeXFile [
  <!ENTITY foo "bar">
]>
<BibTeX:BibTeXFile xmi:version="2.0" xmlns:xmi="http://www.omg.org/XMI" xmlns:BibTeX="http://BibTeX/1.0">
  <entries xsi:type="BibTeX:Book" id="book1" title="Test" year="2023" publisher="Pub"/>
</BibTeX:BibTeXFile>"""


def run_test(name, raw_content, expected):
    """Run one test case and return (passed: bool, details: str)."""
    result = classify_extraction(raw_content, subject=SUBJECT)
    passed = True
    failures = []

    for key, expected_val in expected.items():
        actual_val = result.get(key)
        if actual_val != expected_val:
            passed = False
            failures.append(f"  {key}: expected={expected_val!r} actual={actual_val!r}")

    status = "PASS" if passed else "FAIL"
    print(f"\n{'='*60}")
    print(f"TEST: {name} — {status}")
    if failures:
        for f in failures:
            print(f)
        print(f"  Full classification:")
        for k, v in sorted(result.items()):
            if k not in ("usable_xml", "strict_xml", "recovered_xml"):
                print(f"    {k}: {v!r}")
    else:
        print(f"  All {len(expected)} assertions passed.")
    return passed


# ═══════════════════════════════════════════════════════════════════════════════
# TEST CASE 1: Strict — valid <source_model> envelope
# ═══════════════════════════════════════════════════════════════════════════════

test1_input = f"<source_model>\n{VALID_XMI}\n</source_model>\n\nSome trailing text."

test1 = run_test("STRICT", test1_input, {
    "strict_contract_status": STRICT_CONTRACT_PASS,
    "strict_failure_reason": "",
    "recovery_attempted": False,
    "recovery_status": "NOT_ATTEMPTED_STRICT_PASSED",
    "recovered_xml_well_formed": True,
    "recovered_root_tag": "BibTeXFile",
    "extraction_pathway": PATHWAY_STRICT,
    "primary_analysis_eligible": PRIMARY_ELIGIBLE,
    "sensitivity_analysis_eligible": SENSITIVITY_ELIGIBLE,
})

# ═══════════════════════════════════════════════════════════════════════════════
# TEST CASE 2: Recoverable — single ```xml fence, well-formed, correct root
# ═══════════════════════════════════════════════════════════════════════════════

test2_input = f"```xml\n{VALID_XMI}\n```"

test2 = run_test("RECOVERABLE", test2_input, {
    "strict_contract_status": STRICT_CONTRACT_FAIL,
    "strict_failure_reason": STRICT_FAIL_MISSING_WRAPPER,
    "recovery_attempted": True,
    "recovery_rule": "single_fence_xml",
    "recovery_status": RECOVERY_RECOVERABLE,
    "recovered_xml_well_formed": True,
    "recovered_root_tag": "BibTeXFile",
    "extraction_pathway": PATHWAY_RECOVERED,
    "primary_analysis_eligible": PRIMARY_INELIGIBLE,
    "sensitivity_analysis_eligible": SENSITIVITY_ELIGIBLE,
})

# ═══════════════════════════════════════════════════════════════════════════════
# TEST CASE 3: Malformed — single fence, XML parse error
# ═══════════════════════════════════════════════════════════════════════════════

test3_input = f"```xml\n{MALFORMED_XMI}\n```"

test3 = run_test("MALFORMED", test3_input, {
    "strict_contract_status": STRICT_CONTRACT_FAIL,
    "strict_failure_reason": STRICT_FAIL_MISSING_WRAPPER,
    "recovery_attempted": True,
    "recovery_rule": "single_fence_xml",
    "recovery_status": RECOVERY_FAIL_XML_MALFORMED,
    "recovered_xml_well_formed": False,
    "extraction_pathway": PATHWAY_NONE,
    "primary_analysis_eligible": PRIMARY_INELIGIBLE,
    "sensitivity_analysis_eligible": SENSITIVITY_INELIGIBLE,
})

# ═══════════════════════════════════════════════════════════════════════════════
# TEST CASE 4: Multiple fences
# ═══════════════════════════════════════════════════════════════════════════════

test4_input = f"```xml\n{VALID_XMI}\n```\n\n```xml\n{WRONG_ROOT_XMI}\n```"

test4 = run_test("MULTI_FENCE", test4_input, {
    "strict_contract_status": STRICT_CONTRACT_FAIL,
    "strict_failure_reason": STRICT_FAIL_MISSING_WRAPPER,
    "recovery_attempted": True,
    "recovery_rule": "multiple_fences_count_4",
    "recovery_status": RECOVERY_ATTEMPTED_MULTIPLE_FENCES,
    "extraction_pathway": PATHWAY_NONE,
    "primary_analysis_eligible": PRIMARY_INELIGIBLE,
    "sensitivity_analysis_eligible": SENSITIVITY_INELIGIBLE,
})

# ═══════════════════════════════════════════════════════════════════════════════
# TEST CASE 5: DOCTYPE in fenced content
# ═══════════════════════════════════════════════════════════════════════════════

test5_input = f"```xml\n{DOCTYPE_XMI}\n```"

test5 = run_test("DOCTYPE", test5_input, {
    "strict_contract_status": STRICT_CONTRACT_FAIL,
    "strict_failure_reason": STRICT_FAIL_MISSING_WRAPPER,
    "recovery_attempted": True,
    "recovery_rule": "single_fence_xml",
    "recovery_status": RECOVERY_FAIL_DOCTYPE_FORBIDDEN,
    "extraction_pathway": PATHWAY_NONE,
    "primary_analysis_eligible": PRIMARY_INELIGIBLE,
    "sensitivity_analysis_eligible": SENSITIVITY_INELIGIBLE,
})

# ═══════════════════════════════════════════════════════════════════════════════
# TEST CASE 6: Wrong root — well-formed but unexpected root element
# ═══════════════════════════════════════════════════════════════════════════════

test6_input = f"```xml\n{WRONG_ROOT_XMI}\n```"

test6 = run_test("WRONG_ROOT", test6_input, {
    "strict_contract_status": STRICT_CONTRACT_FAIL,
    "strict_failure_reason": STRICT_FAIL_MISSING_WRAPPER,
    "recovery_attempted": True,
    "recovery_rule": "single_fence_xml",
    "recovery_status": RECOVERY_FAIL_UNEXPECTED_ROOT,
    "recovered_xml_well_formed": True,  # XML is well-formed, just wrong root
    "recovered_root_tag": "Something",
    "extraction_pathway": PATHWAY_NONE,
    "primary_analysis_eligible": PRIMARY_INELIGIBLE,
    "sensitivity_analysis_eligible": SENSITIVITY_INELIGIBLE,
})


# ═══════════════════════════════════════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════════════
# TEST CASE 7: No XML at all — plain text response
# ═══════════════════════════════════════════════════════════════════════════════

test7_input = "I cannot generate the model. Please try again."

test7 = run_test("NO_XML", test7_input, {
    "strict_contract_status": STRICT_CONTRACT_FAIL,
    "strict_failure_reason": STRICT_FAIL_NO_XML,
    "recovery_attempted": True,
    "recovery_rule": "no_fence",
    "recovery_status": "ATTEMPTED_NO_FENCE_DETECTED",
    "extraction_pathway": PATHWAY_NONE,
    "primary_analysis_eligible": PRIMARY_INELIGIBLE,
    "sensitivity_analysis_eligible": SENSITIVITY_INELIGIBLE,
})

results = [test1, test2, test3, test4, test5, test6, test7]
passed = sum(results)
total = len(results)
print(f"\n{'='*60}")
print(f"UNIT TEST SUMMARY: {passed}/{total} passed")
if passed == total:
    print("ALL TESTS PASSED")
    sys.exit(0)
else:
    print(f"FAILED: {total - passed} test(s)")
    sys.exit(1)
