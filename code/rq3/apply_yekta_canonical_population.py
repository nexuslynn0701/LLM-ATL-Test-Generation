"""RQ3 pooling, raw-p tests and ACO baseline exports.

ACO localization is recomputed from canonical RQ2 pair outcomes and original
per-source coverage by build_aco_canonical_localization.py. Both the evaluable
flags and all rankings/EXAM values follow that shared oracle. KILLED/ALIVE
are failing/passing tests; invalid executions do not enter SBFL counts.

Run code/reproduction/build_tables.py --only rq3 to verify this protocol.
"""
import argparse
import csv
import io
import json
from collections import defaultdict
from decimal import Decimal, localcontext, ROUND_HALF_EVEN
from fractions import Fraction as F
from pathlib import Path
from statistics import median

from scipy.stats import wilcoxon, mannwhitneyu

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "results/rq3/data"
SUP = ROOT / "results/rq3/supplementary"
KILL_MATRIX = ROOT / "results/rq2/supplementary/mutant_kill_matrix.csv"
EXAM_CSV = DATA / "mutant_level_exam.csv"

P = ["GPT", "Qwen", "DeepSeek"]
C = ["sm", "stm", "astm", "astmo"]
CONFIGS = [(p, c) for p in P for c in C] + [("Yekta-ACO", "aco")]
N = ["ochiai", "tarantula", "dstar2", "kulczynski2", "mountford", "zoltar",
     "arithmetic_mean", "barinel", "braun_banquet", "baroni_urbani_buser",
     "cohen", "ochiai2", "op2", "phi", "pierce", "rogers_tanimoto",
     "russell_rao", "simple_matching"]

EXPECTED_KILLED = {"BibTeX2DocBook": 32, "CPL2SPL": 50, "UML2ER": 13}  # Table 6 / 95


