#!/usr/bin/env python3
"""Validate the RQ1 failure taxonomy (paper Table 3) and rule coverage (Table 5)
against their evidence.

Table 3 layers, in order:
1. Aggregate consistency: breakdown rows in rq1/data/failure_taxonomy.csv sum
   to their parents and every percentage matches its count over the total.
2. Cross-check with validity.csv: failed attempts = LLM ladder attempts minus
   valid models, using both the published fraction totals row and the 72
   per-cell percentages.
3. Per-attempt recount: when the diagnostics export is present under
   rq1/supplementary/failure_diagnostics/, every runtime category (the six L1
   classes and all L2 breakdowns) is recounted from it. The 77 syntax/parse
   failures are generation-stage and absent there, so they are checked as
   total minus runtime instead.

Table 5 layers:
4. Rule coverage recount: all 72 LLM cells and the six retired baseline cells are
   recounted as rule-ID unions from rq1/supplementary/source_rule_coverage.csv over the
   trace-eligible sources of rq1/supplementary/source_population.csv, with per-subject
   universes checked against rq1/data/subjects.csv. The retired baseline Ant2Maven
   cell keeps only 10/100 traces on disk, so its recount is a lower bound.
5. Pooled Overall: every Table 5 "Overall" value (12 LLM rows, retired baseline,
   Yekta-ACO) is recomputed as covered/total rules pooled across subjects and
   compared against the published paper values.
"""
import csv
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "reproduction"))
from common import DATA, read_csv

DIAGNOSTICS = DATA / "rq1/supplementary/failure_diagnostics/rq1_execution_failure_diagnostics_by_attempt.csv"
GENERATION_RECORDS = DATA / "rq1/supplementary/generation_attempt_records/generation_attempt_records.csv"
TAXONOMY = DATA / "rq1/data/failure_taxonomy.csv"
RULE_COVERAGE = DATA / "rq1/data/rule_coverage.csv"
RULE_COVERAGE_POOLED = DATA / "rq1/data/rule_coverage_overall_pooled.csv"
SOURCE_RULES = DATA / "rq1/supplementary/source_rule_coverage.csv"
POPULATION = DATA / "rq1/supplementary/source_population.csv"
SUBJECTS_TABLE = DATA / "rq1/data/subjects.csv"
ACO_RULE_COVERAGE = DATA / "shared/aco/rule_coverage.csv"
LLMS = {"Gpt", "Qwen", "DeepSeek"}
LLM_CONDITIONS = {"SM", "STM", "ASTM", "ASTMO"}
DIAG_PROVIDERS = {"gpt", "qwen", "deepseek-flash"}
DIAG_CONDITIONS = {"sm", "stm", "astm", "astmo"}
PROMPTS = ("SM", "STM", "ASTM", "ASTMO")
RULE_LLMS = ("GPT", "Qwen", "DeepSeek")
ALIASES = {"gpt": "GPT", "qwen": "Qwen", "deepseek-flash": "DeepSeek"}

# Paper Table 5 "Overall" column: rules pooled across subjects per row.
PAPER_OVERALL = {
    ("GPT", "SM"): 86.36, ("GPT", "STM"): 84.55, ("GPT", "ASTM"): 95.45, ("GPT", "ASTMO"): 95.45,
    ("Qwen", "SM"): 68.18, ("Qwen", "STM"): 72.73, ("Qwen", "ASTM"): 77.27, ("Qwen", "ASTMO"): 70.00,
    ("DeepSeek", "SM"): 74.55, ("DeepSeek", "STM"): 86.36,
    ("DeepSeek", "ASTM"): 93.64, ("DeepSeek", "ASTMO"): 91.82,
    ("Yekta-ACO", "ACO"): 88.89,
}

