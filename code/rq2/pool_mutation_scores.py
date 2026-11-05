"""Pool mutation counts and verify the released numeric anchors."""
import csv

from decimal import Decimal, ROUND_HALF_UP

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SRC = ROOT / "results/experiment_results/RQ2/mutation_results.csv"

POOLED_CSV = ROOT / "results/rq2/supplementary/mutation_score_overall_pooled.csv"

SUBJECTS = ["Ant2Maven", "BibTeX2DocBook", "CPL2SPL", "Ecore2Maude",
            "Grafcet2PetriNet", "UML2ER"]

ROWS = [(ap, disp, pc, f"{ap}-{pc}")
        for ap, disp in (("GPT", "GPT"), ("Qwen", "Qwen"), ("DeepSeek-Flash", "DeepSeek"))
        for pc in ("SM", "STM", "ASTM", "ASTMO")]

ROWS += [("Yekta-ACO", "Yekta-ACO", "—", "Yekta-ACO")]

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
