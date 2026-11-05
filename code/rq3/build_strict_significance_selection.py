"""Build Table 11 using significant wins/losses against all 11 alternatives.

Run from any directory: python code/rq3/build_strict_significance_selection.py
Inputs are read-only. All 1,188 LLM-internal tests use raw p < .05.
This supplementary all-11 selection has no mean-based fallback.
"""
import csv
import itertools
import json
from collections import defaultdict
from pathlib import Path

import scipy
from scipy.stats import mannwhitneyu, wilcoxon

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "results/rq3/data/mutant_level_exam.csv"
OUT = ROOT / "results/rq3/supplementary/strict_significance"
TABLES = ROOT / "results/rq3/tables"
CELLS = [(p, c) for p in ["GPT", "Qwen", "DeepSeek"]
         for c in ["sm", "stm", "astm", "astmo"]]
FORMULAS = [
    ("ochiai", "Ochiai"), ("tarantula", "Tarantula"), ("dstar2", "DStar2"),
    ("kulczynski2", "Kulczynski2"), ("mountford", "Mountford"), ("zoltar", "Zoltar"),
    ("arithmetic_mean", "ArithmeticMean"), ("barinel", "Barinel"),
    ("braun_banquet", "BraunBanquet"), ("baroni_urbani_buser", "BaroniUrbaniBuser"),
    ("cohen", "Cohen"), ("ochiai2", "Ochiai2"), ("op2", "OP2"), ("phi", "Phi"),
    ("pierce", "Pierce"), ("rogers_tanimoto", "RogersTanimoto"),
    ("russell_rao", "RussellRao"), ("simple_matching", "SimpleMatching"),
]


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def write(path, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def label(cell):
    return cell[0] + "-" + cell[1].upper()


def select(tests, p_field):
    selections, evidence = [], []
    for formula, _ in FORMULAS:
        wins = dict.fromkeys(map(label, CELLS), 0)
        losses = dict.fromkeys(wins, 0)
        compared = dict.fromkeys(wins, 0)
        for row in tests:
            if row["formula"] != formula:
                continue
            a, b = row["cell_a"], row["cell_b"]
            compared[a] += 1
            compared[b] += 1
            if row[p_field] < 0.05 and row["A12_a"] != 0.5:
                winner, loser = (a, b) if row["A12_a"] > 0.5 else (b, a)
                wins[winner] += 1
                losses[loser] += 1
        assert all(n == 11 for n in compared.values())
        best = [c for c in wins if wins[c] == 11]
        worst = [c for c in wins if losses[c] == 11]
        assert len(best) <= 1 and len(worst) <= 1
        selections.append(dict(formula=formula, best=best[0] if best else "None",
                               worst=worst[0] if worst else "None"))
        for cell in wins:
            evidence.append(dict(formula=formula, cell=cell,
                                 significant_wins=wins[cell], significant_losses=losses[cell],
                                 other_comparisons=11-wins[cell]-losses[cell],
                                 qualifies_best=int(wins[cell] == 11),
                                 qualifies_worst=int(losses[cell] == 11)))
    return selections, evidence


def compute_tests():
    grid = defaultdict(dict)
    for row in read(SOURCE):
        cell = (row["provider"], row["condition"])
        if row["evaluable"] != "1" or cell not in CELLS:
            continue
        key = (row["formula"], label(cell))
        mutant = (row["subject"], row["mutant_id"])
        assert mutant not in grid[key], (key, mutant)
        grid[key][mutant] = float(row["exam_ac"])
    tests = []
    for formula, _ in FORMULAS:
        for ca, cb in itertools.combinations(CELLS, 2):
            x, y = grid[(formula, label(ca))], grid[(formula, label(cb))]
            keys = sorted(x.keys() & y.keys())
            assert keys, (formula, ca, cb)
            a, b = [x[k] for k in keys], [y[k] for k in keys]
            p = 1.0 if a == b else float(wilcoxon(
                a, b, zero_method="wilcox", alternative="two-sided", method="auto").pvalue)
            effect = 1.0 - float(mannwhitneyu(a, b, alternative="two-sided").statistic) / len(a)**2
            tests.append(dict(formula=formula, cell_a=label(ca), cell_b=label(cb),
                              n_common=len(keys), n_nonzero=sum(i != j for i, j in zip(a, b)),
                              p_raw=p, A12_a=effect,
                              mean_difference=sum(i-j for i, j in zip(a, b))/len(a)))
    assert len(tests) == 1188

    # Independent regression evidence: previously published internal-pair audit.
    previous_path = ROOT / "results/shared/audits/mutant47_rebuild/rq3_llm_internal_tests_supplementary.csv"
    previous = {(r["formula"], r["cell_a"], r["cell_b"]): r for r in read(previous_path)}
    assert len(previous) == len(tests)
    for row in tests:
        old = previous[(row["formula"], row["cell_a"], row["cell_b"])]
        for field in ["n_common", "p_raw", "A12_a"]:
            assert abs(row[field] - float(old[field])) < 1e-12, (row, field)

    return tests


def main():
    tests = compute_tests()
    selection, evidence = select(tests, "p_raw")
    OUT.mkdir(parents=True, exist_ok=True)
    TABLES.mkdir(parents=True, exist_ok=True)
    write(OUT / "llm_internal_pairwise_tests.csv", tests)
    write(OUT / "configuration_win_loss_counts.csv", evidence)
    write(OUT / "table11_strict_selection.csv", selection)

    caption = ("LLM-generated test suites with significantly lower or higher EXAM scores "
               "than all other 11 LLM configurations under each SBFL formula.")
    note = ("Each comparison uses EXAM scores on mutants killed by both configurations. "
            "Two-sided paired Wilcoxon signed-rank tests use raw p-values. "
            "A configuration qualifies as best (worst) only if all 11 comparisons "
            "have raw p < 0.05 and A12 favors that configuration (its opponent). "
            "None indicates that no configuration meets this criterion; it does not establish "
            "equivalence. No mean-based fallback is applied.")
    tex = [r"\begin{table}[t]", r"\centering", r"\caption{" + caption + "}",
           r"\label{tab:rq3bw-selection}", r"\begin{tabular}{lll}", r"\hline",
           r"Formula & Best cell & Worst cell \\", r"\hline"]
    for (_, name), row in zip(FORMULAS, selection):
        tex.append(f"{name} & {row['best']} & {row['worst']} " + r"\\")
    tex.extend([r"\hline", r"\end{tabular}", r"\par\smallskip",
                r"\begin{minipage}{\linewidth}\footnotesize " +
                note.replace("p < 0.05", r"$p<0.05$").replace("A12", r"$A_{12}$"),
                r"\end{minipage}", r"\end{table}"])
    (TABLES / "table11_strict_significance.tex").write_text("\n".join(tex)+"\n", encoding="utf-8")
    md = ["Table 11. " + caption, "", "| Formula | Best cell | Worst cell |",
          "|---|---|---|"]
    md.extend(f"| {name} | {r['best']} | {r['worst']} |" for (_, name), r in zip(FORMULAS, selection))
    md.extend(["", note, "", "中文说明：无配置满足严格标准时标注 None（无）。均值排序不再用于此表。",
               "全部检验使用原始p < 0.05。"])
    (OUT / "TABLE11.md").write_text("\n".join(md)+"\n", encoding="utf-8")
    audit = dict(source=str(SOURCE.relative_to(ROOT)),
                 
                 scipy_version=scipy.__version__, n_tests=len(tests),
                 p_used="raw two-sided Wilcoxon", alpha=0.05,
                 required_wins_or_losses=11, mean_fallback=False,
                 prior_internal_audit_matches=True,
                 n_formulas_with_best=sum(r["best"] != "None" for r in selection),
                 n_formulas_with_worst=sum(r["worst"] != "None" for r in selection),
                 table12_modified=False)
    (OUT / "audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