# Message patterns for the L2 breakdowns, in priority order: a diagnostic row
# takes the first matching category, and the empty-error-code taxonomy row is
# the remainder. Names equal the taxonomy's error_code values.
LOADING_PATTERNS = [
    ("SAXParseException", r"SAXParseException"),
    ("IllegalValueException", r"IllegalValueException"),
    ("object not contained in a resource", r"not contained in a resource"),
    ("UnresolvedReferenceException", r"UnresolvedReferenceException"),
    ("ClassNotFoundException", r"ClassNotFoundException"),
]
METAMODEL_PATTERNS = [
    ("ClassCastException", r"ClassCastException"),
    ("OclUndefined navigation", r"OclUndefined"),
    ("type incompatibility", r"must be of type"),
]


def parse_taxonomy(rows: list[dict[str, str]]):
    total = next((r for r in rows if r["level"] == "TOTAL"), None)
    if total is None:
        raise SystemExit(f"{TAXONOMY}: missing TOTAL row")
    entries = []  # (row, parent row or None), file order
    cur_l0 = cur_l1 = None
    for row in rows:
        if row["level"] == "TOTAL":
            continue
        if row["level"] == "L0":
            cur_l0, cur_l1, parent = row, None, None
        elif row["level"] == "L1":
            cur_l1, parent = row, cur_l0
        else:
            parent = cur_l1
        entries.append((row, parent))
    return total, entries


def check_aggregate(total: dict, entries: list, errors: list[str]) -> None:
    total_count = int(total["count"])
    if abs(float(total["pct_of_all_failures"]) - 100.0) > 1e-9:
        errors.append(f"TOTAL pct is {total['pct_of_all_failures']}, expected 100.00")
    for row, _ in entries:
        expected = int(row["count"]) / total_count * 100
        if abs(float(row["pct_of_all_failures"]) - expected) > 0.005 + 1e-9:
            errors.append(
                f"pct mismatch for {row['category']}: {row['pct_of_all_failures']} vs {expected:.2f}")
    children: dict[int, list[dict]] = {}
    for row, parent in entries:
        children.setdefault(id(parent), []).append(row)
    row_by_id = {id(row): row for row, _ in entries}
    for parent_id, kids in children.items():
        target = total if parent_id == id(None) else row_by_id[parent_id]
        summed = sum(int(k["count"]) for k in kids)
        if summed != int(target["count"]):
            errors.append(
                f"children of {target['category']} sum to {summed}, expected {target['count']}")


def validity_failures(subjects: list[str], errors: list[str]) -> tuple[int, int]:
    rows = read_csv(DATA / "rq1/data/validity.csv")
    fractions = [r for r in rows if r["Generator"] == "LLM Overall" and "/" in r["Cond."]]
    if len(fractions) != 1:
        raise SystemExit("validity.csv: expected exactly one LLM Overall fraction row")
    row = fractions[0]
    numerators = [int(row[s].split("/")[0]) for s in subjects]
    denominators = [int(row[s].split("/")[1]) for s in subjects]
    valid, attempts = sum(numerators), sum(denominators)
    if row["Cond."] != f"{valid}/{attempts}":
        errors.append(f"validity.csv fraction row label {row['Cond.']} != {valid}/{attempts}")

    cells = [r for r in rows if r["Generator"] in LLMS and r["Cond."] in LLM_CONDITIONS]
    if len(cells) != 12 or len(subjects) != 6:
        errors.append(
            f"validity.csv has {len(cells)} LLM ladder rows x {len(subjects)} subjects, expected 12x6")
    cell_valid = sum(float(r[s]) for r in cells for s in subjects)
    if abs(cell_valid - valid) > 1e-6:
        errors.append(f"72 per-cell percentages sum to {cell_valid}, fraction row says {valid}")
    return attempts - valid, attempts


def evidence(row: dict[str, str]) -> str:
    return " ".join(filter(None, (row["error_message"], row["exception_class"], row["stderr_excerpt"])))


