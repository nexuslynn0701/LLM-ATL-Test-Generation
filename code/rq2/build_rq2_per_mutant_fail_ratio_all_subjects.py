#!/usr/bin/env python3
"""
Build per-mutant fail-ratio statistics for RQ2 — ALL 6 subjects.

For each test-generation method a, each eligible mutant m, and each source
model t, computes per-mutant:
    n_killed  — # original-executable sources whose mutant output differs
                from the original target (XMI oracle → KILLED)
    n_alive   — # sources whose mutant output matches (ALIVE)
    n_error   — # sources whose mutant run returned ERROR
    n_invalid — # sources whose mutant run returned INVALID_* / ORIGINAL_FAIL
    n_missing — # original-executable sources with no record for m

Primary fail-ratio (denominator = original-executable source count):
    fail_ratio      = n_killed / n_original_executable_sources
    fail_ratio_pct  = 100 * fail_ratio

Definition of n_original_executable_sources:
    distinct source_ids with `original_success == '1'` in
    source_mutant_outcomes.csv (mutant-testing-phase signal). Sources whose
    original ATL failed at mutant-testing time (original_success == '0') are
    excluded from both the denominator and the outcome counts.

    2026-10-15: the bundled source_mutant_outcomes.csv carries the Ant0030
    replay patch — the 100 Ant2Maven/gpt/astmo/0030 rows (original_success=0,
    ERROR in the frozen export) were restored to original_success=1 with the
    outcomes of results/rq2/supplementary/audits/rq23_ant0030_replay.csv (14 KILLED /
    72 ALIVE / 14 INVALID_RUNTIME). n is therefore 96 for GPT-ASTMO on
    Ant2Maven, matching the released RQ2 tables.

Methods (fixed order, 13): 12 LLM (GPT/Qwen/DeepSeek-Flash × SM/STM/ASTM/ASTMO)
    + Yekta-ACO. `workflow` is RQ4-only and excluded, matching the
    RQ2 suite-level pipeline.

Yekta-ACO pair data: the canonical replay matrix is available in-bundle for
    CPL2SPL and UML2ER (aco/source_mutant_outcomes_aco_replay_cpl_uml.csv,
    converted from results/rq1/supplementary/aco/estar_evidence). The BibTeX2DocBook
    canonical pair matrix (unified XMI oracle, 4,000 pairs, 32/40 mutants
    killed) did not survive the workspace migration; until
    aco/source_mutant_outcomes_aco_canonical_bibtex.csv is placed in
    results/rq2/supplementary/inputs/aco/, that one cell is reported as MISSING_PAIR_INPUT
    instead of being silently dropped. The legacy aggregate matrix
    (aco/source_mutant_outcomes_aco_legacy.csv, 100%/100%/100%) is kept only
    for the audit's canonical-vs-legacy comparison.

Outputs (per subject under
results/rq2/supplementary/per_mutant_fail_ratio/{Subject}/):
    rq2_{slug}_per_mutant_fail_ratio_long.csv
    rq2_{slug}_per_mutant_fail_ratio_summary.csv
Plus combined all-subject long CSV, summary CSV and audit at the top level.

This script only reads and recomputes from pair-level data. It does NOT re-run
ATL and does NOT modify the RQ2 pipeline.
"""
from __future__ import annotations

import csv
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'results/rq2/supplementary/inputs'
OUT_ROOT = ROOT / "results" / "rq2" / "supplementary" / "per_mutant_fail_ratio"

# ── Input files ──
MUTANT_MANIFEST = DATA / "canonical_mutants.csv"
LLM_OUTCOMES = DATA / "source_mutant_outcomes.csv"
ACO_CANONICAL_OUTCOMES = DATA / "aco" / "source_mutant_outcomes_aco_replay_cpl_uml.csv"
ACO_CANONICAL_BIBTEX = DATA / "aco" / "source_mutant_outcomes_aco_canonical_bibtex.csv"
ACO_LEGACY_OUTCOMES = DATA / "aco" / "source_mutant_outcomes_aco_legacy.csv"

# ── Subjects (fixed order) ──
SUBJECTS = ["Ant2Maven", "BibTeX2DocBook", "CPL2SPL", "Ecore2Maude", "Grafcet2PetriNet", "UML2ER"]

