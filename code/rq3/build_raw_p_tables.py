"""Recompute Tables 11/12 using raw two-sided Wilcoxon p < .05.

Run: python code/rq3/build_raw_p_tables.py
Selection and classification use raw p-values on the current canonical population.
"""
import json
from collections import Counter

import apply_yekta_canonical_population as baseline
import build_strict_significance_selection as core
from build_significance_then_mean_selection import select_by_significance

OUT = core.ROOT / "results/rq3/supplementary/raw_p"


def tex_table(caption, label, columns, headers, rows, note):
    text = [r"\begin{table}[t]", r"\centering", r"\caption{"+caption+"}",
            r"\label{"+label+"}", r"\begin{tabular}{"+columns+"}", r"\hline"]
    text.extend(headers)
    text.append(r"\hline")
    text.extend(" & ".join(row) + r" \\" for row in rows)
    text.extend([r"\hline", r"\end{tabular}", r"\par\smallskip",
                 r"\begin{minipage}{\linewidth}\footnotesize "+note,
                 r"\end{minipage}", r"\end{table}"])
    return "\n".join(text)+"\n"


def main():
    internal = core.compute_tests()
    selected, candidates = select_by_significance(internal, "p_raw")
    tests = baseline.pairwise_tests(core.read(core.SOURCE))
    old_tests = core.read(core.ROOT / "results/rq3/data/rq3_pairwise_tests.csv")
    assert len(tests) == len(old_tests) == 216
    for row, old in zip(tests, old_tests):
        for key in ["provider", "condition", "formula", "baseline"]:
            assert row[key] == old[key]
        for key in ["n_common", "p_raw", "A12", "mean_difference"]:
            assert abs(row[key]-float(old[key])) < 1e-12
        assert row["classification"] == old["classification"]
    counts = baseline.counts_of(tests)
    assert len(selected) == len(counts) == 18
    for row in counts:
        for b in ["Yekta-ACO"]:
            assert sum(row[b+"_"+c] for c in ["Worse", "Similar", "Better"]) == 12
    OUT.mkdir(parents=True, exist_ok=True)
    core.TABLES.mkdir(parents=True, exist_ok=True)
    for filename, rows in [("table11_selection.csv", selected), ("table12_counts.csv", counts),
                           ("configuration_candidates.csv", candidates),
                           ("llm_internal_pairwise_tests.csv", internal),
                           ("baseline_pairwise_tests.csv", tests)]:
        core.write(OUT / filename, rows)

    caption11 = "Representative best and worst LLM-generated test suites selected by pairwise significance tests followed by mean EXAM scores."
    caption12 = "Statistical comparison of 12 LLM-generated test suites with baseline test suites."
    shared = (r"Two-sided paired Wilcoxon signed-rank tests use EXAM scores on mutants killed by both "
              r"approaches. Significance is determined by unadjusted $p<0.05$; no multiple-comparison "
              r"correction is applied. $A_{12}>0.5$ favors the first approach, and $A_{12}<0.5$ favors the second.")
    note11 = (shared + " The best cell has the lowest pooled mean EXAM among configurations with no "
              "significant losses; the worst cell has the highest pooled mean EXAM among configurations "
              "with no significant wins. Means use each configuration's own evaluable mutants. "
              "Selected cells are representatives, not necessarily significantly superior or inferior to all alternatives.")
    note12 = (shared + " The first approach is the LLM configuration. Worse/Better indicate a significant "
              "difference favoring the baseline/LLM; Similar indicates no significant difference. "
              "Each baseline has 12 comparisons per formula.")
    rows11 = [[name, r["best"], r["worst"]] for (_, name), r in zip(core.FORMULAS, selected)]
    fields12 = [b+"_"+c for b in ["Yekta-ACO"] for c in ["Worse", "Similar", "Better"]]
    rows12 = [[name]+[str(r[k]) for k in fields12] for (_, name), r in zip(core.FORMULAS, counts)]
    (core.TABLES / "table11_raw_p.tex").write_text(tex_table(
        caption11, "tab:rq3bw-selection", "lll", [r"Formula & Best cell & Worst cell \\"], rows11, note11), encoding="utf-8")
    (core.TABLES / "table12_raw_p.tex").write_text(tex_table(
        caption12, "tab:rq3bw-pairwise-counts", "lrrr",
        [r" & \multicolumn{3}{c}{vs Yekta-ACO} \\",
         r"\cline{2-4}", r"Formula & Worse & Similar & Better \\"] , rows12, note12), encoding="utf-8")
    md = ["# RQ3：原始 p 值版本", "", "两张表均使用双侧配对 Wilcoxon 原始 p < 0.05，不做多重比较校正。",
          "Table 11 先筛选无显著败绩／无显著胜绩的候选，再按各配置自身可评价变异体的平均 EXAM 选最低／最高者。",
          "", "## Table 11", "", "| Formula | Best cell | Worst cell |", "|---|---|---|"]
    md.extend("| " + " | ".join(row) + " |" for row in rows11)
    md.extend(["", "## Table 12", "", "| Formula | Yekta Worse | Yekta Similar | Yekta Better |",
               "|---|---:|---:|---:|"])
    md.extend("| " + " | ".join(row) + " |" for row in rows12)
    md.extend(["", "显著性比较使用双方共同击杀集；A12 判断方向。Similar 不表示已证明等效。",
               "Table 11 的代表不一定显著优于／劣于其余全部配置。显著性使用原始p值。",
               "论文原稿尚未替换；本目录与 results/rq3/tables/table11_raw_p.tex、table12_raw_p.tex 为本次交付。"])
    (OUT / "TABLES.md").write_text("\n".join(md)+"\n", encoding="utf-8")
    audit = dict(
                 scipy_version=core.scipy.__version__, p_used="raw two-sided Wilcoxon p", alpha=0.05,
                 multiple_comparison_correction="none", internal_tests=len(internal), baseline_tests=len(tests),
                 raw_statistics_match_prior=True,
                 table12_totals={b:dict(Counter(r["classification"] for r in tests if r["baseline"]==b))
                                 for b in ["Yekta-ACO"]})
    (OUT / "audit.json").write_text(json.dumps(audit, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