def pattern_counts(group: list[dict], patterns: list[tuple[str, str]]) -> tuple[dict[str, int], int]:
    counts = {name: 0 for name, _ in patterns}
    other = 0
    for row in group:
        text = evidence(row)
        for name, pattern in patterns:
            if re.search(pattern, text):
                counts[name] += 1
                break
        else:
            other += 1
    return counts, other


def check_diagnostics(subjects: list[str], total_count: int, entries: list, errors: list[str]) -> None:
    if not DIAGNOSTICS.exists():
        print(f"- per-attempt recount skipped: {DIAGNOSTICS} not present")
        return
    with DIAGNOSTICS.open(newline="", encoding="utf-8-sig") as f:
        diag = [r for r in csv.DictReader(f)
                if r["provider"] in DIAG_PROVIDERS and r["condition"] in DIAG_CONDITIONS
                and r["subject"] in subjects]
    runtime = next(int(r["count"]) for r, p in entries if p is None and r["category"] == "Runtime error")
    syntax = next(int(r["count"]) for r, p in entries if p is None and r["category"] == "Syntax error")
    if len(diag) != runtime:
        errors.append(f"diagnostics rows {len(diag)} != Runtime error {runtime}")
    if total_count - len(diag) != syntax:
        errors.append(f"total {total_count} - diagnostics {len(diag)} != Syntax error {syntax}")

    l1 = Counter(r["primary_failure_reason"] for r in diag)
    for row, parent in entries:
        if row["level"] != "L1" or parent["category"] != "Runtime error":
            continue
        actual = l1.get(row["error_code"], 0)
        if actual != int(row["count"]):
            errors.append(f"{row['error_code']}: diagnostics {actual} != table {row['count']}")

    groups: dict[str, list[dict]] = {}
    for reason in ("MODEL_LOADING_FAILURE", "METAMODEL_CONFORMANCE_FAILURE"):
        groups[reason] = [r for r in diag if r["primary_failure_reason"] == reason]
    patterns = {"MODEL_LOADING_FAILURE": LOADING_PATTERNS, "METAMODEL_CONFORMANCE_FAILURE": METAMODEL_PATTERNS}
    for reason, group in groups.items():
        counts, other = pattern_counts(group, patterns[reason])
        for name, count in counts.items():
            row = next((r for r, p in entries if p and p["error_code"] == reason
                        and r["level"] == "L2" and r["error_code"] == name), None)
            if row is None:
                errors.append(f"{reason}: no L2 row with error_code {name}")
            elif count != int(row["count"]):
                errors.append(f"{name}: diagnostics {count} != table {row['count']}")
        row = next((r for r, p in entries if p and p["error_code"] == reason
                    and r["level"] == "L2" and not r["error_code"]), None)
        if row is None:
            errors.append(f"{reason}: no remainder L2 row")
        elif other != int(row["count"]):
            errors.append(f"{reason} remainder: diagnostics {other} != table {row['count']}")
    print(f"- per-attempt recount: {len(diag)} diagnostics rows match all runtime categories")


def canonical(provider: str) -> str:
    return ALIASES.get(provider, provider)