# ── Method order (fixed, 14) ──
METHODS = [
    ("gpt",            "sm",    "GPT-SM",             "GPT",            "SM"),
    ("gpt",            "stm",    "GPT-STM",           "GPT",            "STM"),
    ("gpt",            "astm",   "GPT-ASTM",          "GPT",            "ASTM"),
    ("gpt",            "astmo",  "GPT-ASTMO",         "GPT",            "ASTMO"),
    ("qwen",           "sm",    "Qwen-SM",            "Qwen",           "SM"),
    ("qwen",           "stm",   "Qwen-STM",           "Qwen",           "STM"),
    ("qwen",           "astm",  "Qwen-ASTM",          "Qwen",           "ASTM"),
    ("qwen",           "astmo", "Qwen-ASTMO",         "Qwen",           "ASTMO"),
    ("deepseek-flash", "sm",    "DeepSeek-Flash-SM",  "DeepSeek-Flash", "SM"),
    ("deepseek-flash", "stm",   "DeepSeek-Flash-STM", "DeepSeek-Flash", "STM"),
    ("deepseek-flash", "astm",  "DeepSeek-Flash-ASTM","DeepSeek-Flash", "ASTM"),
    ("deepseek-flash", "astmo", "DeepSeek-Flash-ASTMO","DeepSeek-Flash","ASTMO"),
    ("yekta_aco",      "aco",   "Yekta-ACO",          "Yekta-ACO",      "—"),
]

# Yekta-ACO (Troya toolchain) only supports these subjects.
ACO_SUPPORTED = {"BibTeX2DocBook", "CPL2SPL", "UML2ER"}

SLUG = {
    "Ant2Maven": "ant2maven",
    "BibTeX2DocBook": "bibtex",
    "CPL2SPL": "cpl2spl",
    "Ecore2Maude": "ecore2maude",
    "Grafcet2PetriNet": "grafcet2petrinet",
    "UML2ER": "uml2er",
}

# ── Outcome mapping (matches build_rq2_suite_level_mutation_score.py) ──
OUTCOME_BUCKET = {
    "KILLED": "killed",
    "ALIVE": "alive",
    "ERROR": "error",
    "INVALID_CONTAINMENT": "invalid",
    "INVALID_RUNTIME": "invalid",
    "ORIGINAL_FAIL": "invalid",
}

# ── Expected mutation scores (from the RQ2 suite-level table / compare_with_old
#    OLD_POOLED). Keyed (prov, cond) -> [Ant2Maven, BibTeX2DocBook, CPL2SPL,
#    Ecore2Maude, Grafcet2PetriNet, UML2ER]. None = "---" in the old table.
#    Note: for Yekta-ACO these are the LEGACY aggregate values (100%), which
#    disagree with the canonical replay for BibTeX2DocBook and UML2ER. ──
OLD_POOLED = {
    ("gpt", "sm"):     [33.0, 72.5, 82.0, 98.0, 73.3, 88.9],
    ("gpt", "stm"):    [30.0, 67.5, 76.0, 100.0, 70.0, 88.9],
    ("gpt", "astm"):   [43.0, 85.0, 90.0, 100.0, 73.3, 88.9],
    ("gpt", "astmo"):  [41.0, 80.0, 84.0, 100.0, 73.3, 88.9],
    ("qwen", "sm"):    [30.0, 65.0, None, 100.0, 73.3, 88.9],
    ("qwen", "stm"):   [38.0, 65.0, None, 100.0, 73.3, 88.9],
    ("qwen", "astm"):  [40.0, 80.0, None, 100.0, 73.3, 88.9],
    ("qwen", "astmo"): [27.0, 80.0, None, 100.0, 73.3, 88.9],
    ("deepseek-flash", "sm"):    [23.0, 62.5, 66.0, 100.0, 73.3, 88.9],
    ("deepseek-flash", "stm"):   [36.0, 62.5, 80.0, 100.0, 73.3, 88.9],
    ("deepseek-flash", "astm"):  [39.0, 80.0, 76.0, 98.0, 73.3, 88.9],
    ("deepseek-flash", "astmo"): [36.0, 80.0, 82.0, 98.0, 73.3, 88.9],
    ("yekta_aco", "aco"):        [None, 100.0, 100.0, None, None, 100.0],
}

# Expected mean per-mutant fail-ratio pct (== conditional pair-level kill rate).
# Reference values are only established for BibTeX2DocBook (from the RQ2 table).
EXPECTED_MEAN_FR_PCT = {
    "GPT-SM": 64.8, "GPT-STM": 65.0, "GPT-ASTM": 78.8, "GPT-ASTMO": 76.5,
    "Qwen-SM": 49.8, "Qwen-STM": 51.9, "Qwen-ASTM": 72.9, "Qwen-ASTMO": 70.0,
    "DeepSeek-Flash-SM": 62.5, "DeepSeek-Flash-STM": 62.5,
    "DeepSeek-Flash-ASTM": 74.8, "DeepSeek-Flash-ASTMO": 72.2,
}


def expected_ms(prov: str, cond: str, subject: str):
    """Return the expected mutation score, or None if the old table has '---'."""
    vals = OLD_POOLED[(prov, cond)]
    return vals[SUBJECTS.index(subject)]


