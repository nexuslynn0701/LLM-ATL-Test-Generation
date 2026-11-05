"""Build RQ3 Tables 11/12 from paired mutant-level EXAM comparisons.

Run: python code/rq3/build_pairwise_significance_only.py
Each two-sided paired Wilcoxon test uses the mutants killed by both suites.
Raw p < .05 determines significance, and A12 determines the direction.
No means or multiple-comparison correction enter either table.
"""
import json
from collections import Counter, defaultdict

import apply_yekta_canonical_population as baseline
import build_strict_significance_selection as core

OUT = core.ROOT / "results/rq3/supplementary/pairwise_significance_only"


def latex(caption, label, columns, heading, rows, note):
    lines = [r"\begin{table}[t]", r"\centering", r"\caption{" + caption + "}",
             r"\label{" + label + "}", r"\begin{tabular}{" + columns + "}", r"\hline"]
    lines.extend(heading)
    lines.append(r"\hline")
    lines.extend(" & ".join(row) + r" \\" for row in rows)
    lines.extend([r"\hline", r"\end{tabular}", r"\par\smallskip",
                  r"\begin{minipage}{\linewidth}\footnotesize " + note,
                  r"\end{minipage}", r"\end{table}"])
    return "\n".join(lines) + "\n"


def main():
    internal = core.compute_tests()
    baseline_tests = baseline.pairwise_tests(core.read(core.SOURCE))
    assert len(internal) == 1188 and len(baseline_tests) == 216
    expected = core.read(core.ROOT / "results/rq3/data/rq3_pairwise_tests.csv")
    for row, old in zip(baseline_tests, expected):
        assert tuple(row[k] for k in ["provider", "condition", "formula", "baseline"]) == tuple(
            old[k] for k in ["provider", "condition", "formula", "baseline"])
        for field in ["n_common", "p_raw", "A12", "mean_difference"]:
            assert abs(float(row[field])-float(old[field])) < 1e-12

    # A12_a > .5 favors cell_a; in the baseline comparison A12 > .5 favors LLM.
    # Keep the full effect size in the detail CSV even though the compact main
    # tables show candidate names and class counts, respectively.
    for row in internal:
        row["classification"] = ("Similar" if row["p_raw"] >= .05 else
                                 "A_Better" if row["A12_a"] > .5 else "B_Better")
        row.pop("mean_difference")
    for row in baseline_tests:
        row["classification"] = ("Similar" if row["p_raw"] >= .05 else
                                 "Better" if row["A12"] > .5 else "Worse")
        row.pop("mean_difference")

    wins = defaultdict(Counter)
    losses = defaultdict(Counter)
    for row in internal:
        if row["classification"] == "Similar":
            continue
        winner, loser = ((row["cell_a"], row["cell_b"]) if row["classification"] == "A_Better"
                         else (row["cell_b"], row["cell_a"]))
        wins[row["formula"]][winner] += 1
        losses[row["formula"]][loser] += 1

    table11 = []
    details = []
    labels = [core.label(c) for c in core.CELLS]
    for formula, _ in core.FORMULAS:
        best = [c for c in labels if losses[formula][c] == 0]
        worst = [c for c in labels if wins[formula][c] == 0]
        assert best and worst
        table11.append(dict(formula=formula, best_candidates=" / ".join(best),
                            worst_candidates=" / ".join(worst), n_best=len(best), n_worst=len(worst)))
        for cell in labels:
            details.append(dict(formula=formula, cell=cell,
                                significant_wins=wins[formula][cell],
                                significant_losses=losses[formula][cell],
                                nonsignificant_comparisons=11-wins[formula][cell]-losses[formula][cell],
                                best_candidate=int(cell in best), worst_candidate=int(cell in worst)))

    table12 = []
    for formula, _ in core.FORMULAS:
        row = dict(formula=formula)
        for b in ["Yekta-ACO"]:
            classes = Counter(r["classification"] for r in baseline_tests
                              if r["formula"] == formula and r["baseline"] == b)
            assert sum(classes.values()) == 12
            for category in ["Worse", "Similar", "Better"]:
                row[b + "_" + category] = classes[category]
        table12.append(row)

    # Independent check against the prior raw-p result: its candidate flags
    # and baseline counts must match, while mean-based representative choices
    # are deliberately ignored.
    prior_candidates = {(r["formula"], r["cell"]): r for r in core.read(
        core.ROOT / "results/rq3/supplementary/raw_p/configuration_candidates.csv")}
    for row in details:
        old = prior_candidates[(row["formula"], row["cell"])]
        for field in ["significant_wins", "significant_losses", "best_candidate", "worst_candidate"]:
            assert int(row[field]) == int(old[field])
    old_counts = core.read(core.ROOT / "results/rq3/supplementary/raw_p/table12_counts.csv")
    assert table12 == [{k: int(v) if k != "formula" else v for k, v in row.items()}
                       for row in old_counts]

    OUT.mkdir(parents=True, exist_ok=True)
    core.TABLES.mkdir(parents=True, exist_ok=True)
    for name, rows in [("table11_candidates.csv", table11), ("table12_counts.csv", table12),
                       ("llm_internal_pairwise_tests.csv", internal),
                       ("baseline_pairwise_tests.csv", baseline_tests),
                       ("configuration_win_loss_counts.csv", details)]:
        core.write(OUT / name, rows)

    caption11 = "LLM-generated test suite candidates identified by pairwise EXAM significance tests for each SBFL formula."
    caption12 = "Statistical comparison of 12 LLM-generated test suites with test suites generated by the baselines."
    method = ("Each paired Wilcoxon signed-rank test uses mutant-level EXAM scores for mutants killed by "
              "both approaches; significance is based on the unadjusted $p<0.05$. "
              "No multiple-comparison correction or mean EXAM selection is used.")
    note11 = (method + " A best candidate has no significant losses against the other 11 LLM "
              "configurations; a worst candidate has no significant wins. Multiple candidates may occur. "
              "Nonsignificance does not establish equivalence. The full pairwise results include $A_{12}$, "
              "where values above 0.5 favor the first named configuration and values below 0.5 favor the second.")
    note12 = (method + " Worse/Better denotes a significant difference favoring the baseline/LLM; "
              "Similar denotes no significant difference. The full pairwise results include $A_{12}$, "
              "where values above 0.5 favor the LLM and values below 0.5 favor the baseline.")
    rows11 = [[name, r["best_candidates"], r["worst_candidates"]]
              for (_, name), r in zip(core.FORMULAS, table11)]
    fields12 = [b + "_" + c for b in ["Yekta-ACO"]
                for c in ["Worse", "Similar", "Better"]]
    rows12 = [[name] + [str(r[k]) for k in fields12]
              for (_, name), r in zip(core.FORMULAS, table12)]
    (core.TABLES / "table11_pairwise_significance.tex").write_text(latex(
        caption11, "tab:rq3bw-selection", "lll",
        [r"Formula & Best candidates & Worst candidates \\"], rows11, note11), encoding="utf-8")
    (core.TABLES / "table12_pairwise_significance.tex").write_text(latex(
        caption12, "tab:rq3bw-pairwise-counts", "lrrr",
        [r" & \multicolumn{3}{c}{vs Yekta-ACO} \\",
         r"\cline{2-4}",
         r"Formula & Worse & Similar & Better \\"], rows12, note12),
        encoding="utf-8")

    md = ["# RQ3 配对显著性结果（原始 p 值）", "",
          "每项比较按 subject + mutant_id 配对，在双方共同 killed mutants 上取逐 mutant 的 EXAM-AC；双侧 Wilcoxon 原始 p < 0.05 判显著。A12 报告效应量及方向。没有均值选择或多重比较校正。",
          "", "## Table 11", "", "| Formula | Best candidates | Worst candidates |",
          "|---|---|---|"]
    md.extend("| " + " | ".join(row) + " |" for row in rows11)
    md.extend(["", "## Table 12", "",
               "| Formula | Yekta Worse | Yekta Similar | Yekta Better |",
               "|---|---:|---:|---:|"])
    md.extend("| " + " | ".join(row) + " |" for row in rows12)
    md.extend(["", "Table 11 的 Best candidates 为没有显著败绩的配置；Worst candidates 为没有显著胜绩的配置。",
               "Table 12 的 Better/Worse 方向相对于 LLM。两表的逐项 p、A12、共同 mutant 数分别保存在两个 pairwise_tests.csv。",
               "未检出显著差异不表示两种配置等效。论文原稿尚未替换。"])
    (OUT / "TABLES.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    audit = dict(
                 scipy_version=core.scipy.__version__, internal_tests=1188, baseline_tests=216,
                 alpha=0.05, p_used="raw two-sided Wilcoxon", paired_unit="subject + mutant_id",
                 population="mutants evaluable for both suites", effect_size="Vargha-Delaney A12",
                 mean_selection=False, multiple_comparison_correction="none",
                 n_formulas=18, n_best_singletons=sum(r["n_best"] == 1 for r in table11),
                 n_worst_singletons=sum(r["n_worst"] == 1 for r in table11),
                 prior_raw_p_results_match=True)
    (OUT / "audit.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
