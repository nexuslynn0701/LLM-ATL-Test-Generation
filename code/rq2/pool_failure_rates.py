"""Pool killed source-mutant pairs and verify the released numeric anchors."""
import csv

from decimal import Decimal, ROUND_HALF_UP

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SRC = ROOT / "results/experiment_results/RQ2/failure_rates.csv"

POOLED_CSV = ROOT / "results/rq2/supplementary/failure_rate_overall_pooled.csv"

SUBJECTS = ["Ant2Maven", "BibTeX2DocBook", "CPL2SPL", "Ecore2Maude",
            "Grafcet2PetriNet", "UML2ER"]

COMPUTABLE = {"OK", "OK_STRICT_CANONICAL"}

ROWS = [(ap, disp, pc, f"{ap}-{pc}")
        for ap, disp in (("GPT", "GPT"), ("Qwen", "Qwen"), ("DeepSeek-Flash", "DeepSeek"))
        for pc in ("SM", "STM", "ASTM", "ASTMO")]

ROWS += [("Yekta-ACO", "Yekta-ACO", "—", "Yekta-ACO")]

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
