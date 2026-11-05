"""Regenerate paper Table 8 (average failure rates of generated test suites)
and its pair-pooled Overall CSV from the released per-subject data.

Rebuilds both released artifacts from
``results/rq2/data/failure_rate_summary.csv``:
- ``results/rq2/data/failure_rate_overall_pooled.csv``
- ``results/rq2/tables/table_rq2_failure_rate.tex``

Conventions locked with the author:
- Per-subject cell = formula (5): the mean per-mutant fail ratio over the
  subject's eligible mutants, where a mutant's fail ratio is the fraction of
  its test models (paired with executable original sources only) that killed
  it. Display rounding is half-up, the project-wide locked convention.
- Overall column = pair-level pooled across subjects:
  sum(killed pairs) / sum(eligible mutants x executable sources) * 100.
- Qwen x CPL2SPL generated no executable source models: the failure rate is
  undefined (0/0), displayed 0.00 with a dagger, and the subject is excluded
  from Qwen's Overall as a neutral exclusion (unlike Table 6, where the
  measured 0/50 zero counts toward the pool).
- Subjects the ACO tool does not support show N/A; Yekta-ACO pools over its
  3 available subjects (10,600 pairs).
- Every pooled row recomputed from the summary is verified against the
  released counts before anything is written, so a drifted source fails
  loudly instead of silently regenerating a wrong table.

Usage:
    python regenerate_table8_failure_rate.py           # verify + print table to stdout
    python regenerate_table8_failure_rate.py --write   # rewrite both artifacts
"""
import argparse
import csv
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "results/rq2/data/failure_rate_summary.csv"
POOLED_CSV = ROOT / "results/rq2/data/failure_rate_overall_pooled.csv"
TABLE_TEX = ROOT / "results/rq2/tables/table_rq2_failure_rate.tex"

SUBJECTS = ["Ant2Maven", "BibTeX2DocBook", "CPL2SPL", "Ecore2Maude",
            "Grafcet2PetriNet", "UML2ER"]
COMPUTABLE = {"OK", "OK_STRICT_CANONICAL"}

# (approach key in the CSV, display name, prompt condition, pooled-CSV method_id)
ROWS = [(ap, disp, pc, f"{ap}-{pc}")
        for ap, disp in (("GPT", "GPT"), ("Qwen", "Qwen"), ("DeepSeek-Flash", "DeepSeek"))
        for pc in ("SM", "STM", "ASTM", "ASTMO")]
ROWS += [("Yekta-ACO", "Yekta-ACO", "—", "Yekta-ACO")]

# method_id -> released (pooled total pairs, pooled killed pairs, subjects); drift anchors.
EXPECTED = {
    "GPT-SM": (22782, 10965, 6), "GPT-STM": (21770, 10183, 6),
    "GPT-ASTM": (22270, 12920, 6), "GPT-ASTMO": (22650, 12617, 6),
    "Qwen-SM": (18700, 8456, 5), "Qwen-STM": (20240, 9583, 5),
    "Qwen-ASTM": (17060, 10309, 5), "Qwen-ASTMO": (23100, 12371, 5),
    "DeepSeek-Flash-SM": (22464, 11246, 6), "DeepSeek-Flash-STM": (23000, 11700, 6),
    "DeepSeek-Flash-ASTM": (19264, 11000, 6), "DeepSeek-Flash-ASTMO": (18668, 10900, 6),
    "Yekta-ACO": (10600, 5009, 3),
}


def fmt(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):.2f}"


def load_summary() -> dict:
    with SRC.open(encoding="utf-8", newline="") as handle:
        return {(r["subject"], r["method_id"]): r
                for r in csv.DictReader(handle)}


def pool(summary: dict, method_id: str) -> dict:
    total = killed = 0
    included = 0
    no_exec = []
    for subject in SUBJECTS:
        row = summary.get((subject, method_id))
        if row is None or row["status"] not in COMPUTABLE:
            if row is not None and row["status"] == "NO_EXECUTABLE":
                no_exec.append(subject)
            continue
        pairs = int(row["n_eligible_mutants"]) * int(row["n_original_executable_sources"])
        total += pairs
        killed += Decimal(row["mean_fail_ratio_pct"]) / 100 * pairs
        included += 1
    return {"total": total, "killed": round(killed), "included": included,
            "no_exec": no_exec}


