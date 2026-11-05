"""Rebuild All prompts coverage from source-level rule IDs, without LLM calls."""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "reproduction"))
from common import DATA, read_csv, write_csv

PROMPTS = ("SM", "STM", "ASTM", "ASTMO")
LLMS = ("GPT", "Qwen", "DeepSeek")
ALIASES = {"gpt": "GPT", "qwen": "Qwen", "deepseek-flash": "DeepSeek"}
COUNTS = ("n_attempts", "n_source_generated", "n_original_executable",
          "n_trace_eligible", "n_original_executable_without_trace")


def union_coverage(rule_sets: list[set[str]], universe: set[str]) -> tuple[set[str], float]:
    covered = set().union(*rule_sets)
    if not universe or not covered <= universe:
        raise ValueError("Empty rule universe or covered rules outside the universe")
    return covered, 100.0 * len(covered) / len(universe)


def pooled_overall_rows(base: list[dict]) -> list[dict]:
    """Table 5 "Overall" column: covered/total rules pooled across subjects.

    LLM approaches pool all six subjects; Yekta-ACO pools only the subjects
    where it applies (N/A rows dropped), matching the paper.
    """
    rows = []
    for llm in LLMS:
        for prompt in PROMPTS:
            cells = [r for r in base if r["generator"] == "llm_ladder"
                     and r["llm"] == llm and r["prompt_condition"] == prompt]
            covered = sum(int(r["covered_rules"]) for r in cells)
            total = sum(int(r["total_rules"]) for r in cells)
            rows.append({"generator": llm, "prompt_condition": prompt,
                         "subjects_included": len(cells), "pooled_covered_rules": covered,
                         "pooled_total_rules": total, "overall_pooled_pct": f"{100.0 * covered / total:.2f}",
                         "notes": ""})
    for generator, table_name in (("yekta_aco", "Yekta-ACO"),):
        cells = [r for r in base if r["generator"] == generator]
        covered = sum(int(r["covered_rules"]) for r in cells)
        total = sum(int(r["total_rules"]) for r in cells)
        note = ("available subjects only (N/A subjects dropped)" if generator == "yekta_aco"
                else "Ant2Maven is the established value (10/100 traces retained)")
        rows.append({"generator": table_name, "prompt_condition": "N/A",
                     "subjects_included": len(cells), "pooled_covered_rules": covered,
                     "pooled_total_rules": total, "overall_pooled_pct": f"{100.0 * covered / total:.2f}",
                     "notes": note})
    return rows


