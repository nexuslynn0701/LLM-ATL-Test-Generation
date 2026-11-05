#!/usr/bin/env python3
"""Structural checks for historical and current prompt versions."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.experiment.run_ladder_experiment import build_ladder_prompt

MANIFEST = ROOT / "reproducibility/frozen_prompts/manifest.json"


def _cases():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return manifest["rows"]






def test_latest_mode_has_no_section_residual():
    """latest fixes the June-2026 regression: removed sections must not
    leave separator/intro residual in lower tiers."""
    for ds in ("BibTeX2DocBook", "CPL2SPL", "UML2ER", "Ecore2Maude",
               "Ant2Maven", "Grafcet2PetriNet"):
        for cond in ("sm", "stm", "astm"):
            prompt, _m = build_ladder_prompt(ds, cond,
                                                 prompt_version="latest")
            assert "All generated source models must satisfy" not in prompt \
                or cond == "astmo", f"{ds}/{cond}: OCL intro residual"
            assert "Study this ATL transformation" not in prompt \
                or cond in ("astm", "astmo"), \
                f"{ds}/{cond}: ATL intro residual"


def test_historical_grafcet_residual_is_preserved():
    """Historical fidelity: the June Grafcet run DID contain residual —
    grafcet_202606 must reproduce it, not 'fix' it."""
    prompt, _m = build_ladder_prompt("Grafcet2PetriNet", "sm",
                                         prompt_version="grafcet_202606")
    assert "All generated source models must satisfy" in prompt, \
        "grafcet_202606/sm must reproduce the historical residual"
    assert "Study this ATL transformation" in prompt


def test_ant2maven_note_versioning():
    """run3_202606 uses the historical destfile note; latest uses jarfile."""
    hist = build_ladder_prompt("Ant2Maven", "sm", prompt_version="run3_202606")[0]
    latest = build_ladder_prompt("Ant2Maven", "sm", prompt_version="latest")[0]
    assert 'destfile="dist/app.jar"' in hist
    assert 'jarfile="dist/app.jar"' in latest


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {fn.__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} test functions passed")
    sys.exit(1 if failed else 0)