def read_eligible_mutants(subject: str):
    """Return (eligible dict {mutant_id: meta}, excluded dict)."""
    eligible: dict[str, dict[str, str]] = {}
    excluded: dict[str, list[str]] = defaultdict(list)
    with open(MUTANT_MANIFEST) as f:
        for row in csv.DictReader(f):
            if row["subject"] != subject:
                continue
            mid = row["mutant_id"]
            lifecycle = row.get("lifecycle", "").strip()
            evaluated = row.get("evaluated_in_exported_matrix", "0")
            if lifecycle in ("stillborn", "invalid"):
                excluded["stillborn"].append(mid)
                continue
            if lifecycle == "equivalent":
                excluded["equivalent"].append(mid)
                continue
            if evaluated != "1":
                excluded["not_evaluated"].append(mid)
                continue
            eligible[mid] = {
                "target_rule": row.get("faulty_rule", "").strip(),
                "mutation_operator": row.get("mutation_operator", "").strip(),
            }
    return eligible, dict(excluded)


def read_llm_pairs(subject: str):
    """
    Read LLM pair outcomes. Only original-executable sources
    (original_success == '1') are counted, so ERROR/ORIGINAL_FAIL rows produced
    by sources whose original ATL failed at mutant-testing time are excluded.
    """
    method_lookup = {(m[0], m[1]): m[2] for m in METHODS if m[0] in ("gpt", "qwen", "deepseek-flash")}
    pairs: dict[str, dict[str, dict[str, int]]] = defaultdict(lambda: defaultdict(lambda: {"killed": 0, "alive": 0, "error": 0, "invalid": 0}))

    with open(LLM_OUTCOMES) as f:
        for row in csv.DictReader(f):
            if row["subject"] != subject:
                continue
            if row["original_success"] != "1":
                continue  # exclude non-original-executable sources
            key = (row["provider"], row["condition"].lower())
            mid_id = method_lookup.get(key)
            if mid_id is None:
                continue  # skips workflow (RQ4) and any unexpected condition
            mid = row["mutant_id"]
            bucket = OUTCOME_BUCKET.get(row["outcome"])
            if bucket is None:
                raise ValueError(f"Unknown outcome '{row['outcome']}' for {subject}/{mid_id}/{mid}")
            pairs[mid_id][mid][bucket] += 1
    return dict(pairs)


def read_aco_pairs(subject: str):
    """Read ACO pair outcomes from the canonical replay matrices."""
    if subject not in ACO_SUPPORTED:
        return {}
    path = ACO_CANONICAL_BIBTEX if subject == "BibTeX2DocBook" else ACO_CANONICAL_OUTCOMES
    if not path.is_file():
        return {}
    pairs: dict[str, dict[str, dict[str, int]]] = defaultdict(lambda: defaultdict(lambda: {"killed": 0, "alive": 0, "error": 0, "invalid": 0}))
    with open(path) as f:
        for row in csv.DictReader(f):
            if row["subject"] != subject:
                continue
            mid = row["mutant_id"]
            bucket = OUTCOME_BUCKET.get(row["outcome"])
            if bucket is None:
                raise ValueError(f"Unknown ACO outcome '{row['outcome']}' for {subject}/{mid}")
            pairs["Yekta-ACO"][mid][bucket] += 1
    return dict(pairs)


def compute_source_populations(subject: str, pairs: dict) -> dict[str, int]:
    """
    n_original_executable_sources per method_id.

    LLM: distinct source_ids with original_success == '1' (re-read from
    the outcomes file, since the pair aggregate already filters these).
    Yekta-ACO: distinct source_ids in the canonical replay matrix.
    """
    method_lookup = {(m[0], m[1]): m[2] for m in METHODS if m[0] in ("gpt", "qwen", "deepseek-flash")}
    sources: dict[str, set[str]] = defaultdict(set)

    with open(LLM_OUTCOMES) as f:
        for row in csv.DictReader(f):
            if row["subject"] != subject:
                continue
            if row["original_success"] != "1":
                continue
            key = (row["provider"], row["condition"].lower())
            mid_id = method_lookup.get(key)
            if mid_id is None:
                continue
            sources[mid_id].add(row["source_id"])

    if subject == "BibTeX2DocBook" and ACO_CANONICAL_BIBTEX.is_file():
        with open(ACO_CANONICAL_BIBTEX) as f:
            for row in csv.DictReader(f):
                if row["subject"] == subject:
                    sources["Yekta-ACO"].add(row["source_id"])
    elif subject in ACO_SUPPORTED:
        with open(ACO_CANONICAL_OUTCOMES) as f:
            for row in csv.DictReader(f):
                if row["subject"] == subject:
                    sources["Yekta-ACO"].add(row["source_id"])

    return {k: len(v) for k, v in sources.items()}


