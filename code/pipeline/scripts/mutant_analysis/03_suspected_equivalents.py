#!/usr/bin/env python3
"""
03_suspected_equivalents.py
===========================
Union-Pool Suspected-Equivalent Labeling
-----------------------------------------
Definition (following TOSEM conventions):

  A mutant is labeled `suspected_equivalent` if:
    (a) it survives ALL generated tests across ALL evaluated generation
        strategies (the union pool), AND
    (b) its mutated rule/location is exercised by at least one test in
        the union pool.

  A mutant that survives all tests but whose location is NEVER covered
  is labeled `survived_uncovered` (not triggered, not equivalent).

The union pool combines every test/config from:
  deepseek / qwen / gpt  ×  all prompt conditions

Outputs
~~~~~~~
  results_v2/analysis/suspected_equiv/
    {dataset}_suspected_equiv.csv
    {dataset}_sensitivity.json     – MS with/without suspected equivalents
    suspected_equiv_summary.csv    – cross-dataset table
    sensitivity_analysis.json      – full sensitivity table

  The sensitivity analysis reports:
    mutation_score_nominal         – killed / runnable (standard)
    mutation_score_excl_equiv      – killed / (runnable – suspected_equiv)
    ochiai_ac_nominal              – placeholder (needs SBFL scores)
    note if conclusions change

Usage
~~~~~
  python 03_suspected_equivalents.py [--base BASE_DIR] [--datasets d1 d2 ...]

Prerequisites
~~~~~~~~~~~~~
  Run 01_mutant_coverage.py first (produces coverage CSVs).
  Optionally run 02_mutant_type_breakdown.py (adds operator labels).
"""

import argparse
import csv
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

# ──────────────────────────────────────────────────────────────────────────────
DEFAULT_BASE = Path.home() / "research" / "llm_mt_experiment"
DATASETS     = ["BibTeX2DocBook", "CPL2SPL", "UML2ER", "Ecore2Maude"]
MODELS       = ["deepseek", "qwen", "gpt"]

MUTANT_FILE_RE = re.compile(
    r"output_(?P<tid>\d+)_(?P<dataset>.+?)_Mutant(?P<mid>\d+)_trace\.xmi$",
    re.IGNORECASE,
)
ORIG_FILE_RE = re.compile(
    r"output_(?P<tid>\d+)_trace\.xmi$",
    re.IGNORECASE,
)

# ──────────────────────────────────────────────────────────────────────────────
# Load helpers
# ──────────────────────────────────────────────────────────────────────────────

