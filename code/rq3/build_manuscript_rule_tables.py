"""Supplementary all-11 significance selection with a mean EXAM fallback.

All internal and baseline comparisons use raw two-sided Wilcoxon p < .05.
This supplementary selection rule is distinct from the descriptive mean table.
"""
import json
from collections import Counter, defaultdict
from fractions import Fraction

import apply_yekta_canonical_population as baseline
import build_strict_significance_selection as core

OUT = core.ROOT / "results/rq3/supplementary/manuscript_rule"


def pooled_means(rows):
    values = defaultdict(list)
    for row in rows:
        cell = (row["provider"], row["condition"])
        if row["evaluable"] != "1" or cell not in core.CELLS:
            continue
        denominator = 2 * int(row["rule_count"]) * int(row["n_faulty_rules"])
        raw = Fraction(row["exam_ac"])
        exact = Fraction(round(raw * denominator), denominator)
        assert abs(raw - exact) <= Fraction(1, 10**10)
        values[(row["formula"], core.label(cell))].append(exact)
    return {key: sum(v, Fraction(0)) / len(v) for key, v in values.items()}


def pick(formula, tests, means):
    labels = [core.label(c) for c in core.CELLS]
    wins, losses = Counter(), Counter()
    for row in tests:
        if row["formula"] != formula or row["p_raw"] >= .05:
            continue
        if row["A12_a"] > .5:
            winner, loser = row["cell_a"], row["cell_b"]
        elif row["A12_a"] < .5:
            winner, loser = row["cell_b"], row["cell_a"]
        else:
            continue
        wins[winner] += 1
        losses[loser] += 1
    best = [c for c in labels if wins[c] == 11]
    worst = [c for c in labels if losses[c] == 11]
    assert len(best) <= 1 and len(worst) <= 1
    reason_best = "significantly_better_than_all_11" if best else "minimum_pooled_mean_fallback"
    reason_worst = "significantly_worse_than_all_11" if worst else "maximum_pooled_mean_fallback"
    if not best:
        minimum = min(means[formula, c] for c in labels)
        best = [c for c in labels if means[formula, c] == minimum]
    if not worst:
        maximum = max(means[formula, c] for c in labels)
        worst = [c for c in labels if means[formula, c] == maximum]
    return dict(formula=formula, best=" / ".join(best), worst=" / ".join(worst),
                best_reason=reason_best, worst_reason=reason_worst,
                best_mean_exam=float(means[formula, best[0]]),
                worst_mean_exam=float(means[formula, worst[0]]),
                significant_internal_pairs=sum(r["formula"] == formula and
                                               r["p_raw"] < .05 for r in tests))


def latex(caption, label, columns, heading, rows, note):
    lines = [r"\begin{table}[t]", r"\centering", r"\caption{"+caption+"}",
             r"\label{"+label+"}", r"\begin{tabular}{"+columns+"}", r"\hline"]
    lines.extend(heading)
    lines.append(r"\hline")
    lines.extend(" & ".join(row) + r" \\" for row in rows)
    lines.extend([r"\hline", r"\end{tabular}", r"\par\smallskip",
                  r"\begin{minipage}{\linewidth}\footnotesize "+note,
                  r"\end{minipage}", r"\end{table}"])
    return "\n".join(lines)+"\n"


def main():
    rows = core.read(core.SOURCE)
    means = pooled_means(rows)
    internal = core.compute_tests()
    selection = [pick(f, internal, means) for f, _ in core.FORMULAS]
    baseline_tests = baseline.pairwise_tests(rows)
    counts = baseline.counts_of(baseline_tests)
    assert len(internal) == 1188 and len(baseline_tests) == 216
    assert all(r["significant_internal_pairs"] > 0 for r in selection)

    previous_counts = core.read(core.ROOT / "results/rq3/data/rq3_pairwise_counts.csv")
    assert counts == [{k: int(v) if k != "formula" else v for k, v in r.items()}
                      for r in previous_counts]

    OUT.mkdir(parents=True, exist_ok=True)
    core.TABLES.mkdir(parents=True, exist_ok=True)
    for name, data in [("table11_selection.csv", selection), ("table12_counts.csv", counts),
                       ("llm_internal_pairwise_tests.csv", internal),
                       ("baseline_pairwise_tests.csv", baseline_tests)]:
        core.write(OUT / name, data)
    rows11 = [[name, r["best"], r["worst"]] for (_, name), r in zip(core.FORMULAS, selection)]
    fields12 = [b+"_"+c for b in ["Yekta-ACO"]
                for c in ["Worse", "Similar", "Better"]]
    rows12 = [[name]+[str(r[k]) for k in fields12]
              for (_, name), r in zip(core.FORMULAS, counts)]
    note11 = ("Two-sided paired Wilcoxon tests use raw $p<0.05$ and $A_{12}$ for direction. "
              "A suite must beat/lose to all other 11 suites to qualify; otherwise select the "
              "lowest/highest pooled mean EXAM among all 12 suites.")
    note12 = ("Two-sided paired Wilcoxon tests use common evaluable mutants and raw $p<0.05$. "
              "$A_{12}>0.5$ favors the LLM; $A_{12}<0.5$ favors the baseline.")
    (core.TABLES / "table11_manuscript_rule.tex").write_text(latex(
        "Best and worst LLM-generated test suites selected using pairwise tests with a mean EXAM fallback.",
        "tab:rq3bw-selection", "lll", [r"Formula & Best cell & Worst cell \\"], rows11, note11),
        encoding="utf-8")
    (core.TABLES / "table12_manuscript_rule.tex").write_text(latex(
        "Statistical comparison of 12 LLM-generated test suites with the baselines.",
        "tab:rq3bw-pairwise-counts", "lrrr",
        [r" & \multicolumn{3}{c}{vs Yekta-ACO} \\",
         r"\cline{2-4}",
         r"Formula & Worse & Similar & Better \\"], rows12, note12),
        encoding="utf-8")
    md = ["# RQ3 supplementary all-11 selection with mean fallback", "",
          "Internal and baseline tests use raw p < 0.05.",
          "Selection requires 11 significant wins/losses; otherwise pooled mean EXAM is used.", "",
          "## Selection", "", "| Formula | Best cell | Worst cell |", "|---|---|---|"]
    md.extend("| " + " | ".join(r) + " |" for r in rows11)
    md.extend(["", "## Table 12", "",
               "| Formula | Yekta Worse | Yekta Similar | Yekta Better |",
               "|---|---:|---:|---:|"])
    md.extend("| " + " | ".join(r) + " |" for r in rows12)
    (OUT / "TABLES.md").write_text("\n".join(md)+"\n", encoding="utf-8")
    audit = dict(
                 internal_tests=1188, baseline_tests=216, p_used="raw two-sided Wilcoxon", alpha=0.05,
                 n_formulas=18,
                 n_best_significance_winners=sum(r["best_reason"] == "significantly_better_than_all_11"
                                                 for r in selection),
                 n_worst_significance_winners=sum(r["worst_reason"] == "significantly_worse_than_all_11"
                                                  for r in selection),
                 n_formulas_with_partial_significant_differences=sum(r["significant_internal_pairs"] > 0
                                                                   for r in selection),
                 table12_matches_current_counts=True)
    (OUT / "audit.json").write_text(json.dumps(audit, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