def build_long_rows(subject: str, eligible, pairs, populations) -> list[dict]:
    """One row per (method with data, mutant). Methods with n_src==0 are skipped."""
    rows: list[dict] = []
    for order, (prov, cond, method_id, generator, prompt) in enumerate(METHODS, start=1):
        if prov == "yekta_aco":
            order = 14  # stable published identifier; removed methods leave gaps
        n_src = populations.get(method_id, 0)
        if n_src == 0:
            continue  # NO_EXECUTABLE / N/A / missing pair input — no per-mutant data
        method_pairs = pairs.get(method_id, {})
        if prov == "yekta_aco" and subject == "BibTeX2DocBook":
            src_path = str(ACO_CANONICAL_BIBTEX)
        elif prov == "yekta_aco":
            src_path = str(ACO_CANONICAL_OUTCOMES)
        else:
            src_path = str(LLM_OUTCOMES)
        for mid, meta in eligible.items():
            d = method_pairs.get(mid, {"killed": 0, "alive": 0, "error": 0, "invalid": 0})
            n_killed = d["killed"]
            n_alive = d["alive"]
            n_error = d["error"]
            n_invalid = d["invalid"]
            n_missing = max(0, n_src - (n_killed + n_alive + n_error + n_invalid))
            fail_ratio = round(n_killed / n_src, 6)
            fail_ratio_pct = round(100.0 * n_killed / n_src, 4)
            killed_binary = 1 if n_killed > 0 else 0
            rows.append({
                "subject": subject,
                "method_order": order,
                "method_id": method_id,
                "generator": generator,
                "prompt_configuration": prompt,
                "mutant_id": mid,
                "mutation_operator": meta["mutation_operator"],
                "target_rule": meta["target_rule"],
                "eligible_mutant": 1,
                "n_original_executable_sources": n_src,
                "n_killed": n_killed,
                "n_alive": n_alive,
                "n_error": n_error,
                "n_invalid": n_invalid,
                "n_missing": n_missing,
                "fail_ratio": fail_ratio,
                "fail_ratio_pct": fail_ratio_pct,
                "killed_binary": killed_binary,
                "source_matrix_path": src_path,
            })
    return rows


def build_summary_rows(subject: str, eligible, pairs, populations, long_rows) -> list[dict]:
    """One row per (method, subject) — 13 rows, including NO_EXECUTABLE and N/A."""
    by_method: dict[str, list[dict]] = defaultdict(list)
    for r in long_rows:
        by_method[r["method_id"]].append(r)

    n_eligible = len(eligible)
    summary: list[dict] = []
    for order, (prov, cond, method_id, generator, prompt) in enumerate(METHODS, start=1):
        if prov == "yekta_aco":
            order = 14  # stable published identifier; removed methods leave gaps
        rows = by_method[method_id]
        n_src = populations.get(method_id, 0)

        # ACO on a non-supported subject → N/A
        if prov == "yekta_aco" and subject not in ACO_SUPPORTED:
            summary.append(_empty_summary(subject, order, method_id, n_eligible, "N/A"))
            continue

        # ACO BibTeX with the canonical pair matrix still missing → loud placeholder
        if prov == "yekta_aco" and subject == "BibTeX2DocBook" and not ACO_CANONICAL_BIBTEX.is_file():
            summary.append(_empty_summary(subject, order, method_id, n_eligible, "MISSING_PAIR_INPUT"))
            continue

        # NO_EXECUTABLE: evaluated but no original-executable source
        if n_src == 0:
            summary.append(_empty_summary(subject, order, method_id, n_eligible, "NO_EXECUTABLE", ms_pct=0.0))
            continue

        n_killed_mutants = sum(r["killed_binary"] for r in rows)
        ms_pct = round(100.0 * n_killed_mutants / n_eligible, 4) if n_eligible else ""

        fr_pcts = [r["fail_ratio_pct"] for r in rows]
        missing_pairs_count = sum(r["n_missing"] for r in rows)

        arr = np.array(fr_pcts, dtype=float)
        mean = round(float(np.mean(arr)), 4)

        # Status: the released failure_rate_summary.csv records the canonical
        # replay (which disagrees with the legacy 100% aggregate for BibTeX and
        # UML2ER) as OK_STRICT_CANONICAL rather than flagging a raw conflict.
        if prov == "yekta_aco":
            legacy = expected_ms(prov, cond, subject)  # 100.0 for Troya subjects
            if legacy is not None and abs(ms_pct - legacy) > 0.05:
                status = "OK_STRICT_CANONICAL"
            else:
                status = "OK"
        elif n_eligible != len(rows):
            status = "INCOMPLETE"
        elif missing_pairs_count > 0:
            status = "MISSING_PAIRS"
        else:
            status = "OK"

        summary.append({
            "subject": subject,
            "method_order": order,
            "method_id": method_id,
            "n_eligible_mutants": n_eligible,
            "n_original_executable_sources": n_src,
            "n_killed_mutants": n_killed_mutants,
            "mutation_score_pct": ms_pct,
            "mean_fail_ratio_pct": mean,
            "status": status,
        })
    return summary