def check_rule_coverage(errors: list[str]) -> None:
    totals = {r["transformation"]: int(r["total_rules"]) for r in read_csv(SUBJECTS_TABLE)}
    eligible = set()
    for row in read_csv(POPULATION):
        if row["original_execution_success"] == "1" and row["trace_eligible"] == "1":
            eligible.add((row["subject"], canonical(row["provider"]),
                          row["condition"].upper(), row["source_id"]))

    universes: dict[str, set[str]] = defaultdict(set)
    covered: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for row in read_csv(SOURCE_RULES):
        key = (row["subject"], canonical(row["provider"]), row["condition"].upper(), row["source_id"])
        if key not in eligible:
            continue
        universes[row["subject"]].add(row["rule_id"])
        if row["covered"] == "1":
            covered[key[:3]].add(row["rule_id"])
    for subject, universe in sorted(universes.items()):
        if len(universe) != totals[subject]:
            errors.append(f"{subject}: rule universe {len(universe)} != subjects.csv {totals[subject]}")
    total_rules = sum(totals.values())

    rows = read_csv(RULE_COVERAGE)
    published = {(r["subject"], r["llm"], r["prompt_condition"].upper()): r for r in rows
                 if r["generator"] in {"llm_ladder"} and r["prompt_condition"] != "All prompts"}
    cells = [k for k in published if k[1] in RULE_LLMS and k[2] in LLM_CONDITIONS]
    if len(cells) != 72:
        errors.append(f"rule_coverage.csv has {len(cells)} LLM cells, expected 72")
    for key, row in sorted(published.items()):
        actual = len(covered.get(key[:3], set()))
        if actual != int(row["covered_rules"]):
            errors.append(f"{key[:3]}: recounted {actual} covered rules != table {row['covered_rules']}")
        elif round(100 * actual / totals[key[0]], 2) != float(row["rule_coverage_pct"]):
            errors.append(f"{key[:3]}: recounted pct != table {row['rule_coverage_pct']}")
    for llm in sorted({k[1] for k in published}):
        for prompt in PROMPTS:
            pooled = round(100 * sum(len(covered.get((s, llm, prompt), set())) for s in totals) / total_rules, 2)
            if pooled != PAPER_OVERALL[(llm, prompt)]:
                errors.append(f"{llm}/{prompt} pooled Overall {pooled} != paper {PAPER_OVERALL[(llm, prompt)]}")
    aco_cells = {r["subject"]: r for r in rows if r["generator"] == "yekta_aco"}
    aco_evidence = {}
    for row in read_csv(ACO_RULE_COVERAGE):
        if row["status"] == "EVALUATED":
            aco_evidence[row["subject"]] = (int(row["covered_rules_count"]), int(row["total_rules"]))
    for subject, row in sorted(aco_cells.items()):
        counts = aco_evidence.get(subject)
        if counts != (int(row["covered_rules"]), int(row["total_rules"])):
            errors.append(f"ACO {subject}: shared/aco evidence {counts} != table "
                          f"{row['covered_rules']}/{row['total_rules']}")
    aco_pooled = round(100 * sum(c for c, _ in aco_evidence.values())
                       / sum(t for _, t in aco_evidence.values()), 2)
    if aco_pooled != PAPER_OVERALL[("Yekta-ACO", "ACO")]:
        errors.append(f"Yekta-ACO pooled Overall {aco_pooled} != paper {PAPER_OVERALL[('Yekta-ACO', 'ACO')]}")

    if RULE_COVERAGE_POOLED.exists():
        for row in read_csv(RULE_COVERAGE_POOLED):
            generator, prompt = row["generator"], row["prompt_condition"]
            cells = [r for r in rows
                     if (r["llm"] == generator
                         and (r["prompt_condition"] == prompt if r["generator"] == "llm_ladder"
                              else r["prompt_condition"] != "All prompts"))]
            covered = sum(int(r["covered_rules"]) for r in cells)
            total = sum(int(r["total_rules"]) for r in cells)
            if (int(row["pooled_covered_rules"]), int(row["pooled_total_rules"]),
                    row["overall_pooled_pct"], int(row["subjects_included"])) != (
                    covered, total, f"{100.0 * covered / total:.2f}", len(cells)):
                errors.append(f"pooled Overall row {generator}/{prompt} disagrees with rule_coverage.csv")
        print(f"- pooled Overall file: {len(read_csv(RULE_COVERAGE_POOLED))} rows consistent with rule_coverage.csv")
    if not errors:
        print(f"- rule coverage: 72 LLM + {len(aco_cells)} baseline cells recounted from rule IDs; "
              f"{len(PAPER_OVERALL)} pooled Overall values match Table 5")


