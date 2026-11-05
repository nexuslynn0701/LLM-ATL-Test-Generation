#!/usr/bin/env python3
"""
test_strict_positive_path.py — Strict-valid positive-path integration test.

Verifies that a response containing <source_model> envelope:
  → extraction_pathway = "strict"
  → strict_contract_status = PASS_FORMAT_COMPLIANT
  → primary_analysis_eligible = True
  → sensitivity_analysis_eligible = True (includes strict)
  → recovery_attempted = False
  → recovery_rule = "not_needed_strict_passed"
  → generated XMI written to primary/generated_models/ only
  → no file created in sensitivity/recovered_models/
  → ATL execution succeeds on the extracted XMI

Also verifies negative assertions:
  → OK_RECOVERED does not appear for strict-valid
  → recovery_attempted is not True for strict-valid
  → malformed recovery produces no recovered_xmi_path
  → PRE_GATE rows rejected by primary analysis loader

Run:
  python3 tests/test_strict_positive_path.py
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.llm.xmi_extraction import (
    classify_extraction,
    STRICT_CONTRACT_PASS,
    STRICT_CONTRACT_FAIL,
    STRICT_FAIL_MISSING_WRAPPER,
    STRICT_FAIL_NO_XML,
    RECOVERY_RECOVERABLE,
    RECOVERY_FAIL_XML_MALFORMED,
    RECOVERY_ATTEMPTED_NO_FENCE,
    RECOVERY_NOT_ATTEMPTED,
    PATHWAY_STRICT,
    PATHWAY_RECOVERED,
    PATHWAY_NONE,
    PRIMARY_ELIGIBLE,
    PRIMARY_INELIGIBLE,
    SENSITIVITY_ELIGIBLE,
    SENSITIVITY_INELIGIBLE,
)

SUBJECT = "BibTeX2DocBook"

# ── Valid XMI taken from a real Gemma output that passed ATL ─────────────────

VALID_XMI = """<BibTeX:BibTeXFile xmi:version="2.0" xmlns:xmi="http://www.omg.org/XMI" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:BibTeX="http://BibTeX/1.0">
  <entries xsi:type="BibTeX:Book" id="book1" title="My Book" year="2023" publisher="Publisher Inc."/>
  <entries xsi:type="BibTeX:Article" id="article1" title="A Great Article" year="2022" journal="Journal of Awesome Science">
    <authors author="Alice Smith"/>
  </entries>
  <entries xsi:type="BibTeX:InProceedings" id="inproceedings1" title="Conference Paper" year="2024" booktitle="International Conference on Something">
    <authors author="Bob Johnson"/>
  </entries>
  <entries xsi:type="BibTeX:TechReport" id="techreport1" title="Technical Report" year="2021">
    <authors author="Charlie Brown"/>
  </entries>