def _empty_summary(subject, order, method_id, n_eligible, status, ms_pct=""):
    return {
        "subject": subject,
        "method_order": order,
        "method_id": method_id,
        "n_eligible_mutants": n_eligible,
        "n_original_executable_sources": "",
        "n_killed_mutants": "",
        "mutation_score_pct": ms_pct,
        "mean_fail_ratio_pct": "",
        "status": status,
    }


def run_sanity_checks(subject, eligible, populations, long_rows, summary_rows) -> list[str]:
    issues: list[str] = []
    by_method: dict[str, list[dict]] = defaultdict(list)
    for r in long_rows:
        by_method[r["method_id"]].append(r)

    n_eligible = len(eligible)

    # CHECK1: rows per method == n_eligible (for methods with data)
    for prov, cond, method_id, gen, prompt in METHODS:
        if populations.get(method_id, 0) == 0:
            continue  # no data expected
        n = len(by_method.get(method_id, []))
        if n != n_eligible:
            issues.append(f"CHECK1 FAIL: {subject}/{method_id} has {n} rows (expected {n_eligible})")

    # CHECK2: killed+alive+error+invalid+missing == n_src
    for r in long_rows:
        s = r["n_killed"] + r["n_alive"] + r["n_error"] + r["n_invalid"] + r["n_missing"]
        if s != r["n_original_executable_sources"]:
            issues.append(f"CHECK2 FAIL: {r['subject']}/{r['method_id']}/{r['mutant_id']} "
                          f"sum={s} != n_src={r['n_original_executable_sources']}")

    # CHECK3: fail_ratio_pct in [0,100]
    for r in long_rows:
        if not (0 <= r["fail_ratio_pct"] <= 100):
            issues.append(f"CHECK3 FAIL: {r['subject']}/{r['method_id']}/{r['mutant_id']} fr_pct={r['fail_ratio_pct']}")

    # CHECK4: MS = 100 * sum(killed_binary) / n_eligible
    for srow in summary_rows:
        if srow["status"] in ("N/A",):
            continue
        if srow["mutation_score_pct"] == "":
            continue
        kb = sum(r["killed_binary"] for r in by_method.get(srow["method_id"], []))
        recomputed = 100.0 * kb / n_eligible
        if abs(recomputed - srow["mutation_score_pct"]) > 0.001:
            issues.append(f"CHECK4 FAIL: {subject}/{srow['method_id']} MS={srow['mutation_score_pct']} recomputed={recomputed}")

    # CHECK5: MS vs expected table (skip N/A / None expectations; flag ACO conflict)
    for srow in summary_rows:
        method_id = srow["method_id"]
        prov_cond = next((m[0], m[1]) for m in METHODS if m[2] == method_id)
        exp = expected_ms(*prov_cond, subject)
        got = srow["mutation_score_pct"]
        if srow["status"] in ("NO_EXECUTABLE", "MISSING_PAIR_INPUT"):
            if srow["status"] == "NO_EXECUTABLE" and got != 0.0:
                issues.append(f"CHECK5 FAIL: {subject}/{method_id} NO_EXECUTABLE but MS={got}")
            continue
        if srow["status"] == "N/A" or got == "" or exp is None:
            continue
        if abs(got - exp) > 0.05:
            note = " (ACO canonical vs legacy)" if method_id == "Yekta-ACO" else ""
            issues.append(f"CHECK5 FAIL: {subject}/{method_id} MS={got} vs table {exp}{note}")

    # CHECK6: mean fail-ratio cross-check (only BibTeX2DocBook has reference values)
    if subject == "BibTeX2DocBook":
        for srow in summary_rows:
            method_id = srow["method_id"]
            exp = EXPECTED_MEAN_FR_PCT.get(method_id)
            if exp is None:
                continue
            got = srow["mean_fail_ratio_pct"]
            if got == "" or abs(got - exp) > 0.15:
                issues.append(f"CHECK6 FAIL: {subject}/{method_id} meanFR={got} vs expected {exp}")

    return issues


def read_aco_pair_summary(path: Path, subject: str, label: str, eligible) -> dict:
    """Compute killed_mutants / MS / pair counts from an ACO pair-level file."""
    eligible_ids = set(eligible)
    killed: dict[str, int] = defaultdict(int)
    alive = invalid = error = 0
    sources: set[str] = set()
    with open(path) as f:
        for row in csv.DictReader(f):
            if row["subject"] != subject:
                continue
            mid = row["mutant_id"]
            if mid not in eligible_ids:
                continue
            sources.add(row["source_id"])
            oc = row["outcome"]
            if oc == "KILLED":
                killed[mid] += 1
            elif oc == "ALIVE":
                alive += 1
            elif "INVALID" in oc:
                invalid += 1
            elif oc == "ERROR":
                error += 1
    n_killed_mutants = sum(1 for m in eligible_ids if killed[m] > 0)
    return {
        "label": label,
        "n_sources": len(sources),
        "n_killed_mutants": n_killed_mutants,
        "ms_pct": 100.0 * n_killed_mutants / len(eligible_ids) if eligible_ids else 0.0,
        "killed_pairs": sum(killed.values()),
        "alive_pairs": alive,
        "invalid_pairs": invalid,
        "error_pairs": error,
    }


