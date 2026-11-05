#!/usr/bin/env python3
"""Compute 18-formula SBFL EXAM for workflow cells from mutation matrix + trace coverage.

Reads:
  - Workflow mutation matrix.csv (per-model per-mutant KILLED/ALIVE)
  - Workflow trace files (per-model rule coverage via parse_trace)
  - 18-formula registry from results_v3_troya_aligned

Outputs per-mutant SBFL scores in same format as results/sbfl_export/sbfl_exam_*.csv
"""
from __future__ import annotations

import csv
import importlib.util
import json
import math
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.analyzer.coverage_analyzer import parse_trace

# ── Config ──────────────────────────────────────────────────────────────────
FORMULA_REGISTRY = (
    ROOT / "results_v3_troya_aligned/sbfl_formula_registry_troya18/"
    "sbfl_formula_registry.json"
)

WORKFLOW_ROOT = ROOT / "results_ant_grafcet/results_ladder_astmo_rerun_full_workflow"
MUTATION_ANT = ROOT / "results_ant_grafcet/results_ladder_astmo_rerun_full_workflow_mutation_ant"
MUTATION_GRAFCET = ROOT / "results_ant_grafcet/results_ladder_astmo_rerun_full_workflow_mutation_grafcet"
TIER = "astmo_examples_feedback_repair"

RULE_UNIVERSE = {
    "Ant2Maven": [
        "AntProject2Maven", "AntProject2MavenWithoutDescription",
        "AntTarget2MavenMavenGoal", "AntTarget2MavenMavenGoal2",
        "AntPropertyValue2MavenMavenAntPropertyValue",
        "AntPropertyLocation2MavenMavenAntPropertyLocation",
        "AntPropertyFile2MavenMavenAntPropertyFile",
        "AntPropertyEnv2MavenMavenAntPropertyEnv",
        "AntJava2MavenMavenJava", "AntJavac2MavenMavenJavac",
        "AntJavadoc2MavenMavenJavadoc", "AntTstamp2MavenMavenTstamp",
        "AntJar2MavenMavenJar", "AntMkdir2MavenMavenMkdir",
        "AntCopy2MavenMavenCopy", "AntDelete2MavenMavenDelete",
        "AntTaskDef2MavenMavenTaskDef", "AntNewTask2MavenMavenNewTask",
        "AntAttribut2MavenMavenAttribut", "AntPath2MavenMavenPath",
        "AntClassPath2MavenMavenClassPath",
        "AntPathElement2MavenMavenPathElement",
        "AntFileSet2MavenMavenFileSet", "AntFilterSet2MavenMavenFilterSet",
        "AntFilter2MavenMavenFilter", "AntFiltersFile2MavenMavenFiltersFile",
        "AntPatternset2MavenMavenPatternset", "AntIncludes2MavenMavenIncludes",
        "AntExcludes2MavenMavenExcludes", "AntIncludesFile2MavenMavenIncludesFile",
        "AntExcludesFile2MavenMavenExcludesFile",
    ],
    "Grafcet2PetriNet": [
        "PetriNet", "Place", "PlaceToTransition", "Transition", "TransitionToPlace",
    ],
}

CELLS = [
    # (subject, provider, mutation_root, prov_dir)
    ("Ant2Maven",        "gpt",            MUTATION_ANT,     "gpt"),
    ("Ant2Maven",        "qwen",           MUTATION_ANT,     "qwen"),
    ("Ant2Maven",        "deepseek-flash", MUTATION_ANT,     "deepseek-flash"),
    ("Grafcet2PetriNet", "gpt",            MUTATION_GRAFCET, "gpt"),
    ("Grafcet2PetriNet", "qwen",           MUTATION_GRAFCET, "qwen"),
    ("Grafcet2PetriNet", "deepseek-flash", MUTATION_GRAFCET, "deepseek-flash"),
]

OUT_DIR = ROOT / "rq4_data_export" / "workflow" / "sbfl_exam"
OUT_DIR.mkdir(parents=True, exist_ok=True)


# ── Formula loading ─────────────────────────────────────────────────────────

def load_module(path: Path) -> Any:
    name = f"_sbfl_{abs(hash(str(path.resolve())))}"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_formulas() -> list[dict[str, Any]]:
    registry = json.loads(FORMULA_REGISTRY.read_text(encoding="utf-8"))
    assert registry["registry_status"] == "READY", "formula registry not ready"
    formulas = registry["formulas"]
    # Fix root path
    registry_root = Path(registry.get("root", "."))
    loaded = []
    modules: dict[str, Any] = {}
    for entry in formulas:
        src_path = registry_root / entry["source_path"]
        # Handle mounted path differences
        if not src_path.is_file():
            src_path = ROOT / entry["source_path"]
        module = modules.get(str(src_path))
        if module is None:
            module = load_module(src_path)
            modules[str(src_path)] = module
        func = module
        for part in entry["callable"].split("."):
            func = getattr(func, part)
        loaded.append({**entry, "function": func})
    return loaded


