#!/usr/bin/env python3
"""
02_mutant_type_breakdown.py
===========================
Mutant-Type Breakdown by Mutation Operator
-------------------------------------------
Classifies each mutant by its mutation operator, then reports:
  - total / runnable / killed / survived per operator per dataset
  - kill rate and survival rate per operator
  - cross-dataset aggregate

Reads from:
  1. results_v2/analysis/coverage/{dataset}_coverage_summary.csv  (from script 01)
  2. datasets/models_{dataset}/transformations/  (ATL files, for operator labels)
     Falls back to filename-embedded operator tokens if CSV already has them.

Outputs
~~~~~~~
  results_v2/analysis/mutation_types/
    {dataset}_operator_breakdown.csv
    {dataset}_operator_breakdown.json
    operator_breakdown_overall.csv   – summed over all datasets
    operator_breakdown_overall.json

Usage
~~~~~
  python 02_mutant_type_breakdown.py [--base BASE_DIR] [--datasets d1 d2 ...]
"""

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

# ──────────────────────────────────────────────────────────────────────────────
DEFAULT_BASE = Path.home() / "research" / "llm_mt_experiment"
DATASETS     = ["BibTeX2DocBook", "CPL2SPL", "UML2ER", "Ecore2Maude"]

MUTATION_OPS_DISPLAY = {
    "rule_deletion":              "RD  – Rule Deletion",
    "binding_feature_change":     "BFC – Binding Feature Change",
    "binding_value_change":       "BVC – Binding Value Change",
    "guard_mutation":             "GM  – Guard Mutation",
    "navigation_mutation":        "NM  – Navigation Mutation",
    "helper_expression_mutation": "HEM – Helper Expression Mutation",
    "unknown_operator":           "UNK – Unknown",
}

# Equivalence-prone operators (documented in mutation testing literature)
# These are used to add a qualitative note in the output.
EQUIV_PRONE = {"binding_value_change", "helper_expression_mutation", "navigation_mutation"}

# ──────────────────────────────────────────────────────────────────────────────
# Load coverage CSV produced by script 01
# ──────────────────────────────────────────────────────────────────────────────