def build_audit(all_subjects: list[dict]) -> str:
    """One combined audit covering all subjects."""
    lines: list[str] = []
    lines.append("# RQ2 Per-Mutant Fail-Ratio — Audit Report (All Subjects)")
    lines.append(f"\nGenerated: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"\nQuantile method: numpy {np.__version__}, `numpy.percentile(..., [25,50,75])`, "
                 f"`method='linear'` (linear interpolation).")

    lines.append("\n## 1. Denominator & Outcome Definitions\n")
    lines.append("- `n_original_executable_sources` = distinct source_ids with `original_success == '1'` "
                 "in `source_mutant_outcomes.csv` (the mutant-testing-phase signal).")
    lines.append("- Sources whose original ATL failed at mutant-testing time (`original_success == '0'`) "
                 "are excluded from BOTH the denominator and the outcome counts.")
    lines.append("- 2026-10-15: the bundled outcomes file carries the Ant0030 replay patch — the 100 "
                 "Ant2Maven/gpt/astmo/0030 rows were restored to `original_success == '1'` with the "
                 "outcomes of `results/rq2/supplementary/audits/rq23_ant0030_replay.csv` (14 KILLED / 72 ALIVE / "
                 "14 INVALID_RUNTIME), so GPT-ASTMO on Ant2Maven has n = 96, matching the released tables.")
    lines.append("- `fail_ratio = n_killed / n_original_executable_sources`; ERROR and INVALID count as "
                 "`not killed` and stay in the denominator.")
    lines.append("- `KILLED→killed, ALIVE→alive, ERROR→error, INVALID_CONTAINMENT/INVALID_RUNTIME/ORIGINAL_FAIL→invalid`.")
    lines.append("- `workflow` condition is RQ4-only and excluded, matching the RQ2 pipeline.")

    # Per-subject sections
    for d in all_subjects:
        subject = d["subject"]
        eligible = d["eligible"]
        excluded = d["excluded"]
        populations = d["populations"]
        summary = d["summary"]
        long_rows = d["long_rows"]
        issues = d["issues"]

        lines.append(f"\n## 2. Subject: {subject}\n")
        lines.append(f"- Eligible mutants: **{len(eligible)}** "
                     f"(excluded stillborn/invalid={len(excluded.get('stillborn',[]))}, "
                     f"equivalent={len(excluded.get('equivalent',[]))}, "
                     f"not_evaluated={len(excluded.get('not_evaluated',[]))})")
        lines.append(f"- Long-CSV rows: {len(long_rows)} "
                     f"(methods with data × {len(eligible)} mutants)")

        lines.append(f"\n### {subject} — Source suite size\n")
        lines.append(f"| Method | n_original_executable_sources |")
        lines.append(f"|---|---:|")
        for prov, cond, method_id, gen, prompt in METHODS:
            n = populations.get(method_id)
            label = n if n is not None else "—"
            lines.append(f"| {method_id} | {label} |")

        lines.append(f"\n### {subject} — Mutation-score & fail-ratio cross-check\n")
        lines.append(f"| Method | n_src | Killed | MS% | Exp MS% | Match | meanFR% | Exp FR% | FR match | status |")
        lines.append(f"|---|---:|---:|---:|---:|---|---:|---:|---|")
        for srow in summary:
            mid = srow["method_id"]
            prov_cond = next((m[0], m[1]) for m in METHODS if m[2] == mid)
            exp_ms = expected_ms(*prov_cond, subject)
            got_ms = srow["mutation_score_pct"]
            n_src = srow["n_original_executable_sources"]
            km = srow["n_killed_mutants"]
            # MS match
            if srow["status"] == "N/A":
                ms_match = "—"
            elif srow["status"] == "NO_EXECUTABLE":
                ms_match = "✅" if got_ms == 0.0 else "❌"
            elif exp_ms is None or got_ms == "":
                ms_match = "—"
            else:
                ms_match = "✅" if abs(got_ms - exp_ms) <= 0.05 else "❌"
            # FR cross-check only for BibTeX2DocBook
            exp_fr = EXPECTED_MEAN_FR_PCT.get(mid) if subject == "BibTeX2DocBook" else None
            got_fr = srow["mean_fail_ratio_pct"]
            if exp_fr is None:
                fr_match = "—"
            elif got_fr == "":
                fr_match = "—"
            else:
                fr_match = "✅" if abs(got_fr - exp_fr) <= 0.15 else "❌"
            lines.append(f"| {mid} | {n_src} | {km} | {got_ms} | {exp_ms if exp_ms is not None else '—'} | "
                         f"{ms_match} | {got_fr} | {exp_fr if exp_fr is not None else '—'} | {fr_match} | {srow['status']} |")

        if issues:
            lines.append(f"\n### {subject} — sanity-check issues\n")
            for i in issues:
                lines.append(f"- ❌ {i}")
        else:
            lines.append(f"\n### {subject} — sanity-check issues\n\n✅ none (ACO conflict flagged separately).")

    # ACO provenance section
    lines.append("\n## 3. Yekta-ACO Pair-Data Provenance\n")
    lines.append("ACO is evaluated on the three Troya subjects using the **canonical replay** matrix. "
                 "This matrix disagrees with the legacy aggregate (which feeds the current RQ2 table's "
                 "Yekta-ACO = 100%).\n")
    lines.append(f"| Subject | canonical MS% | legacy MS% | agree? |")
    lines.append(f"|---|---:|---:|---|")
    for subject in sorted(ACO_SUPPORTED):
        d = next(x for x in all_subjects if x["subject"] == subject)
        canon_path = ACO_CANONICAL_BIBTEX if subject == "BibTeX2DocBook" else ACO_CANONICAL_OUTCOMES
        if not canon_path.is_file():
            lines.append(f"| {subject} | MISSING_PAIR_INPUT | "
                         f"{read_aco_pair_summary(ACO_LEGACY_OUTCOMES, subject, 'legacy', d['eligible'])['ms_pct']:.1f} | ❌ |")
            continue
        canon = read_aco_pair_summary(canon_path, subject, "canonical", d["eligible"])
        legacy = read_aco_pair_summary(ACO_LEGACY_OUTCOMES, subject, "legacy", d["eligible"])
        agree = "✅" if abs(canon["ms_pct"] - legacy["ms_pct"]) <= 0.05 else "❌"
        lines.append(f"| {subject} | {canon['ms_pct']:.1f} ({canon['n_killed_mutants']}/{len(d['eligible'])}) | "
                     f"{legacy['ms_pct']:.1f} ({legacy['n_killed_mutants']}/{len(d['eligible'])}) | {agree} |")
    lines.append(f"\n- `{ACO_CANONICAL_OUTCOMES.name}` — canonical replay for CPL2SPL/UML2ER (converted from "
                 "results/rq1/supplementary/aco/estar_evidence).")
    lines.append(f"- `{ACO_CANONICAL_BIBTEX.name}` — canonical BibTeX2DocBook pair matrix, **pending** "
                 "re-export from the original workspace; the subject is reported as MISSING_PAIR_INPUT.")
    lines.append(f"- `{ACO_LEGACY_OUTCOMES.name}` — legacy supplementary (deprecated for source-level evidence).")
    lines.append("\n⚠️ The long/summary CSVs ship the **canonical** matrix. If a figure must match the "
                 "legacy aggregate instead, use the legacy matrix for Yekta-ACO on BibTeX2DocBook and "
                 "UML2ER. CPL2SPL agrees at 100% either way.")

    # Data-quality notes
    lines.append("\n## 4. Data-Quality Notes (original_success == '0' exclusions)\n")
    lines.append("The following source models have `original_success == '0'` "
                 "in `source_mutant_outcomes.csv` — i.e. the original ATL re-execution failed during mutant "
                 "testing, so all their mutant outcomes are ERROR/ORIGINAL_FAIL and they are excluded from the "
                 "fail-ratio denominator (Ant2Maven/0030 was restored by the 2026-10-15 replay patch, see §1):")
    lines.append("\n| Subject | Provider | Condition | Source | Outcome | n_rows |")
    lines.append("|---|---|---|---|---|---:|")
    notes = [("Grafcet2PetriNet", "gpt", "sm", "0023", "ORIGINAL_FAIL", 30),
             ("Grafcet2PetriNet", "gpt", "stm", "0004", "ORIGINAL_FAIL", 30),
             ("Grafcet2PetriNet", "gpt", "stm", "0051", "ORIGINAL_FAIL", 30),
             ("Grafcet2PetriNet", "gpt", "stm", "0075", "ORIGINAL_FAIL", 30),
             ("Grafcet2PetriNet", "gpt", "astm", "0062", "ORIGINAL_FAIL", 30)]
    for subj, prov, cond, sid, oc, n in notes:
        lines.append(f"| {subj} | {prov} | {cond} | {sid} | {oc} | {n} |")

    lines.append("\n## 5. NO_EXECUTABLE / N/A / MISSING cells\n")
    lines.append("| Subject | Cell | Status |")
    lines.append("|---|---|---|")
    for subject in SUBJECTS:
        for prov, cond, mid, gen, prompt in METHODS:
            if prov == "yekta_aco" and subject not in ACO_SUPPORTED:
                lines.append(f"| {subject} | {mid} | N/A (tool-incompatible) |")
            elif prov == "yekta_aco" and subject == "BibTeX2DocBook" and not ACO_CANONICAL_BIBTEX.is_file():
                lines.append(f"| {subject} | {mid} | MISSING_PAIR_INPUT (canonical BibTeX matrix pending) |")
            elif prov == "qwen" and subject == "CPL2SPL":
                lines.append(f"| {subject} | {mid} | NO_EXECUTABLE |")
    lines.append("")

    return "\n".join(lines)