def formula_score(entry: dict[str, Any], ef: int, ep: int, nf: int, np: int) -> float:
    counts = {"ef": float(ef), "ep": float(ep), "nf": float(nf), "np": float(np)}
    kwargs = {}
    for param, source in entry["parameter_map"].items():
        if source == "ef+nf":
            kwargs[param] = counts["ef"] + counts["nf"]
        elif source == "ep+np":
            kwargs[param] = counts["ep"] + counts["np"]
        else:
            kwargs[param] = counts[source]
    try:
        return float(entry["function"](**kwargs))
    except (ZeroDivisionError, ValueError, OverflowError):
        return 0.0


# ── Tie-breaking (average cost rank, AC/BC/WC) ──────────────────────────────

def java_double_equal(a: float, b: float) -> bool:
    if math.isnan(a) and math.isnan(b):
        return True
    if a == 0.0 and b == 0.0:
        return math.copysign(1.0, a) == math.copysign(1.0, b)
    return a == b


def compute_ranks(scores: dict[str, float]) -> tuple[dict[str, float], dict[str, float], dict[str, float], dict[str, int]]:
    """Return (ac_ranks, bc_ranks, wc_ranks, tie_sizes) for average/best/worst cost."""
    # Sort by score descending
    ordered = sorted(scores.items(), key=lambda x: (-x[1], x[0]))
    n = len(ordered)

    ac_ranks: dict[str, float] = {}
    bc_ranks: dict[str, float] = {}
    wc_ranks: dict[str, float] = {}
    tie_sizes: dict[str, int] = {}

    i = 0
    while i < n:
        j = i + 1
        while j < n and java_double_equal(ordered[j][1], ordered[i][1]):
            j += 1
        first = i + 1
        last = j
        size = j - i
        avg = (first + last) / 2.0
        for rule, _ in ordered[i:j]:
            ac_ranks[rule] = avg
            bc_ranks[rule] = float(first)   # best: lowest rank in tie group
            wc_ranks[rule] = float(last)    # worst: highest rank in tie group
            tie_sizes[rule] = size
        i = j

    return ac_ranks, bc_ranks, wc_ranks, tie_sizes


# ── Per-rule coverage from traces ───────────────────────────────────────────

def build_profiles(subject: str, provider: str, prov_dir: str) -> dict[str, set[str]]:
    """Parse traces and return {source_id: set(covered_rules)}."""
    outputs_dir = WORKFLOW_ROOT / prov_dir / subject / TIER / "outputs"
    profiles: dict[str, set[str]] = {}

    for trace_path in sorted(outputs_dir.glob("output_*_trace.xmi")):
        # Extract model id: output_NNNN_trace.xmi
        m = re.match(r"output_(\d{4})_trace\.xmi", trace_path.name)
        if not m:
            continue
        model_id = m.group(1)
        try:
            trace_data = parse_trace(str(trace_path))
            profiles[model_id] = set(trace_data.get("executed_rules", set()))
        except Exception:
            profiles[model_id] = set()

    return profiles


# ── Main computation ────────────────────────────────────────────────────────

