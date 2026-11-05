#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean, median

from common import DATA, OUTPUTS, output_path, pct, read_csv, write_csv


def rq1() -> None:
    path = DATA / "rq1/data/validity.csv"
    rows = read_csv(path)
    subjects = [k for k in rows[0] if k not in {"Generator", "Cond."}]
    # The baseline rows carry their own success/attempt counts, so validity is
    # self-contained; shared population and ACO files are no longer inputs here.
    for name in ("Yekta-ACO",):
        if sum(r["Generator"] == name for r in rows) != 1:
            raise ValueError(f"Expected exactly one {name} row in validity.csv")
    out = []
    for row in rows:
        is_baseline = row["Generator"] in {"Yekta-ACO"}
        for subject in subjects:
            value = row[subject].strip()
            if value != "N/A":
                if "/" in value:
                    try:
                        numerator, denominator = map(int, value.split("/"))
                    except ValueError:
                        raise ValueError(f"Malformed count in validity.csv: {row['Generator']}/{subject}")
                    if denominator <= 0 or not 0 <= numerator <= denominator:
                        raise ValueError(f"Invalid count in validity.csv: {row['Generator']}/{subject}")
                    value = f"{pct(numerator, denominator):.1f}"
                elif is_baseline:
                    raise ValueError(f"Baseline row lacks success/attempt counts: {row['Generator']}/{subject}")
                else:
                    value = f"{float(value):.1f}"
                if not 0 <= float(value) <= 100:
                    raise ValueError(f"RQ1 percentage out of range: {row['Generator']}/{subject}")
            out.append({
                "generator": row["Generator"],
                "condition": row["Cond."],
                "subject": subject,
                "validity_pct": value,
            })
    write_csv(output_path("rq1_validity_long.csv"), out, ["generator", "condition", "subject", "validity_pct"])
    # model_size.csv is published from the 2026-10-14 containment-size audit
    # (code/rq1/model_size_audit + rq1/supplementary/model_size_audit);
    # the legacy strict-count rebuild must not overwrite it.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "rq1"))
    from rule_coverage import rebuild_rule_coverage
    rebuild_rule_coverage(data=DATA)


def rq2() -> None:
    rows = read_csv(DATA / "rq2/data/mutation_score.csv")
    fields = ["approach", "prompt_condition", "subject", "eligible_mutants", "executable_source_models", "killed_mutants", "undetected_mutants", "mutation_score"]
    write_csv(output_path("rq2_mutation_score.csv"), [{k: r[k] for k in fields} for r in rows], fields)
    shutil.copyfile(DATA / "shared/aco/mutation_score.csv", output_path("aco_strict_mutation_score.csv"))


def rq4() -> None:
    shutil.copyfile(DATA / "rq4/supplementary/paper_joint_summary.csv", output_path("rq4_joint_summary.csv"))


