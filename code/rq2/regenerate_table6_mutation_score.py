"""Regenerate paper Table 6 (mutation scores of generated test models) and its
pooled-counts CSV from the released per-subject data.

Rebuilds both released artifacts from ``results/rq2/data/mutation_score.csv``:
- ``results/rq2/data/mutation_score_overall_pooled.csv``
- ``results/rq2/tables/table_rq2_suite_mutation_score.tex``

Conventions locked with the author:
- Overall = sum(killed) / sum(eligible_mutants) * 100 across subjects with a
  measured outcome, rounded half-up to two decimals (never banker's rounding,
  e.g. DeepSeek-STM 189/288 = 65.625 must print 65.63).
- Qwen x CPL2SPL generated no executable source models: its 0/50 is a measured
  zero that counts toward Qwen's Overall ("not killed = undetected") and is
  flagged with a dagger; the equal-weight reference without it is kept in the
  pooled CSV only.
- Subjects marked N/A (ACO Ant2Maven/Ecore2Maude/Grafcet2PetriNet) are excluded
  from cells and pools, so Yekta-ACO pools over 3 subjects (108 eligible).
- Every pooled (killed, eligible) pair is verified against the released values
  before anything is written, so a drifted source fails loudly instead of
  silently regenerating a wrong table.

Usage:
    python regenerate_table6_mutation_score.py           # verify + print table to stdout
    python regenerate_table6_mutation_score.py --write   # rewrite both artifacts
"""
import argparse
import csv
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "results/rq2/data/mutation_score.csv"
POOLED_CSV = ROOT / "results/rq2/data/mutation_score_overall_pooled.csv"
TABLE_TEX = ROOT / "results/rq2/tables/table_rq2_suite_mutation_score.tex"

SUBJECTS = ["Ant2Maven", "BibTeX2DocBook", "CPL2SPL", "Ecore2Maude",
            "Grafcet2PetriNet", "UML2ER"]

# (approach key in the CSV, display name, prompt condition, pooled-CSV method_id)
ROWS = [(ap, disp, pc, f"{ap}-{pc}")
        for ap, disp in (("GPT", "GPT"), ("Qwen", "Qwen"), ("DeepSeek-Flash", "DeepSeek"))
        for pc in ("SM", "STM", "ASTM", "ASTMO")]
ROWS += [("Yekta-ACO", "Yekta-ACO", "—", "Yekta-ACO")]

# method_id -> released (pooled killed, pooled eligible); drift anchors.
EXPECTED = {
    "GPT-SM": (190, 288), "GPT-STM": (182, 288), "GPT-ASTM": (210, 288), "GPT-ASTMO": (203, 288),
    "Qwen-SM": (144, 288), "Qwen-STM": (152, 288), "Qwen-ASTM": (160, 288), "Qwen-ASTMO": (147, 288),
    "DeepSeek-Flash-SM": (169, 288), "DeepSeek-Flash-STM": (189, 288),
    "DeepSeek-Flash-ASTM": (196, 288), "DeepSeek-Flash-ASTMO": (196, 288),
    "Yekta-ACO": (95, 108),
}


def pct(killed: int, eligible: int) -> Decimal:
    return Decimal(killed) * 100 / Decimal(eligible)


def fmt(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):.2f}"


def load_cells() -> dict:
    with SRC.open(encoding="utf-8", newline="") as handle:
        return {(r["approach"], r["prompt_condition"], r["subject"]): r
                for r in csv.DictReader(handle)}


def pool(cells: dict, approach: str, prompt: str) -> dict:
    killed = eligible = included = 0
    macro_sum = Decimal(0)
    excl_killed = excl_eligible = 0
    no_exec = []
    for subject in SUBJECTS:
        row = cells.get((approach, prompt, subject))
        if row is None or row["availability_status"] == "N/A":
            continue
        k, e = int(row["killed_mutants"]), int(row["eligible_mutants"])
        killed, eligible, included = killed + k, eligible + e, included + 1
        macro_sum += pct(k, e)
        if row["availability_status"] == "OK":
            excl_killed, excl_eligible = excl_killed + k, excl_eligible + e
        else:
            no_exec.append((subject, e))
    return {"killed": killed, "eligible": eligible, "included": included,
            "macro": macro_sum / included, "excl": (excl_killed, excl_eligible),
            "no_exec": no_exec}


def verify(pools: dict) -> None:
    for method_id, expected in EXPECTED.items():
        got = (pools[method_id]["killed"], pools[method_id]["eligible"])
        if got != expected:
            raise SystemExit(f"FAIL {method_id}: source pools to {got}, "
                             f"released table expects {expected}")


def cell(cells: dict, approach: str, prompt: str, subject: str) -> str:
    row = cells.get((approach, prompt, subject))
    if row is None or row["availability_status"] == "N/A":
        return "N/A"
    value = fmt(pct(int(row["killed_mutants"]), int(row["eligible_mutants"])))
    return value if row["availability_status"] == "OK" else value + r"$^{\dagger}$"