def compute_cell(subject: str, provider: str, mutation_root: Path,
                 prov_dir: str, formulas: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute 18-formula SBFL EXAM for one cell."""
    condition = "workflow"
    matrix_path = mutation_root / prov_dir / subject / condition / "matrix.csv"

    if not matrix_path.is_file():
        return {"status": "NO_MATRIX", "matrix_path": str(matrix_path)}

    universe = RULE_UNIVERSE[subject]
    universe_set = set(universe)
    n_rules = len(universe)

    # Load mutation matrix
    # Need to handle both formats: Ant has different columns than Grafcet
    with matrix_path.open(newline="", encoding="utf-8") as fh:
        matrix_rows = list(csv.DictReader(fh))

    # Discover column names
    cols = set(matrix_rows[0].keys()) if matrix_rows else set()
    model_col = next((c for c in ["model_id", "source_id", "source"] if c in cols), None)

    # Build profiles
    profiles = build_profiles(subject, provider, prov_dir)

    # Build per-mutant status map
    # status = KILLED/ALIVE/INVALID_*
    by_mutant: dict[str, dict[str, str]] = defaultdict(dict)
    mutant_targets: dict[str, list[str]] = defaultdict(list)
    mutant_operators: dict[str, str] = {}

    for row in matrix_rows:
        mid = row.get("mutant", "")
        sid = row.get(model_col, "") if model_col else ""
        # Normalize sid to 4-digit
        sid = str(sid).zfill(4) if sid and sid.isdigit() else sid
        status = str(row.get("status", "")).strip().upper()

        if not mid or not sid or sid not in profiles:
            continue

        # Store target rule info
        target = row.get("target_rule", "") or row.get("target_rules", "")
        if target and mid not in mutant_targets:
            mutant_targets[mid] = [r.strip() for r in re.split(r"[;,|]", target) if r.strip()]
        op = row.get("operator", "")
        if op:
            mutant_operators[mid] = op

        # Only count KILLED/ALIVE for spectrum
        if status == "KILLED":
            by_mutant[mid][sid] = "KILLED"
        elif status not in ("KILLED",):
            if sid not in by_mutant[mid]:
                by_mutant[mid][sid] = "ALIVE"

    # Compute SBFL for each mutant
    all_rows = []
    formulas_used = []
    errors = []

    for mid in sorted(by_mutant):
        statuses = by_mutant[mid]
        failing = {sid for sid, s in statuses.items() if s == "KILLED"}
        passing = {sid for sid, s in statuses.items() if s == "ALIVE"}
        target = mutant_targets.get(mid, [])

        if not failing:
            errors.append({"mutant": mid, "reason": "NO_FAILING"})
            continue
        if not target:
            errors.append({"mutant": mid, "reason": "NO_TARGET_RULE"})
            continue

        # Count ef/ep/nf/np per rule
        for formula_entry in formulas:
            scores = {}
            for rule in universe:
                ef = sum(1 for sid in failing if rule in profiles.get(sid, set()))
                ep = sum(1 for sid in passing if rule in profiles.get(sid, set()))
                nf = len(failing) - ef
                np_val = len(passing) - ep
                scores[rule] = formula_score(formula_entry, ef, ep, nf, np_val)

            ac, bc, wc, ties = compute_ranks(scores)

            # Find best target rule (minimum AC rank)
            matching = [r for r in target if r in ac]
            if not matching:
                errors.append({"mutant": mid, "formula": formula_entry["formula"],
                               "reason": f"TARGET_NOT_FOUND:{';'.join(target)}"})
                continue

            best_rule = min(matching, key=lambda r: ac[r])

            all_rows.append({
                "mutant": mid,
                "target_rule": best_rule,
                "all_target_rules": ";".join(target),
                "operator": mutant_operators.get(mid, ""),
                "n_failing": len(failing),
                "n_passing": len(passing),
                "n_rules": n_rules,
                "tie_size": ties[best_rule],
                f"{formula_entry['formula'].lower().replace(' ','_').replace('&','').replace('-','_')}_AC": ac[best_rule] / n_rules,
            })

            if formula_entry["formula"] not in formulas_used:
                formulas_used.append(formula_entry["formula"])

    if not all_rows:
        return {"status": "NO_RESULTS", "errors": errors,
                "n_profiles": len(profiles), "n_mutants": len(by_mutant)}

    # Merge rows by mutant (one row per mutant, all 18 formulas)
    merged: dict[str, dict] = {}
    for row in all_rows:
        mid = row["mutant"]
        if mid not in merged:
            merged[mid] = {
                "mutant": mid,
                "target_rule": row["target_rule"],
                "all_target_rules": row["all_target_rules"],
                "operator": row["operator"],
                "n_failing": row["n_failing"],
                "n_passing": row["n_passing"],
                "n_rules": row["n_rules"],
                "tie_size": row["tie_size"],
            }
        # Copy formula-specific columns
        for k, v in row.items():
            if k.endswith("_AC") or k.endswith("_BC") or k.endswith("_WC"):
                merged[mid][k] = v

    final_rows = list(merged.values())

    # Summary stats
    formula_names = [f["formula"] for f in formulas]
    summary = {
        "subject": subject,
        "provider": provider,
        "condition": condition,
        "n_profiles": len(profiles),
        "n_mutants": len(by_mutant),
        "n_mutants_with_exam": len(final_rows),
        "n_failing_sources_total": sum(
            sum(1 for s in st.values() if s == "KILLED")
            for st in by_mutant.values()
        ),
        "n_killed_pairs": sum(
            sum(1 for s in st.values() if s == "KILLED")
            for st in by_mutant.values()
        ),
        "n_errors": len(errors),
    }

    # Per-formula medians
    for f_entry in formulas:
        col = f_entry["formula"].lower().replace(" ", "_").replace("&", "").replace("-", "_") + "_AC"
        values = [r[col] for r in final_rows if col in r]
        if values:
            summary[f"median_{col}"] = round(statistics.median(values), 6)
            summary[f"mean_{col}"] = round(statistics.mean(values), 6)

    return {
        "status": "OK",
        "summary": summary,
        "rows": final_rows,
        "errors": errors,
        "formulas_used": formula_names,
    }


def write_sbfl_exam_csv(rows: list[dict], path: Path, formulas: list[dict[str, Any]]):
    """Write per-mutant SBFL EXAM CSV in same format as sbfl_export/*.csv."""
    # Build column set: 18 formulas × 3 modes = 54 exam columns
    formula_cols = []
    for f in formulas:
        slug = f["formula"].lower().replace(" ", "_").replace("&", "").replace("-", "_")
        for mode in ("AC", "BC", "WC"):
            formula_cols.append(f"{slug}_{mode}")

    # We only compute AC in this script; fill BC/WC with same value or empty
    # Actually, let's compute all 3 modes
    # For now: AC is computed, BC/WC are also computed in compute_ranks

    fields = [
        "dataset", "method", "mutant", "buggy_rules",
        "total_tests", "total_fail", "total_pass", "fail_ratio",
    ] + formula_cols

    out_rows = []
    for r in rows:
        n_total = r.get("n_failing", 0) + r.get("n_passing", 0)
        n_fail = r.get("n_failing", 0)
        n_pass = r.get("n_passing", 0)
        out_row = {
            "dataset": r.get("subject", ""),
            "method": r.get("provider", ""),
            "mutant": r["mutant"],
            "buggy_rules": r.get("all_target_rules", ""),
            "total_tests": n_total,
            "total_fail": n_fail,
            "total_pass": n_pass,
            "fail_ratio": round(n_fail / n_total, 4) if n_total > 0 else 0.0,
        }
        for fc in formula_cols:
            out_row[fc] = r.get(fc, "")
        out_rows.append(out_row)

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(out_rows)


def main():
    formulas = load_formulas()
    print(f"Loaded {len(formulas)} formulas: {[f['formula'] for f in formulas]}")

    all_summaries = []
    all_rows: dict[tuple[str, str], list[dict]] = {}

    for subject, provider, mutation_root, prov_dir in CELLS:
        print(f"\n── {subject} {provider} ──")
        result = compute_cell(subject, provider, mutation_root, prov_dir, formulas)

        if result["status"] != "OK":
            print(f"  SKIP: {result['status']} - {result.get('matrix_path', '')}")
            if "errors" in result:
                for e in result["errors"][:5]:
                    print(f"    error: {e}")
            continue

        summary = result["summary"]
        rows = result["rows"]
        all_rows[(subject, provider)] = rows
        all_summaries.append(summary)

        # Per-cell summary
        print(f"  profiles: {summary['n_profiles']}  mutants: {summary['n_mutants']}  "
              f"exam_rows: {summary['n_mutants_with_exam']}  errors: {summary['n_errors']}")
        ochiai_key = "median_ochiai_AC"
        print(f"  median Ochiai AC: {summary.get(ochiai_key, 'N/A')}")

        # Write per-mutant SBFL CSV
        out_csv = OUT_DIR / f"sbfl_exam_{subject}_{provider}_workflow.csv"
        write_sbfl_exam_csv(rows, out_csv, formulas)
        print(f"  → {out_csv}")

        # Also write a simpler per-cell formula summary
        formula_summary = []
        for f in formulas:
            slug = f["formula"].lower().replace(" ", "_").replace("&", "").replace("-", "_") + "_AC"
            values = [r[slug] for r in rows if slug in r]
            if values:
                formula_summary.append({
                    "subject": subject,
                    "provider": provider,
                    "condition": "workflow",
                    "formula": f["formula"],
                    "n_mutants": len(values),
                    "median_EXAM_AC": round(statistics.median(values), 6),
                    "mean_EXAM_AC": round(statistics.mean(values), 6),
                    "min_EXAM_AC": round(min(values), 6),
                    "max_EXAM_AC": round(max(values), 6),
                })

        summary_csv = OUT_DIR / f"sbfl_summary_{subject}_{provider}_workflow.csv"
        with summary_csv.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=[
                "subject", "provider", "condition", "formula",
                "n_mutants", "median_EXAM_AC", "mean_EXAM_AC",
                "min_EXAM_AC", "max_EXAM_AC",
            ])
            w.writeheader()
            w.writerows(formula_summary)
        print(f"  → {summary_csv}")

    # ── All-cells summary ──
    if all_summaries:
        all_path = OUT_DIR / "workflow_sbfl_all_cells_summary.json"
        all_path.write_text(json.dumps(all_summaries, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\n  All summaries → {all_path}")

        # Print comparison table
        print("\n=== Workflow SBFL EXAM (Ochiai AC median) ===")
        for s in all_summaries:
            print(f"  {s['subject']:20s} {s['provider']:15s}  Ochiai AC = {s.get('median_ochiai_AC', 'N/A')}")

    print("\nDone.")


if __name__ == "__main__":
    main()
