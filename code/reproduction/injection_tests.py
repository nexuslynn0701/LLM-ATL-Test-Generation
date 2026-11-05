#!/usr/bin/env python3
"""Injection tests for the rebuild validators (2026-11-05 audit follow-up).

Each case tampers with validator inputs IN MEMORY ONLY (a read_csv stand-in
that mutates rows after reading; no file on disk is modified) and asserts
that the step now FAILS. A pass here means a false-pass of the kind found by
the acceptance audit can no longer slip through.
"""
from __future__ import annotations

import copy
import csv
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "code/reproduction"))
import build_tables as bt  # noqa: E402

RESULTS = []

REAL_DESKTOP = ROOT / "results/experiment_results"


def patched_read_csv(mutator):
    original = bt.read_csv

    def stand_in(path):
        rows = original(path)
        normalised = str(path).replace(chr(92), "/")
        out = mutator(normalised, copy.deepcopy(rows))
        return out if out is not None else rows

    return original, stand_in


def run_case(name, fn):
    ok, detail = fn()
    RESULTS.append((name, ok, detail))
    print(("PASS " if ok else "FALSE-PASS") + f"  {name}: {detail}")


def case_top1_tampered():
    """Desktop top1_rates GPT-SM 98.947... -> 105.947... must be caught."""
    def mutate(path, rows):
        if path.endswith("RQ3/top1_rates.csv") and str(REAL_DESKTOP).replace(chr(92), "/") + "/" in path:
            rows[0]["GPT-SM"] = "105.947368421052632"
        return rows
    orig, stand = patched_read_csv(mutate)
    bt.read_csv = stand
    try:
        label, verdict, details = bt.emit_mirror()
    finally:
        bt.read_csv = orig
    caught = verdict == "MISMATCH" and any("GPT-SM" in d and "105.947" in d for d in details)
    return caught, f"verdict={verdict}; real-diff line present={caught}"


def case_mutation_tampered():
    """Desktop mutation_results row 0 killed_mutants +7 must be caught."""
    def mutate(path, rows):
        if path.endswith("RQ2/mutation_results.csv") and str(REAL_DESKTOP).replace(chr(92), "/") + "/" in path:
            rows[0]["killed_mutants"] = str(int(rows[0]["killed_mutants"]) + 7)
        return rows
    orig, stand = patched_read_csv(mutate)
    bt.read_csv = stand
    try:
        label, verdict, details = bt.emit_mirror()
    finally:
        bt.read_csv = orig
    caught = verdict == "MISMATCH" and any("killed_mutants" in d and "row 0" in d for d in details)
    return caught, f"verdict={verdict}; row-0 kill diff present={caught}"


def case_validity_100_1():
    """validity GPT/SM/Ant2Maven 100.0 -> 100.1 must be a REAL difference
    (100/100 attempts cannot round to 100.1)."""
    def mutate(path, rows):
        if path.endswith("RQ1/validity.csv") and str(REAL_DESKTOP).replace(chr(92), "/") + "/" in path:
            for r in rows:
                if r.get("Generator") == "Gpt" and r.get("Cond.") == "SM":
                    r["Ant2Maven"] = "100.1"
        return rows
    orig, stand = patched_read_csv(mutate)
    bt.read_csv = stand
    try:
        label, verdict, details = bt.emit_mirror()
    finally:
        bt.read_csv = orig
    caught = verdict == "MISMATCH" and any("Ant2Maven" in d and "100.1" in d for d in details)
    return caught, f"verdict={verdict}; 100.1 flagged as real={caught}"


def case_rq4_missing_anchor():
    """Removing the DeepSeek-Flash-SM pooled anchor must fail the RQ4 step."""
    def mutate(path, rows):
        if path.endswith("mutation_score_overall_pooled.csv") and "/results/" in path:
            rows = [r for r in rows if r["method_id"] != "DeepSeek-Flash-SM"]
        return rows
    orig, stand = patched_read_csv(mutate)
    bt.read_csv = stand
    try:
        label, verdict, details = bt.rq4_four_columns()
    finally:
        bt.read_csv = orig
    caught = verdict == "MISMATCH" and any("23/24" in d for d in details)
    return caught, f"verdict={verdict}; 23/24 guard fired={caught}"


