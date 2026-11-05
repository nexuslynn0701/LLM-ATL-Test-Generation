"""Table 11: filter by significant losses/wins, then select by pooled mean EXAM.

Run: python code/rq3/build_significance_then_mean_selection.py
The historical strict-selection outputs and Table 12 are not overwritten.
"""
import json
from collections import defaultdict
from fractions import Fraction

import build_strict_significance_selection as core

OUT = core.ROOT / "results/rq3/supplementary/significance_then_mean"


def select_by_significance(tests, p_field):
    _, counts = core.select(tests, p_field)
    values = defaultdict(list)
    for row in core.read(core.SOURCE):
        cell = (row["provider"], row["condition"])
        if row["evaluable"] != "1" or cell not in core.CELLS:
            continue
        denominator = 2 * int(row["rule_count"]) * int(row["n_faulty_rules"])
        raw = Fraction(row["exam_ac"])
        exact = Fraction(round(raw * denominator), denominator)
        assert abs(raw-exact) <= Fraction(1, 10**10)
        values[(row["formula"], core.label(cell))].append(exact)
    means = {key: sum(v)/len(v) for key, v in values.items()}
    for row in counts:
        key = (row["formula"], row["cell"])
        row.pop("qualifies_best")
        row.pop("qualifies_worst")
        row.update(n_evaluable=len(values[key]), pooled_mean_exam=float(means[key]),
                   best_candidate=int(row["significant_losses"] == 0),
                   worst_candidate=int(row["significant_wins"] == 0))
    selection = []
    for formula, _ in core.FORMULAS:
        candidates = [r for r in counts if r["formula"] == formula]
        best = [r["cell"] for r in candidates if r["best_candidate"]]
        worst = [r["cell"] for r in candidates if r["worst_candidate"]]
        # Do not silently fall back to all configurations if a candidate set is empty.
        assert best and worst, (formula, best, worst)
        minimum = min(means[(formula, c)] for c in best)
        maximum = max(means[(formula, c)] for c in worst)
        selected_best = [c for c in best if means[(formula, c)] == minimum]
        selected_worst = [c for c in worst if means[(formula, c)] == maximum]
        selection.append(dict(formula=formula, best=" / ".join(selected_best),
                              worst=" / ".join(selected_worst),
                              best_mean_exam=float(minimum), worst_mean_exam=float(maximum),
                              n_best_candidates=len(best), n_worst_candidates=len(worst),
                              best_candidates=";".join(best), worst_candidates=";".join(worst)))
    return selection, counts


def main():
    tests = core.compute_tests()
    selection, counts = select_by_significance(tests, "p_raw")
    old_means = {r["formula"]: r for r in core.read(core.ROOT / "results/rq3/data/rq3_best_worst.csv")}
    changes = [dict(formula=r["formula"], old_best=old_means[r["formula"]]["best"],
                    new_best=r["best"], old_worst=old_means[r["formula"]]["worst"], new_worst=r["worst"])
               for r in selection if r["best"] != old_means[r["formula"]]["best"]
               or r["worst"] != old_means[r["formula"]]["worst"]]
    OUT.mkdir(parents=True, exist_ok=True)
    core.TABLES.mkdir(parents=True, exist_ok=True)
    core.write(OUT / "table11_selection.csv", selection)
    core.write(OUT / "configuration_candidates.csv", counts)
    core.write(OUT / "llm_internal_pairwise_tests.csv", tests)
    if changes:
        core.write(OUT / "changes_from_mean_only.csv", changes)
    caption = "Representative best and worst LLM-generated test suites selected by pairwise significance tests followed by mean EXAM scores."
    note = ("For each SBFL formula, the best cell has the lowest pooled mean EXAM among configurations "
            "not significantly outperformed by any other configuration. The worst cell has the highest "
            "pooled mean EXAM among configurations that do not significantly outperform any other configuration. "
            "Pairwise tests use mutants killed by both configurations, whereas pooled means use each configuration's "
            "own evaluable mutants. Two-sided paired Wilcoxon signed-rank tests use raw "
            "p < 0.05 and A12 to determine significant differences and their direction. Selected cells are "
            "representatives and are not necessarily significantly better or worse than all other configurations.")
    tex = [r"\begin{table}[t]", r"\centering", r"\caption{"+caption+"}",
           r"\label{tab:rq3bw-selection}", r"\begin{tabular}{lll}", r"\hline",
           r"Formula & Best cell & Worst cell \\", r"\hline"]
    for (_, name), row in zip(core.FORMULAS, selection):
        tex.append(f"{name} & {row['best']} & {row['worst']} " + r"\\")
    tex.extend([r"\hline", r"\end{tabular}", r"\par\smallskip",
                r"\begin{minipage}{\linewidth}\footnotesize " +
                note.replace("p < 0.05", r"$p<0.05$").replace("A12", r"$A_{12}$"),
                r"\end{minipage}", r"\end{table}"])
    (core.TABLES / "table11_significance_then_mean.tex").write_text("\n".join(tex)+"\n", encoding="utf-8")
    md = ["Table 11. " + caption, "", "| Formula | Best cell | Worst cell |", "|---|---|---|"]
    md.extend(f"| {name} | {r['best']} | {r['worst']} |" for (_, name), r in zip(core.FORMULAS, selection))
    md.extend(["", note, "", "当前规则：先按显著性确定候选，再按各配置自身可评价变异体上的 pooled mean EXAM 选择代表。",
               "均值完全相同则并列列出；本次未出现并列。每个比较的共同变异体集合可不同，候选集合不表示已经证明等效。",
               "此前严格要求对其余全部 11 个配置获胜／落败的版本仅留作历史对照。"])
    (OUT / "TABLE11.md").write_text("\n".join(md)+"\n", encoding="utf-8")
    audit = dict(
                 n_tests=len(tests), n_formulas=len(selection), p_used="raw two-sided Wilcoxon", alpha=0.05,
                 best_rule="zero significant losses, then minimum pooled mean EXAM",
                 worst_rule="zero significant wins, then maximum pooled mean EXAM",
                 exact_mean_ties="retain all tied configurations", 
                 best_changes=sum(r["best"] != old_means[r["formula"]]["best"] for r in selection),
                 worst_changes=sum(r["worst"] != old_means[r["formula"]]["worst"] for r in selection),
                 rows_changed=len(changes), table12_modified=False)
    (OUT / "audit.json").write_text(json.dumps(audit, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