def render_tex(cells: dict, pools: dict) -> str:
    mutants_total = pools["GPT-SM"]["eligible"]
    zero = pools["Qwen-SM"]["no_exec"][0]
    header_cells = " & ".join(rf"\textbf{{{s}}}" for s in SUBJECTS)
    lines = [
        "% Table 6 (mutation scores) — Overall column: mutant-level pooled aggregation across subjects,",
        "% Overall = sum(killed) / sum(eligible_mutants) * 100, where eligible = canonical mutants",
        "% minus compile-failed/stillborn minus equivalent (all zero here).",
        f"% Denominators: GPT / Qwen / DeepSeek pool over all six subjects ({mutants_total} eligible mutants).",
        f"% Qwen's {zero[0]} zero (0/{zero[1]}, no executable source models generated) is a measured zero and",
        "% counts toward its Overall, per the \"not killed = undetected\" rule; only undefined 0/0 cases",
        "% (none here for mutation score; cf. Table 8 failure rate) are excluded.",
        f"% Yekta-ACO pools over its {pools['Yekta-ACO']['included']} available subjects ({pools['Yekta-ACO']['eligible']} eligible mutants).",
        "% Counts per row: results/rq2/data/mutation_score_overall_pooled.csv",
        "% Regenerated by code/rq2/regenerate_table6_mutation_score.py.",
        r"\begin{table}[t]",
        r"\centering",
        r"\caption{Mutation scores (\%) of generated test models.}",
        r"\label{tab:rq2-suite-mutation-score}",
        r"\setlength{\tabcolsep}{3pt}",
        r"\begin{tabular}{lcccccccc}",
        r"\toprule",
        rf"\textbf{{Approach}} & \textbf{{Prompt}} & {header_cells} & \textbf{{Overall}}\\",
        r"\midrule",
        r"\textbf{Mutants} & & "
        + " & ".join(str(int(cells[("GPT", "SM", s)]["eligible_mutants"])) for s in SUBJECTS)
        + rf" & {mutants_total} \\",
        r"\midrule",
    ]
    for index, (approach, display, prompt, method_id) in enumerate(ROWS):
        values = [cell(cells, approach, prompt, s) for s in SUBJECTS]
        current = pools[method_id]
        values.append(fmt(pct(current["killed"], current["eligible"])))
        if prompt in ("SM", "STM", "ASTM", "ASTMO"):
            if index % 4 == 0:
                lines.append(rf"\multirow{{4}}{{*}}{{\textbf{{{display}}}}}")
            lines.append(f"  & {prompt} & " + " & ".join(values) + r" \\")
        else:
            lines.append(rf"\textbf{{{display}}} & -- & " + " & ".join(values) + r" \\")
        if index % 4 == 3 and index < len(ROWS) - 2:
            lines.append(r"\midrule")
    lines.append(r"\bottomrule")
    if zero:
        lines.append(
            r"\multicolumn{9}{p{0.98\linewidth}}{\footnotesize $^{\dagger}$No executable source "
            rf"models were generated for Qwen on {zero[0]}, so none of its {zero[1]} mutants was "
            rf"killed; the 0/{zero[1]} outcome counts toward Qwen's Overall.}}")
    lines += [r"\end{tabular}", r"\end{table}", ""]
    return "\n".join(lines)


def pooled_csv_rows(pools: dict) -> list[dict]:
    rows = []
    for _, _, _, method_id in ROWS:
        current = pools[method_id]
        notes = ""
        if current["no_exec"]:
            subject, eligible = current["no_exec"][0]
            notes = (f"{subject} included: measured 0/{eligible} (not-killed = undetected); "
                     "excl-reference in last column")
        elif method_id == "Yekta-ACO":
            notes = "available subjects only (N/A subjects dropped)"
        rows.append({
            "method_id": method_id,
            "subjects_included": current["included"],
            "pooled_eligible_mutants": current["eligible"],
            "pooled_killed_mutants": current["killed"],
            "overall_macro_equal_weight_pct": fmt(current["macro"]),
            "overall_pooled_pct": fmt(pct(current["killed"], current["eligible"])),
            "pooled_excl_no_executable_subjects_reference_pct":
                fmt(pct(*current["excl"])) if current["no_exec"] else "",
            "notes": notes,
        })
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true",
                        help="rewrite the pooled CSV and the LaTeX table (default: stdout preview)")
    args = parser.parse_args()

    cells = load_cells()
    pools = {method_id: pool(cells, approach, prompt)
             for approach, _, prompt, method_id in ROWS}
    verify(pools)
    tex = render_tex(cells, pools)
    if not args.write:
        print(tex)
        print(f"[dry-run] all {len(EXPECTED)} pooled rows match the released values; "
              "rerun with --write to rewrite both artifacts.")
        return
    rows = pooled_csv_rows(pools)
    with POOLED_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\r\n")
        writer.writeheader()
        writer.writerows(rows)
    TABLE_TEX.write_text(tex, encoding="utf-8", newline="\n")
    print(f"Wrote {POOLED_CSV.relative_to(ROOT)}")
    print(f"Wrote {TABLE_TEX.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
