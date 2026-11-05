#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from collections import defaultdict
from statistics import mean, median

from common import DATA, ROOT, pct, read_csv


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)
    print(f"PASS  {message}")


def main() -> None:
    cells = read_csv(DATA / "shared/population/estar_population_by_cell.csv")
    workflow = [r for r in cells if r["condition"] == "workflow"]
    require(len(workflow) == 18, "workflow contains 6 subjects x 3 providers")
    require(sum(int(r["n_estar"]) for r in workflow) == 1644, "workflow E* count is 1,644")

    qwen = [r for r in workflow if r["provider"] == "Qwen"]
    require(sum(int(r["n_estar"]) for r in qwen) == 567, "Qwen workflow E* count is 567")
    by_provider = {
        provider: sum(int(r["n_estar"]) for r in workflow if r["provider"] == provider)
        for provider in {r["provider"] for r in workflow}
    }
    require(by_provider == {"GPT": 521, "Qwen": 567, "DeepSeek": 556}, "workflow provider totals are 521, 567, and 556")
    cpl_qwen = next(r for r in qwen if r["subject"] == "CPL2SPL")
    require(int(cpl_qwen["n_estar"]) == 96, "CPL2SPL/Qwen/workflow E* count is 96")

    source = read_csv(DATA / "rq1/supplementary/source_population.csv")
    index = {(r["subject"], r["provider"], r["condition"], r["source_id"]): r for r in source}
    require(index[("CPL2SPL", "Qwen", "workflow", "0061")]["in_estar"] == "0", "source 0061 is excluded")
    require(index[("CPL2SPL", "Qwen", "workflow", "0080")]["in_estar"] == "0", "source 0080 is excluded")
    require(index[("Ant2Maven", "GPT", "astmo", "0030")]["in_estar"] == "1", "source 0030 is included")

    subjects = {r["transformation"]: r for r in read_csv(ROOT / "results/rq1/data/subjects.csv")}
    require(subjects["Ant2Maven"]["total_rules"] == "30", "Ant2Maven protocol uses the 30-rule original transformation")

    ant_audit = json.loads((DATA / "shared/audit/ant2maven_trace_scope_audit.json").read_text(encoding="utf-8"))
    require(ant_audit["base_rules"] == 30, "Ant2Maven audited base rule universe has 30 rules")
    require(ant_audit["final_script_universe_equal_base"] and ant_audit["rq1_canonical_equal_base"], "Ant2Maven final rule universes equal the original rule set")
    require(ant_audit["spectra"] == {
        "rows": 4449000,
        "cells": 16,
        "all_cells_equal_base": True,
        "test_mutant_blocks": 148300,
        "all_blocks_equal_base": True,
    }, "Ant2Maven audit covers 16 configurations and 4,449,000 spectrum records")
    require(ant_audit["exam"]["denominator_counts"] == {"30": 34560}, "all 34,560 expanded Ant2Maven EXAM records use denominator 30")
    require(ant_audit["exam"]["evaluable_rows"] == 13500 and ant_audit["exam"]["wrong_rank_over_30"] == 0, "all 13,500 evaluable Ant2Maven EXAM records satisfy rank-average divided by 30")
    stored = ant_audit["stored_outputs"]
    require(stored["files"] == {"target": 2202, "trace": 1101} and not stored["bad"], "2,202 audited Ant2Maven target XMI files contain no mixed-in trace elements")
    require(stored["empty_traces"] == 0 and not stored["trace_extra_rules"], "all 1,101 audited Ant2Maven traces are non-empty and contain only original rules")
    require(
        (ant_audit["trace_only_change_classification"], ant_audit["target_change_classification"], ant_audit["embedded_trace_change_classification"])
        == ("ALIVE", "KILLED", "KILLED"),
        "Ant2Maven oracle excludes the separate trace resource but compares complete selected target trees",
    )

    ant_rq4 = [r for r in read_csv(DATA / "rq4/supplementary/master_cells.csv") if r["subject"] == "Ant2Maven"]
    require(ant_rq4 and all(r["total_rules"] == "30" for r in ant_rq4), "all released Ant2Maven RQ4 cells use 30 coverage rules")
    ant_rq5 = [r for r in read_csv(DATA / "rq5/supplementary/localization_mechanism.csv") if r["subject"] == "Ant2Maven"]
    require(ant_rq5 and all(r["rule_universe_size"] == "30" for r in ant_rq5), "all released Ant2Maven RQ5 localization cells use 30 rules")
    ant_exam = [r for r in read_csv(DATA / "rq3/data/mutant_level_exam.csv") if r["subject"] == "Ant2Maven"]
    require(ant_exam and all(r["rule_count"] == "30" for r in ant_exam), "all released Ant2Maven mutant-level EXAM rows use denominator 30")

    workflow_metrics = read_csv(DATA / "rq5/data/workflow_metrics.csv")
    wf_index = {(r["subject"], r["llm"], r["condition"]): r for r in workflow_metrics}
    require(round(float(wf_index[("Ant2Maven", "GPT", "astmo")]["coverage_pct"]), 1) == 93.3, "final Ant2Maven/GPT/ASTMO coverage is 93.3%")
    require(round(float(wf_index[("Ant2Maven", "Qwen", "astmo")]["coverage_pct"]), 1) == 60.0, "final Ant2Maven/Qwen/ASTMO coverage is 60.0%")
    require(round(float(wf_index[("Ant2Maven", "DeepSeek", "astmo")]["coverage_pct"]), 1) == 83.3, "final Ant2Maven/DeepSeek/ASTMO coverage is 83.3%")
    require(all(float(wf_index[("UML2ER", llm, condition)]["coverage_pct"]) == 100.0 for llm in ("GPT", "Qwen", "DeepSeek") for condition in ("astm", "astmo", "workflow")), "UML2ER coverage uses its 8-rule universe")

    comparable_coverage = {
        (r["subject"], r["llm"])
        for r in workflow_metrics
        if r["condition"] == "astmo" and r["coverage_pct"] != "--"
    }
    for llm, expected_base, expected_workflow in (
        ("GPT", 97.2, 99.1),
        ("Qwen", 91.0, 99.5),
        ("DeepSeek", 94.6, 98.0),
    ):
        keys = {key for key in comparable_coverage if key[1] == llm}
        base = mean(float(wf_index[(subject, llm, "astmo")]["coverage_pct"]) for subject, _ in keys)
        optimized = mean(float(wf_index[(subject, llm, "workflow")]["coverage_pct"]) for subject, _ in keys)
        require(round(base, 1) == expected_base and round(optimized, 1) == expected_workflow, f"{llm} coverage uses the same comparable subjects: {expected_base:.1f}% to {expected_workflow:.1f}%")

    ecore_ds_sizes = [
        int(r["model_size"])
        for r in source
        if r["subject"] == "Ecore2Maude" and r["provider"] == "DeepSeek"
        and r["condition"] == "workflow" and r["in_estar"] == "1" and r["model_size"]
    ]
    require(median(ecore_ds_sizes) == 7.5, "minimum workflow cell median model size is 7.5 EObjects")

    overlap = read_csv(DATA / "rq5/data/mutant_overlap.csv")
    comparable_overlap = [r for r in overlap if r["comparison_status"] != "BASELINE_EMPTY"]
    wf_only = {
        llm: sum(int(r["workflow_only_mutants"]) for r in comparable_overlap if r["provider"] == llm)
        for llm in ("GPT", "Qwen", "DeepSeek")
    }
    require(wf_only == {"GPT": 19, "Qwen": 27, "DeepSeek": 29}, "workflow-only mutant totals are 19, 27, and 29")
    require(sum(int(r["astmo_only_mutants"]) for r in comparable_overlap) == 1, "exactly one ASTMO-only mutant remains in comparable cells")

    formulas = read_csv(DATA / "rq3/supplementary/cell_formula_scores.csv")
    ochiai = [r for r in formulas if r["formula"] == "ochiai" and r["condition"] in {"astmo", "workflow"}]
    astmo_keys = {(r["subject"], r["provider"]) for r in ochiai if r["condition"] == "astmo"}
    astmo_ochiai = mean(float(r["mean_exam_ac"]) for r in ochiai if r["condition"] == "astmo")
    workflow_ochiai = mean(float(r["mean_exam_ac"]) for r in ochiai if r["condition"] == "workflow" and (r["subject"], r["provider"]) in astmo_keys)
    require(round(astmo_ochiai, 3) == 0.402 and round(workflow_ochiai, 3) == 0.372, "paired Ochiai EXAM-AC is 0.402 to 0.372")

    aco = {r["subject"]: r for r in read_csv(DATA / "shared/aco/mutation_score.csv")}
    expected = {"BibTeX2DocBook": 80.0, "CPL2SPL": 100.0, "UML2ER": 72.2222}
    for subject, score in expected.items():
        require(abs(float(aco[subject]["strict_mutation_score_pct"]) - score) < 0.0001, f"ACO {subject} strict score is {score:g}%")

    aco_validity = {r["subject"]: r for r in read_csv(DATA / "shared/aco/validity.csv")}
    require(aco_validity["BibTeX2DocBook"]["n_original_executable"] == "100", "ACO BibTeX2DocBook has 100 executable sources")
    aco_coverage = {r["subject"]: r for r in read_csv(DATA / "shared/aco/rule_coverage.csv")}
    require(aco_coverage["BibTeX2DocBook"]["rule_coverage_pct"] == "77.78", "ACO BibTeX2DocBook rule coverage is 77.78%")

    per_mutant = read_csv(DATA / "shared/aco/per_mutant_outcomes.csv")
    by_subject: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in per_mutant:
        by_subject[row["subject"]].append(row)
    for subject, score in expected.items():
        rows = by_subject[subject]
        killed = sum(int(r["killed_binary"]) for r in rows)
        require(pct(killed, len(rows)) == round(score, 1), f"ACO {subject} score reproduces from mutant outcomes")

    # Independent cross-RQ guard: rankings must use exactly RQ2's fail labels,
    # rather than merely reusing the same canonically killed mutant population.
    aco_pairs = []
    for name in ("source_mutant_outcomes_aco_canonical_bibtex.csv",
                 "source_mutant_outcomes_aco_replay_cpl_uml.csv"):
        aco_pairs += read_csv(ROOT / "code/rq2/data/aco" / name)
    failure_counts = defaultdict(int)
    for row in aco_pairs:
        failure_counts[(row["subject"], row["mutant_id"])] += row["outcome"] == "KILLED"
    aco_exam = [r for r in read_csv(DATA / "rq3/data/mutant_level_exam.csv") if r["provider"] == "Yekta-ACO"]
    require(len(aco_pairs) == 10600 and len(aco_exam) == 1944,
            "ACO canonical evidence covers 10,600 pairs and 1,944 localization rows")
    require(all(int(r["failing_sources"] or 0) == failure_counts[(r["subject"], r["mutant_id"])] for r in aco_exam),
            "all ACO SBFL failing-source counts equal canonical RQ2 kill counts")
    require(all((r["evaluable"] == "1") == (failure_counts[(r["subject"], r["mutant_id"])] > 0) for r in aco_exam),
            "ACO evaluability and SBFL fail/pass labels share the same oracle")

    prompts = [p for p in (ROOT / "data/prompts").glob("*/*.txt")
               if p.stem in {"sm", "stm", "astm", "astmo"}]
    prompts += list((ROOT / "data/workflow/prompts").glob("*.txt"))
    require(len(prompts) == 31, "24 ladder prompts, 6 workflow prompts, and the workflow template are present")

    # The generated XMI artifacts (data/test_cases/*.xmi) are regenerable via
    # the shipped harness and are not part of the public checkout; the checks
    # below run only when the artifacts are present (e.g. after regeneration).
    test_cases_root = ROOT / "data/test_cases"
    if next(test_cases_root.rglob("*.xmi"), None) is None:
        print("SKIP  generated test models (data/test_cases/*.xmi) are not present in this checkout;")
        print("      population/artifact consistency checks require regenerating them with the harness")
    else:
        expected_cases = {
            (r["subject"], r["provider"], r["condition"], r["source_id"])
            for r in source if r["artifact_exists"] == "1"
        }
        provider_dirs = {"GPT": "gpt", "Qwen": "qwen", "DeepSeek": "deepseek"}
        def case_path(key):
            subject, provider, condition, source_id = key
            base = ROOT / "data/test_cases" / subject
            if condition == "random":
                base /= "_baselines"
            return base / condition / provider_dirs[provider] / f"{source_id}.xmi"

        missing_cases = [
            key for key in expected_cases
            if not case_path(key).is_file()
        ]
        require(len(expected_cases) == 8921 and not missing_cases, "all 8,921 generated XMI artifacts are present")
        expected_paths = {case_path(key) for key in expected_cases}
        aco_paths = set(test_cases_root.glob("*/_baselines/aco/*/*.xmi"))
        # Only currently published suites belong to this consistency check.
        retired_paths = set(test_cases_root.glob("*/_baselines/random/*/*.xmi"))
        actual_paths = set(test_cases_root.rglob("*.xmi")) - aco_paths - retired_paths
        require(actual_paths == expected_paths, "subject-first test cases exactly match the released population")
        aco_cases = read_csv(test_cases_root / "_metadata/aco/manifest.csv")
        aco_case_paths = {ROOT / row["path"] for row in aco_cases}
        require(len(aco_cases) == 300 and len(aco_case_paths) == 300
                and aco_case_paths == aco_paths,
                "all 300 archived ACO source models are present, with no extra or missing XMI")
        for subject in ("BibTeX2DocBook", "CPL2SPL", "UML2ER"):
            require(sum(row["subject"] == subject for row in aco_cases) == 100,
                    f"ACO {subject} retains 100 source models")

    require({r["condition"] for r in cells} <= {"sm", "stm", "astm", "astmo", "workflow", "random"}, "population uses the public condition vocabulary")
    local_paths = []
    released_bases = [DATA / f"rq{i}/data" for i in range(1, 6)]
    released_bases += [DATA / "shared" / n for n in ("aco", "audit", "population", "protocol")]
    released_bases += [ROOT / "data/prompts" / s for s in subjects]
    released_bases += [ROOT / "data/workflow/prompts"]
    local_path_markers = (
        "/home/",
        ":\\Users\\",
        ":/Users/",
        "Desktop\\ppt",
        "Desktop/ppt",
    )
    for base in released_bases:
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            if any(marker in text for marker in local_path_markers):
                local_paths.append(str(path.relative_to(ROOT)))
    require(not local_paths, "released files contain no local absolute paths")

    print("\nAll artifact checks passed.")


if __name__ == "__main__":
    try:
        main()
    except (AssertionError, KeyError, ValueError) as exc:
        print(f"FAIL  {exc}", file=sys.stderr)
        raise SystemExit(1)