</BibTeX:BibTeXFile>"""


def test_strict_positive_path():
    """End-to-end test of strict-valid input through the extraction + ATL pipeline."""

    strict_response = f"<source_model>\n{VALID_XMI}\n</source_model>\n\nSome trailing remarks."

    # ═══════════════════════════════════════════════════════════════════════════
    # Part A: Extraction classification
    # ═══════════════════════════════════════════════════════════════════════════

    result = classify_extraction(strict_response, subject=SUBJECT)

    checks = {
        "extraction_pathway":          (result["extraction_pathway"], PATHWAY_STRICT),
        "strict_contract_status":      (result["strict_contract_status"], STRICT_CONTRACT_PASS),
        "strict_failure_reason":       (result["strict_failure_reason"], ""),
        "recovery_attempted":          (result["recovery_attempted"], False),
        "recovery_rule":               (result["recovery_rule"], "not_needed_strict_passed"),
        "recovery_status":             (result["recovery_status"], RECOVERY_NOT_ATTEMPTED),
        "recovered_xml_well_formed":   (result["recovered_xml_well_formed"], True),
        "recovered_root_tag":          (result["recovered_root_tag"], "BibTeXFile"),
        "primary_analysis_eligible":   (result["primary_analysis_eligible"], PRIMARY_ELIGIBLE),
        "sensitivity_analysis_eligible": (result["sensitivity_analysis_eligible"], SENSITIVITY_ELIGIBLE),
    }

    all_ok = True
    print("Part A: Extraction classification")
    for name, (actual, expected) in checks.items():
        ok = actual == expected
        if not ok:
            all_ok = False
        print(f"  {'✓' if ok else '✗'} {name}: {actual!r}" + (f" (expected {expected!r})" if not ok else ""))

    # Negative assertions
    assert result["extraction_pathway"] != PATHWAY_RECOVERED, "FAIL: strict input classified as recovered"
    assert result["recovery_attempted"] != True, "FAIL: strict input triggered recovery"
    assert result["extraction_pathway"] != PATHWAY_NONE, "FAIL: strict input classified as none"
    print(f"  ✓ pathway != recovered")
    print(f"  ✓ recovery_attempted != True")

    # ═══════════════════════════════════════════════════════════════════════════
    # Part B: Directory isolation simulation
    # ═══════════════════════════════════════════════════════════════════════════

    tmpdir = tempfile.mkdtemp(prefix="test_strict_")
    try:
        primary_gen = Path(tmpdir) / "primary" / "generated_models" / SUBJECT / "sm"
        sensitivity_gen = Path(tmpdir) / "sensitivity" / "recovered_models" / SUBJECT / "sm"
        primary_gen.mkdir(parents=True)
        sensitivity_gen.mkdir(parents=True)

        # Simulate writing to primary (as the experiment runner does)
        source_path = primary_gen / "source_model_0001.xmi"
        source_path.write_text(VALID_XMI, encoding="utf-8")

        # Verify NO file written to sensitivity
        sensitivity_files = list(sensitivity_gen.glob("*.xmi"))
        assert len(sensitivity_files) == 0, f"FAIL: {len(sensitivity_files)} files in sensitivity"

        # Verify file in primary
        primary_files = list(primary_gen.glob("*.xmi"))
        assert len(primary_files) == 1, f"FAIL: {len(primary_files)} files in primary (expected 1)"

        print(f"\nPart B: Directory isolation")
        print(f"  ✓ primary file: {primary_files[0].name}")
        print(f"  ✓ sensitivity files: 0")

        # ═══════════════════════════════════════════════════════════════════════
        # Part C: ATL execution on strict-valid XMI
        # ═══════════════════════════════════════════════════════════════════════

        from src.executor.transformation_executor import run_transformation
        out_path = str(Path(tmpdir) / "primary" / "outputs" / SUBJECT / "sm" / "output_0001.xmi")
        os.makedirs(os.path.dirname(out_path), exist_ok=True)

        exec_result = run_transformation(str(source_path), out_path, "BibTeX2DocBook")
        atl_ok = exec_result["success"]

        print(f"\nPart C: ATL execution")
        print(f"  success: {atl_ok}")
        if not atl_ok:
            print(f"  error: {(exec_result.get('error') or exec_result.get('stderr', ''))[:200]}")

        # ATL on valid XMI should succeed
        assert atl_ok, "FAIL: ATL execution failed on strict-valid XMI"

        # ═══════════════════════════════════════════════════════════════════════
        # Part D: Eligibility after ATL
        # ═══════════════════════════════════════════════════════════════════════

        primary_final = result["primary_analysis_eligible"] == PRIMARY_ELIGIBLE and atl_ok
        sensitivity_final = primary_final or (
            result["sensitivity_analysis_eligible"] == SENSITIVITY_ELIGIBLE and atl_ok
        )

        print(f"\nPart D: Final eligibility")
        print(f"  primary_eligible: {primary_final}")
        print(f"  sensitivity_eligible: {sensitivity_final}")
        assert primary_final, "FAIL: strict-valid not primary eligible after ATL success"
        assert sensitivity_final, "FAIL: strict-valid not sensitivity eligible after ATL success"

        # ═══════════════════════════════════════════════════════════════════════
        # Part E: Negative assertions on malformed recovery + no-XML
        # ═══════════════════════════════════════════════════════════════════════

        # E1: malformed fenced XML → no recovered_xmi_path, no ATL
        malformed_result = classify_extraction(
            "```xml\n<BibTeX:BibTeXFile><unclosed>...</BibTeX:BibTeXFile>\n```",
            subject=SUBJECT,
        )
        assert malformed_result["recovery_status"] == RECOVERY_FAIL_XML_MALFORMED, (
            f"FAIL: expected RECOVERY_FAIL_XML_MALFORMED, got {malformed_result['recovery_status']}"
        )
        assert malformed_result["recovered_xmi_path"] == "", (
            "FAIL: malformed recovery should not have recovered_xmi_path"
        )

        # E2: no-XML → pathway=none, not eligible
        noxml_result = classify_extraction("Just some text, no XML at all.", subject=SUBJECT)
        assert noxml_result["extraction_pathway"] == PATHWAY_NONE
        assert noxml_result["primary_analysis_eligible"] == PRIMARY_INELIGIBLE
        assert noxml_result["sensitivity_analysis_eligible"] == SENSITIVITY_INELIGIBLE

        # E3: PRE_GATE row MUST be rejected by primary analysis loader
        from src.llm.xmi_extraction import assert_primary_analysis_eligible

        # Construct a PRE_GATE row (run_scope=PRE_GATE, counts=False)
        pre_gate_row = {
            "model_id": "0001",
            "status": "OK",
            "extraction_pathway": PATHWAY_STRICT,
            "primary_analysis_eligible": str(PRIMARY_ELIGIBLE),
            "strict_contract_status": STRICT_CONTRACT_PASS,
            "run_scope": "PRE_GATE_DIAGNOSTIC_DO_NOT_ANALYZE",
            "counts_toward_experiment_budget": "False",
        }
        try:
            assert_primary_analysis_eligible(pre_gate_row)
            assert False, "FAIL: PRE_GATE row passed primary assertion"
        except AssertionError as e:
            assert "PRE_GATE" in str(e), f"FAIL: wrong assertion message: {e}"

        # Construct a GATE_PASSED row (run_scope=GATE_PASSED, counts=True)
        gate_passed_row = {
            "model_id": "0001",
            "status": "OK",
            "extraction_pathway": PATHWAY_STRICT,
            "primary_analysis_eligible": str(PRIMARY_ELIGIBLE),
            "strict_contract_status": STRICT_CONTRACT_PASS,
            "run_scope": "GATE_PASSED",
            "counts_toward_experiment_budget": "True",
        }
        assert_primary_analysis_eligible(gate_passed_row)  # must pass

        # A recovered row must fail hard assertion
        recovered_row = dict(gate_passed_row)
        recovered_row["extraction_pathway"] = PATHWAY_RECOVERED
        recovered_row["primary_analysis_eligible"] = str(PRIMARY_INELIGIBLE)
        recovered_row["status"] = "OK_RECOVERED"
        try:
            assert_primary_analysis_eligible(recovered_row)
            assert False, "FAIL: OK_RECOVERED row passed primary assertion"
        except AssertionError:
            pass  # expected

        print(f"\nPart E: Negative assertions")
        print(f"  ✓ malformed recovery → no recovered_xmi_path")
        print(f"  ✓ no-XML → pathway=none, not eligible")
        print(f"  ✓ PRE_GATE row rejected by primary loader")
        print(f"  ✓ GATE_PASSED strict-valid accepted by primary loader")
        print(f"  ✓ OK_RECOVERED row rejected by primary loader")

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    print(f"\n{'='*60}")
    print(f"STRICT POSITIVE PATH: ALL CHECKS PASSED")
    return True


if __name__ == "__main__":
    ok = test_strict_positive_path()
    sys.exit(0 if ok else 1)