def load_coverage_csv(coverage_dir: Path, dataset: str) -> dict[int, dict]:
    """Return {mutant_id: row_dict} from 01_mutant_coverage output."""
    fp = coverage_dir / f"{dataset}_coverage_summary.csv"
    if not fp.exists():
        print(f"  [WARN] {fp} not found – run 01_mutant_coverage.py first.")
        return {}
    result = {}
    with open(fp, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                mid = int(row["mutant_id"])
                result[mid] = row
            except (KeyError, ValueError):
                pass
    return result


# ──────────────────────────────────────────────────────────────────────────────
# Build union pool kill/survive status from trace files
# ──────────────────────────────────────────────────────────────────────────────

def _outputs_differ(orig_path: Path, mutant_path: Path) -> bool:
    """
    Lightweight heuristic: two trace XMI files 'differ' (mutant killed) if
    their sizes differ by more than 5 % OR their content hashes differ.
    For proper mutation testing you'd compare actual model outputs; this is a
    proxy for when full oracle comparison is not available.

    If you have a proper kill oracle (e.g., from existing SBFL script), the
    load_kill_status_csv() path is used instead and this function is bypassed.
    """
    if not orig_path.exists() or not mutant_path.exists():
        return False
    os_orig   = orig_path.stat().st_size
    os_mutant = mutant_path.stat().st_size
    if os_orig == 0:
        return False
    ratio = abs(os_orig - os_mutant) / os_orig
    if ratio > 0.05:
        return True
    # Byte-level comparison (fast for small XMIs)
    return orig_path.read_bytes() != mutant_path.read_bytes()


def _load_kill_oracle_csv(results_v2: Path, dataset: str) -> dict[int, set[str]]:
    """
    Try to load pre-computed kill results from SBFL/oracle CSVs.
    Returns {mutant_id: set_of_test_ids_that_kill_it}.
    Falls back to empty dict if not found.
    """
    import glob as _glob
    killed_by: dict[int, set[str]] = defaultdict(set)
    patterns = [
        str(results_v2 / "analysis" / "sbfl" / f"{dataset}*kill*.csv"),
        str(results_v2 / "**" / "outputs" / dataset / "**" / "kill_matrix*.csv"),
    ]
    for pat in patterns:
        for fp in _glob.glob(pat, recursive=True):
            try:
                with open(fp, newline="", encoding="utf-8") as f:
                    for row in csv.DictReader(f):
                        mid  = row.get("mutant_id") or row.get("MutantID")
                        tid  = row.get("test_id")   or row.get("TestID")
                        stat = row.get("status",  "").lower()
                        if mid and tid and stat in {"killed", "kill", "1", "true"}:
                            killed_by[int(mid)].add(str(tid))
            except Exception:
                pass
    return killed_by


def build_union_pool_status(
    results_v2: Path,
    dataset: str,
    coverage_rows: dict[int, dict],
) -> dict[int, dict]:
    """
    For each mutant, determine its status in the union pool.
    Returns {mutant_id: {"killed_in_union": bool,
                          "killed_by_configs": list[str],
                          "covering_tests": int}}
    """
    # ── Try oracle CSV first ──────────────────────────────────────────────────
    oracle = _load_kill_oracle_csv(results_v2, dataset)

    # ── Build from trace files if oracle missing ──────────────────────────────
    # Structure: {mutant_id: {config_key: killed_bool}}
    mutant_status: dict[int, dict] = defaultdict(lambda: {
        "killed_in_union": False,
        "killed_by_configs": [],
        "covering_tests": 0,
    })

    # Seed from oracle
    for mid, tids in oracle.items():
        if tids:
            mutant_status[mid]["killed_in_union"] = True
            mutant_status[mid]["killed_by_configs"] = list(tids)

    # Augment from trace files (configs not in oracle)
    for model in MODELS:
        out_root = results_v2 / model / "outputs" / dataset
        if not out_root.exists():
            continue
        for config_dir in sorted(out_root.iterdir()):
            if not config_dir.is_dir():
                continue
            config_key = f"{model}/{config_dir.name}"

            # Map test_id -> original trace path
            orig_traces: dict[str, Path] = {}
            for xmi in config_dir.glob("output_*_trace.xmi"):
                m = ORIG_FILE_RE.match(xmi.name)
                if m:
                    orig_traces[m.group("tid")] = xmi

            # Check each mutant trace
            for xmi in config_dir.glob(f"output_*_{dataset}_Mutant*_trace.xmi"):
                m = MUTANT_FILE_RE.match(xmi.name)
                if not m:
                    continue
                tid = m.group("tid")
                mid = int(m.group("mid"))

                # Count covering tests
                mutant_status[mid]["covering_tests"] += 1

                # Already marked killed?
                if mutant_status[mid]["killed_in_union"]:
                    continue

                orig = orig_traces.get(tid)
                if orig and _outputs_differ(orig, xmi):
                    mutant_status[mid]["killed_in_union"] = True
                    mutant_status[mid]["killed_by_configs"].append(config_key)

    return dict(mutant_status)


# ──────────────────────────────────────────────────────────────────────────────
# Label mutants
# ──────────────────────────────────────────────────────────────────────────────

def label_mutants(
    coverage_rows:   dict[int, dict],
    union_status:    dict[int, dict],
) -> tuple[list[dict], dict]:
    """
    Apply TOSEM labeling:
      killed
      survived_uncovered      (not triggered)
      suspected_equivalent    (survived + covered)
      survived_covered        (survived + covered, not calling equiv yet – same as above but we
                               report both names for flexibility)

    Actually for the paper:
      survived + NOT covered  → survived_uncovered
      survived + covered      → suspected_equivalent  (TOSEM label)

    Returns (rows, counters).
    """
    rows = []
    counters = defaultdict(int)

    all_ids = set(coverage_rows.keys()) | set(union_status.keys())

    for mid in sorted(all_ids):
        cov_row  = coverage_rows.get(mid, {})
        u_status = union_status.get(mid, {})

        # Base classification from coverage script
        base_cls = cov_row.get("classification", "unknown")
        covered  = cov_row.get("location_covered", "n/a")
        op       = cov_row.get("mutation_op", "unknown_operator")
        rule     = cov_row.get("mutated_rule", "unknown")

        killed_in_union = u_status.get("killed_in_union", False)
        covering_tests  = u_status.get("covering_tests", 0)

        # Determine final label
        if base_cls == "compile_failed":
            label = "compile_failed"
        elif base_cls == "stillborn":
            label = "stillborn"
        elif killed_in_union or base_cls == "killed":
            label = "killed"
        else:
            # Survived in union pool
            if covered == "yes":
                label = "suspected_equivalent"
            elif covered == "no":
                label = "survived_uncovered"
            else:
                label = "survived_unknown_coverage"

        counters[label] += 1
        counters["total"] += 1

        rows.append({
            "mutant_id":           mid,
            "mutated_rule":        rule,
            "mutation_op":         op,
            "location_covered":    covered,
            "killed_in_union":     "yes" if killed_in_union else "no",
            "covering_tests":      covering_tests,
            "union_label":         label,
        })

    return rows, dict(counters)


# ──────────────────────────────────────────────────────────────────────────────
# Sensitivity analysis
# ──────────────────────────────────────────────────────────────────────────────

def sensitivity_analysis(counters: dict, dataset: str) -> dict:
    """
    Report mutation score with and without suspected equivalents.
    """
    killed   = counters.get("killed", 0)
    se       = counters.get("suspected_equivalent", 0)
    uncov    = counters.get("survived_uncovered", 0)
    unk      = counters.get("survived_unknown_coverage", 0)
    cf       = counters.get("compile_failed", 0)
    sb       = counters.get("stillborn", 0)

    runnable_nominal   = killed + se + uncov + unk          # all runnable
    runnable_excl_se   = killed + uncov + unk               # excl. suspected equiv
    runnable_excl_all  = killed + uncov                     # excl. equiv + unk coverage

    def ms(k, r): return round(k / r, 4) if r > 0 else None

    result = {
        "dataset":                    dataset,
        "compile_failed":             cf,
        "stillborn":                  sb,
        "runnable_nominal":           runnable_nominal,
        "killed":                     killed,
        "survived_uncovered":         uncov,
        "survived_unknown_coverage":  unk,
        "suspected_equivalent":       se,
        # MS variants
        "ms_nominal":                 ms(killed, runnable_nominal),
        "ms_excl_suspected_equiv":    ms(killed, runnable_excl_se),
        "ms_excl_se_and_unk":         ms(killed, runnable_excl_all),
        # Effective mutants definition
        "effective_mutants":          runnable_excl_se,
        "ms_effective":               ms(killed, runnable_excl_se),
        # Notes
        "conclusion_stable":          None,  # filled below
    }

    # Check stability
    if result["ms_nominal"] is not None and result["ms_excl_suspected_equiv"] is not None:
        diff = abs(result["ms_nominal"] - result["ms_excl_suspected_equiv"])
        result["conclusion_stable"] = "yes" if diff < 0.05 else "check_carefully"
        result["ms_delta"] = round(diff, 4)
    else:
        result["ms_delta"] = None

    return result


# ──────────────────────────────────────────────────────────────────────────────
# Output
# ──────────────────────────────────────────────────────────────────────────────

_ROW_FIELDS = [
    "mutant_id", "mutated_rule", "mutation_op",
    "location_covered", "killed_in_union", "covering_tests", "union_label",
]

def main():
    parser = argparse.ArgumentParser(description="Suspected-equivalent labeling")
    parser.add_argument("--base", default=str(DEFAULT_BASE))
    parser.add_argument("--datasets", nargs="+", default=DATASETS)
    args = parser.parse_args()

    base         = Path(args.base).expanduser()
    results_v2   = base / "results_v2"
    coverage_dir = results_v2 / "analysis" / "coverage"
    out_dir      = results_v2 / "analysis" / "suspected_equiv"
    out_dir.mkdir(parents=True, exist_ok=True)

    all_sensitivity = []
    summary_rows    = []

    for ds in args.datasets:
        print(f"\n[{ds}] Processing …")

        # Load coverage
        cov = load_coverage_csv(coverage_dir, ds)
        if not cov:
            continue

        # Build union pool status
        print(f"  Building union-pool kill status …")
        union_status = build_union_pool_status(results_v2, ds, cov)

        # Label
        rows, counters = label_mutants(cov, union_status)

        # Write detailed CSV
        csv_path = out_dir / f"{ds}_suspected_equiv.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=_ROW_FIELDS)
            w.writeheader()
            w.writerows(rows)
        print(f"  Wrote {csv_path}")

        # Sensitivity
        sens = sensitivity_analysis(counters, ds)
        json_path = out_dir / f"{ds}_sensitivity.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(sens, f, indent=2)
        print(f"  Wrote {json_path}")

        all_sensitivity.append(sens)
        summary_rows.append({
            "dataset":             ds,
            "runnable":            sens["runnable_nominal"],
            "killed":              sens["killed"],
            "survived_uncovered":  sens["survived_uncovered"],
            "suspected_equivalent":sens["suspected_equivalent"],
            "effective_mutants":   sens["effective_mutants"],
            "ms_nominal":          sens["ms_nominal"],
            "ms_excl_se":          sens["ms_excl_suspected_equiv"],
            "ms_delta":            sens["ms_delta"],
            "stable":              sens["conclusion_stable"],
        })

    if not all_sensitivity:
        print("\nNo results to summarise.")
        return

    # Write cross-dataset summary
    summ_path = out_dir / "suspected_equiv_summary.csv"
    with open(summ_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(summary_rows[0].keys()))
        w.writeheader()
        w.writerows(summary_rows)
    print(f"\n  Wrote {summ_path}")

    sens_path = out_dir / "sensitivity_analysis.json"
    with open(sens_path, "w", encoding="utf-8") as f:
        json.dump(all_sensitivity, f, indent=2)

    # Pretty print
    print("\n" + "="*80)
    print("SUSPECTED-EQUIVALENT SUMMARY  +  SENSITIVITY ANALYSIS")
    print("="*80)
    fmt = f"  {{:<20}} {{:>7}} {{:>7}} {{:>7}} {{:>7}} {{:>8}} {{:>8}} {{:>6}} {{:>8}}"
    print(fmt.format(
        "Dataset", "Run", "Killed", "Uncov", "SuspEq",
        "MS_nom", "MS_excl", "Delta", "Stable?",
    ))
    print("  " + "-"*78)
    for r in summary_rows:
        ms_n = f"{r['ms_nominal']:.3f}"   if r["ms_nominal"]  is not None else "  n/a"
        ms_x = f"{r['ms_excl_se']:.3f}"  if r["ms_excl_se"]  is not None else "  n/a"
        dlt  = f"{r['ms_delta']:.3f}"    if r["ms_delta"]    is not None else "  n/a"
        print(fmt.format(
            r["dataset"][:20],
            r["runnable"], r["killed"], r["survived_uncovered"],
            r["suspected_equivalent"], ms_n, ms_x, dlt, r["stable"] or "n/a",
        ))
    print("="*80)
    print("  Uncov   = survived + mutant location NOT covered (not triggered)")
    print("  SuspEq  = survived + location covered → suspected equivalent")
    print("  MS_nom  = killed / runnable (standard)")
    print("  MS_excl = killed / (runnable - suspected_equiv)  [sensitivity check]")
    print("  Stable? = yes if |MS_nom - MS_excl| < 0.05")

    print(f"\nDone. Results in: {out_dir}")


if __name__ == "__main__":
    main()