def rebuild_rule_coverage(data: Path = DATA) -> list[dict]:
    path = data / "experiment_results/RQ1/rule_coverage.csv"
    original = read_csv(path)
    # Replace aggregates on reruns; preserve every released configuration/baseline row.
    base = [r for r in original if r["prompt_condition"] != "All prompts"]
    cells = {}
    for row in base:
        if row["generator"] != "llm_ladder":
            continue
        key = (row["subject"], row["llm"], row["prompt_condition"])
        if key in cells or key[1] not in LLMS or key[2] not in PROMPTS:
            raise ValueError(f"Duplicate or unexpected coverage cell: {key}")
        cells[key] = row
    subjects = list(dict.fromkeys(k[0] for k in cells))
    expected = {(s, llm, p) for s in subjects for llm in LLMS for p in PROMPTS}
    if len(subjects) != 6 or set(cells) != expected:
        raise ValueError("Expected all 72 subject/LLM/prompt cells")
    totals = {r["transformation"]: int(r["total_rules"])
              for r in read_csv(data / "rq1/supplementary/subjects.csv")}

    population = defaultdict(list)
    eligible = {}
    for row in read_csv(data / "rq1/supplementary/source_population.csv"):
        cell = (row["subject"], row["provider"], row["condition"].upper())
        if cell not in cells:
            continue
        key = (*cell, row["source_id"])
        population[cell].append(row)
        if row["original_execution_success"] == "1" and row["trace_eligible"] == "1":
            if not row["source_id"] or key in eligible:
                raise ValueError(f"Missing or duplicate eligible source ID: {key}")
            eligible[key] = row

    source_rules = defaultdict(dict)
    evidence = data / "rq1/supplementary/source_rule_coverage.csv"
    with evidence.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            key = (row["subject"], ALIASES.get(row["provider"], row["provider"]),
                   row["condition"].upper(), row["source_id"])
            if key not in eligible:
                continue
            rule = row["rule_id"]
            if not rule or rule in source_rules[key] or row["covered"] not in {"0", "1"}:
                raise ValueError(f"Invalid or duplicate rule record: {key}/{rule}")
            source_rules[key][rule] = int(row["covered"])
    if set(source_rules) != set(eligible):
        missing = sorted(set(eligible) - set(source_rules))
        raise ValueError(f"Missing rule-level evidence for {len(missing)} sources: {missing[:3]}")

    universes = {}
    cell_rules = defaultdict(set)
    source_counts = defaultdict(int)
    for key, rules in source_rules.items():
        subject = key[0]
        universe = set(rules)
        if len(universe) != totals[subject] or universes.setdefault(subject, universe) != universe:
            raise ValueError(f"Inconsistent rule universe: {key}")
        covered = {rule for rule, flag in rules.items() if flag}
        if len(covered) != int(eligible[key]["matrix_covered_count"]):
            raise ValueError(f"Source coverage differs from population evidence: {key}")
        cell_rules[key[:3]].update(covered)
        source_counts[key[:3]] += 1
    for key, row in cells.items():
        if (len(cell_rules[key]) != int(row["covered_rules"])
                or source_counts[key] != int(row["n_trace_eligible"])
                or int(row["total_rules"]) != totals[key[0]]
                or round(100 * len(cell_rules[key]) / totals[key[0]], 2) != float(row["rule_coverage_pct"])):
            raise ValueError(f"Rule evidence disagrees with released coverage cell: {key}")
        members = population[key]
        if len(members) != int(row["n_attempts"]):
            raise ValueError(f"Attempt count differs from population: {key}")

    aggregates, details, wide = [], [], []
    for llm in (*LLMS, "All LLM"):
        providers = LLMS if llm == "All LLM" else (llm,)
        table_row = {"Approach": llm, "Prompt": "All prompts"}
        percentages = []
        for subject in subjects:
            keys = [(subject, provider, prompt) for provider in providers for prompt in PROMPTS]
            covered, percentage = union_coverage([cell_rules[k] for k in keys], universes[subject])
            row = {"subject": subject, "generator": "llm_ladder", "llm": llm,
                   "prompt_condition": "All prompts",
                   **{field: sum(int(cells[k][field]) for k in keys) for field in COUNTS},
                   "covered_rules": len(covered), "total_rules": totals[subject],
                   "rule_coverage_pct": f"{percentage:.2f}",
                   "status": "OK" if covered else "EVALUATED_NO_TRACE_ELIGIBLE_MODEL",
                   "coverage_basis_note": "rule-ID union over original-executable, trace-eligible sources; "
                                          "SM+STM+ASTM+ASTMO" + ("; all three LLMs" if llm == "All LLM" else "")}
            aggregates.append(row)
            details.append({"subject": subject, "llm": llm, "prompt_condition": "All prompts",
                            "covered_rules": len(covered), "total_rules": totals[subject],
                            "rule_coverage_pct": f"{percentage:.2f}",
                            "covered_rule_ids": "|".join(sorted(covered)),
                            "uncovered_rule_ids": "|".join(sorted(universes[subject] - covered))})
            table_row[subject] = f"{percentage:.2f}"
            percentages.append(percentage)
        # Macro average of unrounded per-subject fractions, not pooled rule counts.
        table_row["Overall"] = f"{mean(percentages):.2f}"
        wide.append(table_row)

    # All validation finishes before any published output is changed.
    write_csv(path, base + aggregates, list(original[0]))
    write_csv(data / "rq1/supplementary/rq1_rule_coverage_all_prompts.csv", wide,
              ["Approach", "Prompt", *subjects, "Overall"])
    write_csv(data / "rq1/supplementary/rq1_rule_coverage_union_details.csv", details, list(details[0]))
    write_csv(data / "rq1/supplementary/rule_coverage_overall_pooled.csv", pooled_overall_rows(base),
              ["generator", "prompt_condition", "subjects_included", "pooled_covered_rules",
               "pooled_total_rules", "overall_pooled_pct", "notes"])
    return aggregates


if __name__ == "__main__":
    rows = rebuild_rule_coverage()
    print(f"Wrote {len(rows)} All prompts rows, the wide table with Overall macro averages, "
          f"and the pooled Table 5 Overall file.")