def load_coverage_csv(coverage_dir: Path, dataset: str) -> list[dict]:
    fp = coverage_dir / f"{dataset}_coverage_summary.csv"
    if not fp.exists():
        print(f"  [WARN] Coverage CSV not found: {fp}  (run 01_mutant_coverage.py first)")
        return []
    rows = []
    with open(fp, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append(row)
    return rows


# ──────────────────────────────────────────────────────────────────────────────
# Compute per-operator stats
# ──────────────────────────────────────────────────────────────────────────────

def compute_breakdown(rows: list[dict], dataset: str) -> tuple[list[dict], dict]:
    """
    Returns (detail_rows, operator_stats_dict).
    operator_stats_dict: { op_label: { total, compile_failed, stillborn,
                                        runnable, killed, survived_covered,
                                        survived_uncovered, kill_rate } }
    """
    op_stats: dict[str, dict] = defaultdict(lambda: defaultdict(int))

    for row in rows:
        op    = row.get("mutation_op", "unknown_operator") or "unknown_operator"
        cls   = row.get("classification", "unknown")

        op_stats[op]["total"] += 1
        if cls == "compile_failed":
            op_stats[op]["compile_failed"] += 1
        elif cls == "stillborn":
            op_stats[op]["stillborn"] += 1
        elif cls == "killed":
            op_stats[op]["killed"]   += 1
            op_stats[op]["runnable"] += 1
        elif cls in {"survived_covered", "survived_uncovered", "survived_unknown_coverage"}:
            op_stats[op]["survived"] += 1
            op_stats[op]["runnable"] += 1
            if cls == "survived_covered":
                op_stats[op]["survived_covered"]   += 1
            elif cls == "survived_uncovered":
                op_stats[op]["survived_uncovered"] += 1
        else:
            op_stats[op]["unknown_status"] += 1

    detail_rows = []
    for op, s in sorted(op_stats.items()):
        runnable  = s["runnable"]
        killed    = s["killed"]
        survived  = s["survived"]
        kill_rate = round(killed / runnable, 4) if runnable > 0 else None
        surv_rate = round(survived / runnable, 4) if runnable > 0 else None
        detail_rows.append({
            "dataset":              dataset,
            "mutation_op":          op,
            "op_display":           MUTATION_OPS_DISPLAY.get(op, op),
            "equiv_prone":          "yes" if op in EQUIV_PRONE else "no",
            "total":                s["total"],
            "compile_failed":       s["compile_failed"],
            "stillborn":            s["stillborn"],
            "runnable":             runnable,
            "killed":               killed,
            "survived_total":       survived,
            "survived_covered":     s["survived_covered"],
            "survived_uncovered":   s["survived_uncovered"],
            "kill_rate":            kill_rate,
            "survival_rate":        surv_rate,
        })

    return detail_rows, dict(op_stats)


# ──────────────────────────────────────────────────────────────────────────────
# Cross-dataset aggregate
# ──────────────────────────────────────────────────────────────────────────────

def aggregate_across_datasets(all_detail: dict[str, list[dict]]) -> list[dict]:
    """Sum numeric fields across datasets for each operator."""
    combined: dict[str, dict] = defaultdict(lambda: defaultdict(int))
    int_fields = [
        "total", "compile_failed", "stillborn", "runnable",
        "killed", "survived_total", "survived_covered", "survived_uncovered",
    ]
    op_display_map: dict[str, str] = {}

    for dataset, rows in all_detail.items():
        for row in rows:
            op = row["mutation_op"]
            op_display_map[op] = row["op_display"]
            for f in int_fields:
                combined[op][f] += int(row.get(f) or 0)

    result = []
    for op, s in sorted(combined.items()):
        runnable  = s["runnable"]
        killed    = s["killed"]
        survived  = s["survived_total"]
        result.append({
            "mutation_op":          op,
            "op_display":           op_display_map.get(op, op),
            "equiv_prone":          "yes" if op in EQUIV_PRONE else "no",
            "total":                s["total"],
            "compile_failed":       s["compile_failed"],
            "stillborn":            s["stillborn"],
            "runnable":             runnable,
            "killed":               killed,
            "survived_total":       survived,
            "survived_covered":     s["survived_covered"],
            "survived_uncovered":   s["survived_uncovered"],
            "kill_rate":            round(killed / runnable, 4) if runnable > 0 else None,
            "survival_rate":        round(survived / runnable, 4) if runnable > 0 else None,
        })

    return result


# ──────────────────────────────────────────────────────────────────────────────
# Output helpers
# ──────────────────────────────────────────────────────────────────────────────

_DETAIL_FIELDS = [
    "dataset", "mutation_op", "op_display", "equiv_prone",
    "total", "compile_failed", "stillborn", "runnable",
    "killed", "survived_total", "survived_covered", "survived_uncovered",
    "kill_rate", "survival_rate",
]

def print_table(rows: list[dict], title: str):
    print(f"\n{'='*80}")
    print(f"  {title}")
    print(f"{'='*80}")
    fmt = f"  {{:<28}} {{:>5}} {{:>7}} {{:>7}} {{:>9}} {{:>9}}"
    print(fmt.format("Operator", "Run", "Killed", "Surv", "KillRate", "SurvRate"))
    print(f"  {'-'*78}")
    for r in rows:
        kr = f"{r['kill_rate']:.3f}" if r["kill_rate"] is not None else "  n/a"
        sr = f"{r['survival_rate']:.3f}" if r["survival_rate"] is not None else "  n/a"
        ep = " *" if r["equiv_prone"] == "yes" else "  "
        print(fmt.format(
            r["op_display"][:28] + ep,
            r["runnable"], r["killed"], r["survived_total"], kr, sr,
        ))
    print(f"\n  (* = operator documented as equivalence-prone in mutation testing literature)")


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Mutant-type breakdown by operator")
    parser.add_argument("--base", default=str(DEFAULT_BASE))
    parser.add_argument("--datasets", nargs="+", default=DATASETS)
    args = parser.parse_args()

    base         = Path(args.base).expanduser()
    results_v2   = base / "results_v2"
    coverage_dir = results_v2 / "analysis" / "coverage"
    out_dir      = results_v2 / "analysis" / "mutation_types"
    out_dir.mkdir(parents=True, exist_ok=True)

    all_detail: dict[str, list[dict]] = {}

    for ds in args.datasets:
        print(f"\n[{ds}] Loading coverage data …")
        rows = load_coverage_csv(coverage_dir, ds)
        if not rows:
            print(f"  Skipping {ds} (no data).")
            continue

        detail_rows, _ = compute_breakdown(rows, ds)
        all_detail[ds] = detail_rows

        # Write per-dataset CSV
        csv_path = out_dir / f"{ds}_operator_breakdown.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=_DETAIL_FIELDS)
            w.writeheader()
            w.writerows(detail_rows)
        print(f"  Wrote {csv_path}")

        # Write per-dataset JSON
        json_path = out_dir / f"{ds}_operator_breakdown.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(detail_rows, f, indent=2)

        print_table(detail_rows, f"Operator Breakdown – {ds}")

    if not all_detail:
        print("\nNo data to aggregate. Exiting.")
        return

    # Cross-dataset aggregate
    overall = aggregate_across_datasets(all_detail)
    overall_csv = out_dir / "operator_breakdown_overall.csv"
    overall_json = out_dir / "operator_breakdown_overall.json"

    overall_fields = [f for f in _DETAIL_FIELDS if f != "dataset"]
    with open(overall_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=overall_fields)
        w.writeheader()
        w.writerows(overall)
    print(f"\n  Wrote {overall_csv}")

    with open(overall_json, "w", encoding="utf-8") as f:
        json.dump(overall, f, indent=2)

    print_table(overall, "Operator Breakdown – ALL DATASETS (aggregated)")

    # Narrative note for paper
    print("\n  INTERPRETATION NOTE FOR PAPER")
    print("  " + "-"*60)
    for r in overall:
        if r["equiv_prone"] == "yes" and r["survival_rate"] is not None and r["survival_rate"] > 0.3:
            print(f"  ⚠  {r['op_display']}: survival rate = {r['survival_rate']:.1%} "
                  f"(equiv-prone operator – expected)")
    print("  " + "-"*60)
    print("  Equivalence-prone operators: BVC, HEM, NM")
    print("  High survival in these categories supports the suspected-equivalent hypothesis.")

    print(f"\nDone. Results in: {out_dir}")


if __name__ == "__main__":
    main()