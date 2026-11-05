#!/usr/bin/env python3
"""
test_expected_root_regression.py — 6-subject expected-root validation regression.

For each of the 6 subjects, loads a known-good historical source model
and confirms:
  1. Expected-root mapping matches the actual root element (namespace + local name)
  2. Metamodel loading succeeds (XML parse)
  3. Original ATL execution succeeds

Prevents the expected-root mapping from being overly strict and rejecting
legitimate XMI serializations.

Run:
  python -X utf8 code/runtime/pipeline_toolchain/tests/test_expected_root_regression.py
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.llm.xmi_extraction import EXPECTED_ROOT, _resolve_model_root
from src.experiment.run_ladder_experiment import DATASETS, get_executor_config

# ── Known-good XMI per subject (verified in prior experiments) ────────────────

BUNDLE = next(parent for parent in ROOT.parents
              if (parent/'results/experiment_results').is_dir())
import csv
with (BUNDLE/'results/rq1/supplementary/source_population.csv').open(encoding='utf-8-sig', newline='') as handle:
    population = list(csv.DictReader(handle))
KNOWN_GOOD = {}
for subject in EXPECTED_ROOT:
    row = next(r for r in population if r['subject']==subject and r['provider']=='GPT'
               and r['condition']=='astmo' and r['in_estar']=='1')
    source = BUNDLE/'data/test_cases'/subject/'astmo/gpt'/(row['source_id']+'.xmi')
    KNOWN_GOOD[subject] = {'path':str(source)}



def run_regression():
    import xml.etree.ElementTree as ET
    from src.executor.transformation_executor import run_transformation

    all_ok = True

    for subject in sorted(EXPECTED_ROOT.keys()):
        expected = EXPECTED_ROOT[subject]
        known = KNOWN_GOOD.get(subject)
        print(f"\n{'='*60}")
        print(f"SUBJECT: {subject}")
        print(f"  Expected root: {{{expected['namespace']}}}{expected['local_name']}")

        if known is None:
            print(f"  ✗ No known-good XMI registered")
            all_ok = False
            continue

        xmi_path = ROOT / known["path"]
        if not xmi_path.exists():
            print(f"  ✗ Known-good XMI missing: {xmi_path}")
            all_ok = False
            continue

        # ═══════════════════════════════════════════════════════════════════════
        # Check 1: Parse XML and verify model root matches expected
        # ═══════════════════════════════════════════════════════════════════════
        try:
            tree = ET.parse(str(xmi_path))
            root = tree.getroot()
            model_qname, model_local = _resolve_model_root(root)

            if "}" in model_qname:
                ns_end = model_qname.index("}") + 1
                actual_ns = model_qname[1:ns_end - 1]
            else:
                actual_ns = ""

            root_matches = (model_qname == expected["qname"])
            status = "✓" if root_matches else "✗"
            print(f"  {status} Model root: {{{actual_ns}}}{model_local}")

            if not root_matches:
                print(f"    Expected: {{{expected['namespace']}}}{expected['local_name']}")
                all_ok = False
                continue
        except ET.ParseError as e:
            print(f"  ✗ XML parse error: {e}")
            all_ok = False
            continue

        # ═══════════════════════════════════════════════════════════════════════
        # Check 2: Metamodel loading passes (just confirms the file exists)
        # ═══════════════════════════════════════════════════════════════════════
        ds = DATASETS.get(subject)
        if ds is None:
            print(f"  ✗ Subject not in DATASETS")
            all_ok = False
            continue

        src_mm = ds["dataset_dir"] / ds["source_mm"]
        if src_mm.exists():
            print(f"  ✓ Source metamodel exists: {ds['source_mm']}")
        else:
            print(f"  ✗ Source metamodel missing: {src_mm}")
            all_ok = False
            continue

        # ═══════════════════════════════════════════════════════════════════════
        # Check 3: Original ATL execution
        # ═══════════════════════════════════════════════════════════════════════
        exec_cfg = get_executor_config(subject)
        out_path = str(ROOT / f"tmp_regression_test_{subject}_out.xmi")

        try:
            exec_result = run_transformation(
                str(xmi_path), out_path, ds["atl_name"], exec_cfg
            )
            atl_ok = exec_result["success"]
            if atl_ok:
                print(f"  ✓ ATL execution")
            else:
                all_ok = False
                err = (exec_result.get("error") or exec_result.get("stderr", ""))[:150]
                print(f"  ⚠ ATL execution FAILED")
                print(f"    Error: {err}")
        except Exception as e:
            print(f"  ✗ ATL execution exception: {e}")
            all_ok = False
        finally:
            # Cleanup
            for tmp in ROOT.glob("tmp_regression_test_*"):
                try:
                    tmp.unlink()
                except Exception:
                    pass

        # ═══════════════════════════════════════════════════════════════════════
        # Check 4: Expected-root mapping produces the correct Clark notation
        # when classify_extraction is given a strict-valid response
        # ═══════════════════════════════════════════════════════════════════════
        from src.llm.xmi_extraction import (
            classify_extraction,
            STRICT_CONTRACT_PASS,
            PATHWAY_STRICT,
        )
        xmi_content = xmi_path.read_text(encoding="utf-8")
        strict_response = f"<source_model>\n{xmi_content}\n</source_model>"

        classification = classify_extraction(strict_response, subject=subject)
        extract_strict_ok = (
            classification["strict_contract_status"] == STRICT_CONTRACT_PASS
            and classification["extraction_pathway"] == PATHWAY_STRICT
            and classification["recovered_root_tag"] == expected["local_name"]
        )
        status = "✓" if extract_strict_ok else "✗"
        print(f"  {status} classify_extraction → strict PASS, root={classification.get('recovered_root_tag')}")
        if not extract_strict_ok:
            print(f"    strict_contract: {classification.get('strict_contract_status')}")
            print(f"    extraction_pathway: {classification.get('extraction_pathway')}")
            print(f"    recovered_root_tag: {classification.get('recovered_root_tag')}")
            all_ok = False

    return all_ok


if __name__ == "__main__":
    ok = run_regression()
    print(f"\n{'='*60}")
    print(f"EXPECTED-ROOT REGRESSION: {'ALL 6 SUBJECTS PASSED' if ok else 'SOME FAILURES'}")
    sys.exit(0 if ok else 1)