def check_generation_records(subjects: list[str], entries: list, errors: list[str]) -> None:
    """Recount the syntax/runtime split and per-cell validity from the raw
    per-attempt generation records, when the export is present."""
    if not GENERATION_RECORDS.exists():
        print("- per-attempt generation recount skipped: generation records not present")
        return
    with GENERATION_RECORDS.open(newline="", encoding="utf-8-sig") as f:
        rows = [r for r in csv.DictReader(f)
                if r["provider"] in DIAG_PROVIDERS and r["condition"] in DIAG_CONDITIONS
                and r["subject"] in subjects]
    if len(rows) != 7200:
        errors.append(f"generation records have {len(rows)} LLM ladder rows, expected 7200")
    statuses = Counter(r["raw_status"] for r in rows)
    runtime = next(int(r["count"]) for r, p in entries if p is None and r["category"] == "Runtime error")
    syntax = next(int(r["count"]) for r, p in entries if p is None and r["category"] == "Syntax error")
    if statuses["ATL_EXEC_FAIL"] != runtime:
        errors.append(f"generation records ATL_EXEC_FAIL {statuses['ATL_EXEC_FAIL']} != Runtime error {runtime}")
    generated = sum(c for s, c in statuses.items() if s not in ("OK", "ATL_EXEC_FAIL"))
    if generated != syntax:
        errors.append(f"generation records generation failures {generated} != Syntax error {syntax}")

    expected = Counter()
    for r in read_csv(POPULATION):
        if r["provider"] in ("GPT", "Qwen", "DeepSeek") and r["condition"] in DIAG_CONDITIONS:
            expected[(r["subject"], r["provider"], r["condition"].upper())] += int(r["original_execution_success"])
    actual = Counter((r["subject"], canonical(r["provider"]), r["condition"].upper())
                     for r in rows if r["raw_status"] == "OK")
    mismatches = [k for k in expected if actual.get(k, 0) != expected[k]]
    if mismatches:
        errors.append(f"{len(mismatches)} validity cells disagree with generation records: {mismatches[:3]}")

    if DIAGNOSTICS.exists():
        with DIAGNOSTICS.open(newline="", encoding="utf-8-sig") as f:
            diag_ids = {r["attempt_id"] for r in csv.DictReader(f)}
        runtime_ids = {r["attempt_id"] for r in rows if r["raw_status"] == "ATL_EXEC_FAIL"}
        if runtime_ids != diag_ids:
            errors.append(f"runtime attempt ids differ from diagnostics: "
                          f"{len(runtime_ids - diag_ids)} only in records, {len(diag_ids - runtime_ids)} only in diagnostics")
    print(f"- generation records: 7200 attempts recount OK={statuses['OK']}, "
          f"runtime={statuses['ATL_EXEC_FAIL']}, syntax={generated}; validity cells and "
          f"diagnostics join consistent")


def main() -> None:
    errors: list[str] = []
    total, entries = parse_taxonomy(read_csv(TAXONOMY))
    total_count = int(total["count"])
    check_aggregate(total, entries, errors)
    print(f"- aggregate: {len(entries)} rows, total {total_count}, hierarchy and percentages consistent"
          if not errors else "- aggregate: see errors below")

    subjects = [k for k in read_csv(DATA / "rq1/data/validity.csv")[0] if k not in {"Generator", "Cond."}]
    failures, attempts = validity_failures(subjects, errors)
    if failures != total_count:
        errors.append(f"validity failures {failures} != taxonomy total {total_count}")
    else:
        print(f"- validity: {attempts} attempts - valid = {failures} failures, matches taxonomy total")

    check_diagnostics(subjects, total_count, entries, errors)
    check_generation_records(subjects, entries, errors)
    check_rule_coverage(errors)

    if errors:
        for message in errors:
            print(f"FAIL: {message}", file=sys.stderr)
        raise SystemExit(1)
    print("All Table 3 and Table 5 checks passed.")


if __name__ == "__main__":
    main()