def read(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def render_csv(rows, fields):
    buf = io.StringIO(newline="")
    w = csv.DictWriter(buf, fieldnames=fields)
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def fmt(x, n=15):
    with localcontext() as c:
        c.prec = 60
        return str((Decimal(x.numerator) / Decimal(x.denominator))
                   .quantize(Decimal(1).scaleb(-n), rounding=ROUND_HALF_EVEN))


def mean(xs):
    return sum(xs, F(0)) / len(xs)


def quantile(vals, q):
    vals = sorted(vals)
    idx = (len(vals) - 1) * q
    i = idx.numerator // idx.denominator
    rem = idx - i
    return vals[i] * (1 - rem) + vals[min(i + 1, len(vals) - 1)] * rem


def grid(r, name="exam_ac"):
    d = 2 * int(r["rule_count"]) * int(r["n_faulty_rules"])
    v = F(r[name])
    x = F(round(v * d), d)
    assert abs(v - x) <= F(1, 10**10)
    return x




# ---------------------------------------------------------------- steps
def derive_excluded(rows):
    """Yekta rows present in the FL data minus the canonical killed set."""
    covered = defaultdict(set)
    for r in rows:
        if r["provider"] == "Yekta-ACO":
            covered[r["subject"]].add(r["mutant_id"])
    killed = defaultdict(set)
    for r in read(KILL_MATRIX):
        if r["killed_Yekta-ACO"] in ("1", "1.0"):
            killed[r["subject"]].add(r["mutant_id"])
    assert {s: len(v) for s, v in killed.items()} == EXPECTED_KILLED, \
        f"kill matrix disagrees with Table 6: {{s: len(v) for s, v in killed.items()}}"
    for s, k in killed.items():
        assert k <= covered[s], f"killed mutants absent from FL data: {s}"
    excluded = {s: covered[s] - killed[s] for s in covered}
    assert {s: len(v) for s, v in killed.items()} | {} == EXPECTED_KILLED
    counts = {s: len(v) for s, v in excluded.items() if v}
    assert counts == {"BibTeX2DocBook": 8, "UML2ER": 5}, f"unexpected exclusion set: {counts}"
    return excluded, killed


def pool_of(rows):
    pool = defaultdict(list)
    for r in rows:
        if r["evaluable"] == "1":
            pool[(r["provider"], r["condition"], r["formula"])].append(r)
    return pool


def pooled_tables(pool):
    """Recompute rq3_top1_pooled / rq3_exam_pooled exactly as compute_top1_pooled.py."""
    toprows, examrows = [], []
    for f in N:
        t = dict(formula=f)
        ex = dict(formula=f)
        for p, c in CONFIGS:
            rs = pool[(p, c, f)]
            key = f"{p}-{c.upper()}"
            t[key] = fmt(100 * mean([F(int(F(r["best_rank"]) <= 1)) for r in rs]))
            vv = [grid(r) for r in rs]
            ex[key + "_mean"] = fmt(mean(vv))
            ex[key + "_median"] = fmt(median(vv))
            ex[key + "_n"] = len(rs)
        toprows.append(t)
        examrows.append(ex)
    return toprows, examrows


def pairwise_tests(rows):
    """Paired Wilcoxon raw p-values and A12 on common evaluable mutants."""
    gg = defaultdict(dict)
    for r in rows:
        if r["evaluable"] == "1":
            gg[(r["provider"], r["condition"], r["formula"])][(r["subject"], r["mutant_id"])] = float(r["exam_ac"])
    out = []
    for p in P:
        for c in C:
            for f in N:
                x = gg[(p, c, f)]
                for b, bc in [("Yekta-ACO", "aco")]:
                    y = gg[(b, bc, f)]
                    ks = sorted(x.keys() & y.keys())
                    a = [x[k] for k in ks]
                    bb = [y[k] for k in ks]
                    pv = 1. if all(i == j for i, j in zip(a, bb)) else float(
                        wilcoxon(a, bb, zero_method="wilcox", alternative="two-sided", method="auto").pvalue)
                    eff = 1 - float(mannwhitneyu(a, bb, alternative="two-sided").statistic) / (len(a) * len(bb))
                    out.append(dict(provider=p, condition=c, formula=f, baseline=b, n_common=len(ks),
                                    p_raw=pv, A12=eff,
                                    mean_difference=sum(i - j for i, j in zip(a, bb)) / len(a)))
    for r in out:
        r["classification"] = "Similar" if r["p_raw"] >= .05 else "Better" if r["A12"] > .5 else "Worse"
    return out


def counts_of(tests):
    out = []
    for f in N:
        r = dict(formula=f)
        for b in ["Yekta-ACO"]:
            for label in ["Worse", "Similar", "Better"]:
                r[b + "_" + label] = sum(t["formula"] == f and t["baseline"] == b
                                         and t["classification"] == label for t in tests)
        out.append(r)
    return out


def cell_scores(rows, old_cells):
    """Recompute cell_formula_scores rows; source_count carried from the released file."""
    src = {(r["subject"], r["provider"], r["condition"]): r["source_count"] for r in old_cells}
    cells = defaultdict(list)
    for r in rows:
        cells[(r["subject"], r["provider"], r["condition"], r["formula"])].append(r)
    cellrows = []
    for key, rs in sorted(cells.items()):
        sub, p, c, f = key
        e = [r for r in rs if r["evaluable"] == "1"]
        r = dict(subject=sub, provider=p, condition=c, cell_kind=rs[0]["cell_kind"], formula=f,
                 source_count=src[key[:3]], distinct_mutants=len(rs), killed_mutants=len(e),
                 faulty_rule_observations=sum(int(r["n_faulty_rules"]) for r in rs),
                 evaluable_observations=sum(int(r["n_faulty_rules"]) for r in e))
        for name in ["bc", "ac", "wc"]:
            vals = [grid(x, "exam_" + name) for x in e]
            for agg, v in [("mean", mean(vals) if vals else None),
                           ("median", median(vals) if vals else None),
                           ("q25", quantile(vals, F(1, 4)) if vals else None),
                           ("q75", quantile(vals, F(3, 4)) if vals else None)]:
                r[agg + "_exam_" + name] = fmt(v) if v is not None else "NA"
        for k in [1, 3, 5]:
            r["top" + str(k) + "_rate"] = fmt(mean([F(int(F(x["best_rank"]) <= k)) for x in e])) if e else "NA"
        r["median_tie_size"] = fmt(median([F(x["tie_size"]) for x in e])) if e else "NA"
        r["median_rule_count"] = fmt(median([F(x["rule_count"]) for x in e])) if e else "NA"
        cellrows.append(r)
    return cellrows


def baseline_columns(examrows, rows):
    """Regenerate results/rq3/supplementary/rq3_baseline_columns/ (export_rq3_baseline_exam.py format)."""
    g = defaultdict(list)
    counts = defaultdict(set)
    for r in rows:
        if r["provider"] not in ["Yekta-ACO"] or r["evaluable"] != "1":
            continue
        g[r["provider"], r["formula"]].append(grid(r))
        counts[r["provider"], r["subject"]].add(r["mutant_id"])
    prior = {(r["formula"]): r for r in examrows}
    names = ["Ochiai", "Tarantula", "DStar2", "Kulczynski2", "Mountford", "Zoltar",
             "ArithmeticMean", "Barinel", "BraunBanquet", "BaroniUrbaniBuser", "Cohen",
             "Ochiai2", "OP2", "Phi", "Pierce", "RogersTanimoto", "RussellRao", "SimpleMatching"]
    long_rows, wide = [], []
    for name, f in zip(names, N):
        row = {"Formula": name}
        pr = prior[f]
        for p, suffix in [("Yekta-ACO", "ACO")]:
            v = g[p, f]
            a = sum(v, F(0)) / len(v)
            b = median(v)
            k = f"{p}-{suffix}"
            assert len(v) == int(pr[k + "_n"]) and abs(a - F(pr[k + "_mean"])) < F(1, 10**14) \
                and abs(b - F(pr[k + "_median"])) < F(1, 10**14), f"baseline/pooled mismatch {p}/{f}"
            long_rows.append(dict(formula=f, baseline=p, n_mutants=len(v),
                                  mean_15dp=fmt(a, 15), median_15dp=fmt(b, 15),
                                  mean_numerator=a.numerator, mean_denominator=a.denominator,
                                  median_numerator=b.numerator, median_denominator=b.denominator,
                                  display_mean=fmt(a, 2), display_median=fmt(b, 2)))
            row[p] = fmt(a, 2) + "/" + fmt(b, 2)
        wide.append(row)
    pop = [dict(baseline=p, subject=s, n_evaluable=len(v)) for (p, s), v in sorted(counts.items())]
    tex = ["% Formula & Yekta-ACO mean/median",
           "% Pooled evaluable mutants; exact rank-grid EXAM; ROUND_HALF_EVEN.",
           "% Yekta-ACO uses canonical pair outcomes for all 95 evaluable mutants; see",
           "% code/rq3/build_aco_canonical_localization.py; old rankings are not retained."]
    tex += [" & ".join(r.values()) + r" \\" for r in wide]
    audit = dict(status="PASS", baseline_formula_groups=len(long_rows),
                 matches_rebuilt_pooled_summary=True,
                 Yekta_ACO_n=len(g["Yekta-ACO", "ochiai"]),
                 population_basis="canonical RQ2 pair outcomes and original source-rule coverage; rankings fully recomputed",
                 manuscript_modified=False)
    return long_rows, wide, pop, "\n".join(tex) + "\n", audit


def main():
    """Verify/rebuild current 13-configuration, 216-comparison summaries."""
    import subprocess, sys
    args = [sys.executable, str(ROOT/'code/reproduction/build_tables.py'), '--only', 'rq3']
    raise SystemExit(subprocess.run(args).returncode)

if __name__ == '__main__':
    main()
