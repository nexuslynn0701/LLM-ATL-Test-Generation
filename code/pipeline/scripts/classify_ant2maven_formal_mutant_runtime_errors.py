#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SRC = (
    ROOT / "results_v3_troya_aligned/"
    "ant2maven_formal_mutant_runtime_diagnosis/summary.json"
)
OUT = (
    ROOT / "results_v3_troya_aligned/"
    "ant2maven_formal_mutant_runtime_diagnosis/classification.json"
)

WARNING = "containment references cannot span across models"

data = json.loads(SRC.read_text(encoding="utf-8"))
rows = []

for mutant in data["mutants"]:
    build_runs = [r for r in mutant["runs"] if r["source"] == "buildAnt"]
    minimal_run = next(r for r in mutant["runs"] if r["source"] == "minimal")

    combined = "\n".join(
        (r.get("stdout") or "") + "\n" +
        (r.get("stderr") or "") + "\n" +
        (r.get("error") or "")
        for r in build_runs
    )

    if WARNING in combined:
        category = "rejected_containment_warning"
    elif "VMException" in combined or "Exception" in combined:
        category = "runtime_exception"
    elif any(not r.get("outputs") for r in build_runs):
        category = "missing_declared_outputs"
    else:
        category = "other"

    row = {
        "mutant": mutant["mutant"],
        "category": category,
        "operators": mutant["sub_operators"],
        "target_rules": mutant["target_rules"],
        "buildAnt_successes": [r["success"] for r in build_runs],
        "buildAnt_returncodes": [r["returncode"] for r in build_runs],
        "minimal_success": minimal_run["success"],
        "error_tail": combined[-3000:],
    }
    rows.append(row)

print("================ configured smoke input ================")
from src.experiment.multi_config_experiment import DATASETS
print(DATASETS["Ant2Maven"].get("smoke_input"))

print("\n================ classifications ================")
print(Counter(row["category"] for row in rows))

for row in rows:
    print(f'\n---- {row["mutant"]}: {row["category"]}')
    print("operators:", row["operators"])
    print("rules:", row["target_rules"])
    print("error tail:")
    print(row["error_tail"])

OUT.write_text(json.dumps(rows, indent=2), encoding="utf-8")
print("\nWrote:", OUT)