LONG_FIELDS = [
    "subject", "method_order", "method_id", "generator", "prompt_configuration",
    "mutant_id", "mutation_operator", "target_rule", "eligible_mutant",
    "n_original_executable_sources", "n_killed", "n_alive", "n_error", "n_invalid",
    "n_missing", "fail_ratio", "fail_ratio_pct", "killed_binary", "source_matrix_path",
]

SUMMARY_FIELDS = [
    "subject", "method_order", "method_id", "n_eligible_mutants",
    "n_original_executable_sources", "n_killed_mutants", "mutation_score_pct",
    "mean_fail_ratio_pct", "status",
]


def write_csv(path: Path, fields: list[str], rows: list[dict]):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def main() -> int:
    print("=== RQ2 Per-Mutant Fail-Ratio Builder — ALL SUBJECTS ===\n")
    if not ACO_CANONICAL_BIBTEX.is_file():
        print(f"[warn] {ACO_CANONICAL_BIBTEX.name} not found — Yekta-ACO x BibTeX2DocBook "
              "will be reported as MISSING_PAIR_INPUT (see results/rq2/supplementary/inputs/aco/README.md).\n")
    all_long: list[dict] = []
    all_summary: list[dict] = []
    all_subjects_data: list[dict] = []
    total_issues = 0

    for subject in SUBJECTS:
        print(f"\n--- {subject} ---")
        eligible, excluded = read_eligible_mutants(subject)
        pairs = read_llm_pairs(subject)
        aco = read_aco_pairs(subject)
        if aco:
            pairs.update(aco)
        populations = compute_source_populations(subject, pairs)

        long_rows = build_long_rows(subject, eligible, pairs, populations)
        summary_rows = build_summary_rows(subject, eligible, pairs, populations, long_rows)
        issues = run_sanity_checks(subject, eligible, populations, long_rows, summary_rows)
        total_issues += len(issues)

        n_data_methods = len({r["method_id"] for r in long_rows})
        print(f"  eligible mutants: {len(eligible)}")
        print(f"  methods with data: {n_data_methods}")
        print(f"  long rows: {len(long_rows)}  summary rows: {len(summary_rows)}  issues: {len(issues)}")
        for s in summary_rows:
            flag = "" if s["status"] == "OK" else f"  [{s['status']}]"
            print(f"    {s['method_id']:22s} n_src={s['n_original_executable_sources']!s:>5s} "
                  f"MS={s['mutation_score_pct']!s:>6s} meanFR={s['mean_fail_ratio_pct']!s:>7s}{flag}")

        # Per-subject outputs
        subj_dir = OUT_ROOT / subject
        subj_dir.mkdir(parents=True, exist_ok=True)
        slug = SLUG[subject]
        write_csv(subj_dir / f"rq2_{slug}_per_mutant_fail_ratio_long.csv", LONG_FIELDS, long_rows)
        write_csv(subj_dir / f"rq2_{slug}_per_mutant_fail_ratio_summary.csv", SUMMARY_FIELDS, summary_rows)

        all_long.extend(long_rows)
        all_summary.extend(summary_rows)
        all_subjects_data.append({
            "subject": subject, "eligible": eligible, "excluded": excluded,
            "populations": populations, "long_rows": long_rows,
            "summary": summary_rows, "issues": issues,
        })

    # Combined outputs
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    write_csv(OUT_ROOT / "rq2_per_mutant_fail_ratio_long_all_subjects.csv", LONG_FIELDS, all_long)
    write_csv(OUT_ROOT / "rq2_per_mutant_fail_ratio_summary_all_subjects.csv", SUMMARY_FIELDS, all_summary)

    audit = build_audit(all_subjects_data)
    audit_path = OUT_ROOT / "rq2_per_mutant_fail_ratio_audit.md"
    audit_path.write_text(audit, encoding="utf-8")

    print(f"\n=== Combined outputs ===")
    print(f"  long: {len(all_long)} rows")
    print(f"  summary: {len(all_summary)} rows")
    print(f"  audit: {audit_path}")
    print(f"  total sanity issues: {total_issues}")

    return 0 if total_issues == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