def verify(pools: dict) -> None:
    for method_id, expected in EXPECTED.items():
        got = (pools[method_id]["total"], pools[method_id]["killed"],
               pools[method_id]["included"])
        if got != expected:
            raise SystemExit(f"FAIL {method_id}: summary pools to {got}, "
                             f"released CSV expects {expected}")


def cell(summary: dict, method_id: str, subject: str) -> str:
    row = summary.get((subject, method_id))
    if row is None or row["status"] not in COMPUTABLE:
        if row is not None and row["status"] == "NO_EXECUTABLE":
            return "0.00$^{\\dagger}$"
        return "N/A"
    return fmt(Decimal(row["mean_fail_ratio_pct"]))


def render_tex(summary: dict, pools: dict) -> str:
    zero = pools["Qwen-SM"]["no_exec"][0]
    lines = [
        "% Table 8 (failure rates) — per-subject cell = formula (5): mean per-mutant fail",
        "% ratio over the subject's eligible mutants (test models paired with executable",
        "% original sources only). Overall column: pair-level pooled across subjects,",
        "% Overall = sum(killed pairs) / sum(eligible mutants x executable sources) * 100,",
        "% rounded half-up to two decimals.",
        f"% Denominators: GPT / Qwen / DeepSeek pool over {'six' if pools['GPT-SM']['included'] == 6 else pools['GPT-SM']['included']} subjects; Qwen excludes {zero} (0/0, neutral).",
        f"% Yekta-ACO pools over its {pools['Yekta-ACO']['included']} available subjects ({pools['Yekta-ACO']['total']:,} pairs).",
        "% Counts per row: results/rq2/data/failure_rate_overall_pooled.csv",
        "% Regenerated by code/rq2/regenerate_table8_failure_rate.py.",
        r"\begin{table}[t]",
        r"\centering",
        r"\caption{Average failure rates (\%) of test suites generated by different approaches.}",
        r"\label{tab:rq2-failure-rate}",
        r"\setlength{\tabcolsep}{3pt}",
        r"\begin{tabular}{lcccccccc}",
        r"\toprule",
        r"\textbf{Approach} & \textbf{Prompt} & "
        + " & ".join(rf"\textbf{{{s}}}" for s in SUBJECTS)
        + r" & \textbf{Overall}\\",
        r"\midrule",
    ]
    for index, (approach, display, prompt, method_id) in enumerate(ROWS):
        values = [cell(summary, method_id, s) for s in SUBJECTS]
        current = pools[method_id]
        values.append(fmt(Decimal(current["killed"]) * 100 / Decimal(current["total"])))
        if prompt in ("SM", "STM", "ASTM", "ASTMO"):
            if index % 4 == 0:
                lines.append(rf"\multirow{{4}}{{*}}{{\textbf{{{display}}}}}")
            lines.append(f"  & {prompt} & " + " & ".join(values) + r" \\")
        else:
            lines.append(rf"\textbf{{{display}}} & -- & " + " & ".join(values) + r" \\")
        if index % 4 == 3 and index < len(ROWS) - 2:
            lines.append(r"\midrule")
    lines.append(r"\bottomrule")
    lines.append(
        r"\multicolumn{9}{p{0.98\linewidth}}{\footnotesize $^{\dagger}$Qwen generated no "
        rf"executable source models on {zero}, so its failure rate there is undefined (0/0); "
        rf"the subject is excluded from Qwen's Overall.}}")
    lines += [r"\end{tabular}", r"\end{table}", ""]
    return "\n".join(lines)


def pooled_csv_rows(pools: dict) -> list[dict]:
    rows = []
    for _, _, _, method_id in ROWS:
        current = pools[method_id]
        rows.append({
            "method_id": method_id,
            "overall_pooled_pairs_pct":
                fmt(Decimal(current["killed"]) * 100 / Decimal(current["total"])),
            "pooled_total_pairs": current["total"],
            "pooled_killed_pairs": current["killed"],
            "subjects_included": current["included"],
            "no_executable_cell_handling":
                "excluded (0/0, neutral)" if current["no_exec"] else "n/a",
        })
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true",
                        help="rewrite the pooled CSV and the LaTeX table (default: stdout preview)")
    args = parser.parse_args()

    summary = load_summary()
    pools = {method_id: pool(summary, method_id) for _, _, _, method_id in ROWS}
    verify(pools)
    tex = render_tex(summary, pools)
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