def case_missing_column():
    def mutate(path, rows):
        if path == str(REAL_DESKTOP / "RQ2/mutation_results.csv").replace(chr(92), "/"):
            for row in rows:
                row.pop("killed_mutants")
        return rows
    orig, stand = patched_read_csv(mutate)
    bt.read_csv = stand
    try:
        _, verdict, details = bt.emit_mirror()
    finally:
        bt.read_csv = orig
    return verdict == "MISMATCH" and any("schema mismatch" in d for d in details), verdict


def case_candidate_count():
    def mutate(path, rows):
        if path == str(REAL_DESKTOP / "RQ2/mutation_results.csv").replace(chr(92), "/"):
            row = next(r for r in rows if r["approach"] == "Qwen" and r["subject"] == "CPL2SPL")
            row["generated_candidates"] = "107"
        return rows
    orig, stand = patched_read_csv(mutate)
    bt.read_csv = stand
    try:
        _, verdict, details = bt.emit_mirror()
    finally:
        bt.read_csv = orig
    return verdict == "MISMATCH" and any("107" in d for d in details), verdict


def case_stale_aco_failure_count():
    """An old failing-source count must fail even when evaluable stays one."""
    def mutate(path, rows):
        if path == str(ROOT / "results/experiment_results/RQ3/mutant_level_exam.csv").replace(chr(92), "/"):
            row = next(r for r in rows if r["provider"] == "Yekta-ACO"
                       and r["mutant_id"] == "BibTeX2DocBook_Mutant1" and r["formula"] == "ochiai")
            row["failing_sources"] = "38"
        return rows
    orig, stand = patched_read_csv(mutate)
    bt.read_csv = stand
    try:
        _, verdict, details = bt.rq3_aco_canonical()
    finally:
        bt.read_csv = orig
    caught = verdict == "MISMATCH" and any("failing_sources" in d and "38" in d for d in details)
    return caught, f"verdict={verdict}; stale ACO count caught={caught}"


def case_blank_rebuilt_aco_flag():
    """The old missing-BibTeX exemption may no longer hide an empty kill flag."""
    def mutate(path, rows):
        target = str(bt.OUT / "experiment_results/RQ2/mutant_kill_matrix.csv").replace(chr(92), "/")
        if path == target:
            row = next(r for r in rows if r["subject"] == "BibTeX2DocBook")
            row["killed_Yekta-ACO"] = ""
        return rows
    orig, stand = patched_read_csv(mutate)
    bt.read_csv = stand
    try:
        _, verdict, details = bt.emit_mirror()
    finally:
        bt.read_csv = orig
    caught = verdict == "MISMATCH" and any("killed_Yekta-ACO" in d and "BibTeX2DocBook" in d for d in details)
    return caught, f"verdict={verdict}; empty canonical ACO flag caught={caught}"


def main() -> int:
    global REAL_DESKTOP
    # Keep injected reference reads separate from canonical calculation inputs.
    # Every case tampers only in memory; the private copy is removed afterward.
    reference = REAL_DESKTOP
    temporary = tempfile.TemporaryDirectory(prefix='paper-injection-reference-')
    shutil.copytree(reference, temporary.name, dirs_exist_ok=True)
    REAL_DESKTOP = Path(temporary.name)
    bt.REFERENCE_DIR = REAL_DESKTOP
    run_case("I1 top1 98.95->105.95 in reference", case_top1_tampered)
    run_case("I2 mutation killed +7 in reference", case_mutation_tampered)
    run_case("I3 validity 100.0->100.1 in reference", case_validity_100_1)
    run_case("I4 RQ4 anchor removed", case_rq4_missing_anchor)
    run_case("I5 missing killed-count column", case_missing_column)
    run_case("I6 candidate count 100->107", case_candidate_count)
    run_case("I7 stale ACO failing count 74->38 with evaluable unchanged", case_stale_aco_failure_count)
    run_case("I8 empty rebuilt ACO/BibTeX kill flag", case_blank_rebuilt_aco_flag)
    bad = [r for r in RESULTS if not r[1]]
    print(f"\nINJECTION TESTS: {'PASS' if not bad else 'FALSE-PASS'} "
          f"({len(RESULTS) - len(bad)}/{len(RESULTS)} tampering cases caught)")
    if temporary is not None:
        temporary.cleanup()
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