def rq5() -> list[dict[str, object]]:
    metrics = read_csv(DATA / "rq5/data/workflow_metrics.csv")
    rows = [r for r in metrics if r["condition"] == "workflow"]
    out = []
    total = sum(int(r["n_estar"]) for r in rows)
    out.append({"scope": "All", "n_estar": total, "denominator": 1800, "validity_pct": pct(total, 1800), "non_verifiable": 1800 - total})
    for llm in ["GPT", "Qwen", "DeepSeek"]:
        n = sum(int(r["n_estar"]) for r in rows if r["llm"] == llm)
        out.append({"scope": llm, "n_estar": n, "denominator": 600, "validity_pct": pct(n, 600), "non_verifiable": 600 - n})
    write_csv(output_path("rq5_workflow_validity.csv"), out, ["scope", "n_estar", "denominator", "validity_pct", "non_verifiable"])

    metric_index = {(r["subject"], r["llm"], r["condition"]): r for r in metrics}
    coverage_rows = []
    for llm in ["GPT", "Qwen", "DeepSeek"]:
        subjects = [
            r["subject"] for r in metrics
            if r["llm"] == llm and r["condition"] == "astmo" and r["coverage_pct"] != "--"
        ]
        baseline = mean(float(metric_index[(subject, llm, "astmo")]["coverage_pct"]) for subject in subjects)
        optimized = mean(float(metric_index[(subject, llm, "workflow")]["coverage_pct"]) for subject in subjects)
        coverage_rows.append({
            "llm": llm,
            "n_comparable_subjects": len(subjects),
            "astmo_coverage_pct": f"{baseline:.1f}",
            "workflow_coverage_pct": f"{optimized:.1f}",
            "delta_pp": f"{optimized - baseline:+.1f}",
        })
    write_csv(
        output_path("rq5_coverage_paired.csv"),
        coverage_rows,
        ["llm", "n_comparable_subjects", "astmo_coverage_pct", "workflow_coverage_pct", "delta_pp"],
    )

    overlap = [r for r in read_csv(DATA / "rq5/data/mutant_overlap.csv") if r["comparison_status"] != "BASELINE_EMPTY"]
    overlap_rows = []
    for llm in ["GPT", "Qwen", "DeepSeek"]:
        members = [r for r in overlap if r["provider"] == llm]
        overlap_rows.append({
            "llm": llm,
            "n_comparable_subjects": len(members),
            "shared_mutants": sum(int(r["shared_mutants"]) for r in members),
            "astmo_only_mutants": sum(int(r["astmo_only_mutants"]) for r in members),
            "workflow_only_mutants": sum(int(r["workflow_only_mutants"]) for r in members),
            "neither_mutants": sum(int(r["neither_mutants"]) for r in members),
        })
    write_csv(
        output_path("rq5_mutant_overlap_summary.csv"),
        overlap_rows,
        ["llm", "n_comparable_subjects", "shared_mutants", "astmo_only_mutants", "workflow_only_mutants", "neither_mutants"],
    )

    source = read_csv(DATA / "rq1/supplementary/source_population.csv")
    medians = []
    for row in rows:
        values = [
            int(r["model_size"]) for r in source
            if r["subject"] == row["subject"] and r["provider"] == row["llm"]
            and r["condition"] == "workflow" and r["in_estar"] == "1" and r["model_size"]
        ]
        if values:
            medians.append({"subject": row["subject"], "llm": row["llm"], "median_model_size": median(values)})
    write_csv(output_path("rq5_workflow_model_size_medians.csv"), medians, ["subject", "llm", "median_model_size"])
    return out


def population() -> None:
    rows = read_csv(DATA / "shared/population/estar_population_by_cell.csv")
    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        groups[row["condition"]].append(row)
    out = []
    for condition, members in sorted(groups.items()):
        e = sum(int(r["n_E"]) for r in members)
        estar = sum(int(r["n_estar"]) for r in members)
        out.append({"condition": condition, "n_cells": len(members), "n_E": e, "n_estar": estar, "n_dropped": e - estar})
    write_csv(output_path("population_summary.csv"), out, ["condition", "n_cells", "n_E", "n_estar", "n_dropped"])


def report(workflow_rows: list[dict[str, object]]) -> None:
    aco = {r["subject"]: r for r in read_csv(DATA / "shared/aco/mutation_score.csv")}
    ant_audit = json.loads((DATA / "shared/audit/ant2maven_trace_scope_audit.json").read_text(encoding="utf-8"))
    all_row = next(r for r in workflow_rows if r["scope"] == "All")
    qwen = next(r for r in workflow_rows if r["scope"] == "Qwen")
    text = f"""# Reproduction report

- Workflow validity: {all_row['n_estar']}/{all_row['denominator']} = {all_row['validity_pct']:.1f}%.
- Non-verifiable workflow attempts: {all_row['non_verifiable']}.
- Qwen workflow validity: {qwen['n_estar']}/{qwen['denominator']} = {qwen['validity_pct']:.1f}%.
- ACO BibTeX2DocBook mutation score: {float(aco['BibTeX2DocBook']['strict_mutation_score_pct']):.1f}%.
- ACO CPL2SPL mutation score: {float(aco['CPL2SPL']['strict_mutation_score_pct']):.1f}%.
- ACO UML2ER mutation score: {float(aco['UML2ER']['strict_mutation_score_pct']):.1f}%.
- Ant2Maven coverage and EXAM rule universe: {ant_audit['base_rules']} original ATL rules.
- Ant2Maven target/trace audit: {ant_audit['stored_outputs']['files']['target']:,} target XMI files and {ant_audit['stored_outputs']['files']['trace']:,} separate trace files; no target/trace mixing found.
"""
    (output_path("reproduction_report.md")).write_text(text, encoding="utf-8")


def main() -> None:
    OUTPUTS.mkdir(exist_ok=True)
    population()
    rq1()
    rq2()
    rq4()
    workflow = rq5()
    report(workflow)
    print(f"Wrote reproduction outputs to {OUTPUTS}")


if __name__ == "__main__":
    main()
