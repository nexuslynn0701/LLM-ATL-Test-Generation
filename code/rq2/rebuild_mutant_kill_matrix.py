"""Rebuild the released mutant kill matrix from the pair-level inputs.

Reproduces ``results/experiment_results/RQ2/mutant_kill_matrix.csv`` from ``results/rq2/supplementary/inputs/``:

- LLM columns (GPT / Qwen / DeepSeek-Flash): prompt-pooled union — a mutant is
  1 if any pair from an original-executable source has outcome KILLED, else 0;
  blank when the provider has no original-executable source for the subject
  (Qwen x CPL2SPL: no executable source models, so no pairs at all).
- Yekta-ACO: canonical replay matrix (CPL2SPL/UML2ER from the estar evidence;
  BibTeX2DocBook from aco/source_mutant_outcomes_aco_canonical_bibtex.csv,
  which is pending re-export — see data/aco/README.md); blank for the three
  unsupported subjects.

Cell formats replicate the released file exactly: int ``0``/``1`` for
GPT / DeepSeek-Flash, float ``0.0``/``1.0`` for Qwen and
Yekta-ACO, blanks for unavailable cells, LF line endings, rows ordered by
subject (fixed order) then mutant_id (lexicographic).

The released file itself is the drift anchor: every rebuilt cell must match
it, except the Yekta-ACO x BibTeX2DocBook block while the canonical pair file
is absent (reported, not silently ignored). ``--write`` is refused unless the
rebuild is complete, so the released matrix can never be degraded; use
``--output`` to side-write a partial rebuild for inspection.

Usage:
    python rebuild_mutant_kill_matrix.py                 # verify against released
    python rebuild_mutant_kill_matrix.py --write         # rewrite the released path
    python rebuild_mutant_kill_matrix.py --output x.csv  # side-write elsewhere
"""
import argparse
import csv
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'results/rq2/supplementary/inputs'
SRC = ROOT / "results/experiment_results/RQ2/mutant_kill_matrix.csv"
OUT = ROOT / "results/experiment_results/RQ2/mutant_kill_matrix.csv"

MUTANT_MANIFEST = DATA / "canonical_mutants.csv"
OPERATOR_MAP = DATA / "rq2_mutant_operator_map.csv"
LLM_OUTCOMES = DATA / "source_mutant_outcomes.csv"
ACO_CANONICAL = DATA / "aco" / "source_mutant_outcomes_aco_replay_cpl_uml.csv"
ACO_CANONICAL_BIBTEX = DATA / "aco" / "source_mutant_outcomes_aco_canonical_bibtex.csv"

SUBJECTS = ["Ant2Maven", "BibTeX2DocBook", "CPL2SPL", "Ecore2Maude",
            "Grafcet2PetriNet", "UML2ER"]
COLUMNS = ["killed_GPT", "killed_Qwen", "killed_DeepSeek-Flash",
           "killed_Yekta-ACO"]
LLM_PROVIDERS = {"killed_GPT": "gpt", "killed_Qwen": "qwen",
                 "killed_DeepSeek-Flash": "deepseek-flash"}
ACO_SUPPORTED = {"BibTeX2DocBook", "CPL2SPL", "UML2ER"}

# Survivor/kill anchors from the released Table 6 / pie (drift alarm).
EXPECTED_KILLED_TOTALS = {"killed_GPT": 213, "killed_Qwen": 163,
                          "killed_DeepSeek-Flash": 207,
                          "killed_Yekta-ACO": 95}


def read_eligible():
    """Eligible mutants with the released operator/rule metadata.

    mutation_operator is the released normalisation: multi-operator mutants
    (is_multi_operator, 92 of 288) collapse to "multi-operator"; all others
    keep operator_signature from rq2_mutant_operator_map.csv.
    """
    with open(MUTANT_MANIFEST, encoding="utf-8", newline="") as handle:
        meta = {(r["subject"], r["mutant_id"]): r
                for r in csv.DictReader(handle)
                if r["lifecycle"].strip() not in ("stillborn", "invalid", "equivalent")
                and r["evaluated_in_exported_matrix"].strip() == "1"}
    with open(OPERATOR_MAP, encoding="utf-8-sig", newline="") as handle:
        operators = {(r["subject"], r["mutant_id"]): r for r in csv.DictReader(handle)}
    missing = set(meta) - set(operators)
    if missing:
        raise SystemExit(f"FAIL: {len(missing)} eligible mutants absent from the operator map")
    rows = []
    for key, r in meta.items():
        op = operators[key]
        rows.append({
            "subject": r["subject"],
            "mutant_id": r["mutant_id"],
            "mutation_operator": "multi-operator" if op["is_multi_operator"] == "True" else op["operator_signature"],
            "faulty_rule": r["faulty_rule"],
        })
    return rows


def collect_kills(path, subjects=None):
    """Return {(subject, provider): {mutant_id: killed}} plus source counts."""
    kills: dict = defaultdict(dict)
    sources: dict = defaultdict(set)
    with open(path, encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            subject = row["subject"]
            if subjects is not None and subject not in subjects:
                continue
            if row.get("original_success", "1") != "1":
                continue
            if row.get("condition", "").lower() == "workflow":
                continue  # RQ4-only condition, excluded from the RQ2 ladder
            provider = row.get("provider", "aco").lower()
            key = (subject, provider)
            killed = row["outcome"] == "KILLED"
            prev = kills[key].get(row["mutant_id"])
            kills[key][row["mutant_id"]] = (prev or False) or killed
            sources[key].add(row["source_id"])
    return kills, sources


def fmt(column: str, value) -> str:
    if value is None:
        return ""
    if column in ("killed_Qwen", "killed_Yekta-ACO"):
        return "1.0" if value else "0.0"
    return "1" if value else "0"


def build_cells():
    """Return {(subject, mutant_id, column): str cell} for the full matrix."""
    kills, sources = collect_kills(LLM_OUTCOMES)

    aco_kills, aco_sources = collect_kills(ACO_CANONICAL, subjects={"CPL2SPL", "UML2ER"})
    if ACO_CANONICAL_BIBTEX.is_file():
        btx_kills, btx_sources = collect_kills(ACO_CANONICAL_BIBTEX, subjects={"BibTeX2DocBook"})
        aco_kills.update(btx_kills)
        aco_sources.update(btx_sources)
        bibtex_available = True
    else:
        bibtex_available = False

    cells: dict = {}
    for subject in SUBJECTS:
        for column, provider in LLM_PROVIDERS.items():
            killed = kills.get((subject, provider), {})
            has_sources = bool(sources.get((subject, provider)))
            for mutant in killed:
                cells[(subject, mutant, column)] = fmt(column, killed[mutant]) if has_sources else ""
        # Yekta-ACO
        if subject not in ACO_SUPPORTED:
            continue
        if subject == "BibTeX2DocBook" and not bibtex_available:
            continue  # stays blank; reported as pending
        killed = aco_kills.get((subject, "aco"), {})
        for mutant in killed:
            cells[(subject, mutant, "killed_Yekta-ACO")] = fmt("killed_Yekta-ACO", killed[mutant])
    return cells, bibtex_available


def render(eligible, cells) -> str:
    lines = ["subject,mutant_id,mutation_operator,target_rule," + ",".join(COLUMNS)]
    for subject in SUBJECTS:
        rows = sorted((m for m in eligible if m["subject"] == subject),
                      key=lambda r: r["mutant_id"])
        for row in rows:
            values = [cells.get((subject, row["mutant_id"], c), "") for c in COLUMNS]
            lines.append(",".join([subject, row["mutant_id"],
                                   row["mutation_operator"], row["faulty_rule"]]
                                  + values))
    return "\n".join(lines) + "\n"


def compare(rebuilt_rows, released_rows, bibtex_available):
    """Cell-level compare incl. metadata columns; returns (unexpected diffs, pending count)."""
    ridx = {(r["subject"], r["mutant_id"]): r for r in released_rows}
    unexpected, pending = [], 0
    for row in rebuilt_rows:
        rel = ridx[(row["subject"], row["mutant_id"])]
        for column in ("mutation_operator", "target_rule") + tuple(COLUMNS):
            got, want = row[column], rel[column]
            if got == want:
                continue
            if (column == "killed_Yekta-ACO" and row["subject"] == "BibTeX2DocBook"
                    and not bibtex_available and got == ""):
                pending += 1
                continue
            unexpected.append((row["subject"], row["mutant_id"], column, got, want))
    return unexpected, pending


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true",
                        help="rewrite the released path (refused unless the rebuild is complete)")
    parser.add_argument("--output", type=Path,
                        help="side-write the rebuilt matrix here instead of/in addition to stdout stats")
    args = parser.parse_args()

    eligible = read_eligible()
    cells, bibtex_available = build_cells()
    rendered = render(eligible, cells)
    rebuilt = list(csv.DictReader(rendered.splitlines()))

    with open(SRC, encoding="utf-8", newline="") as handle:
        released = list(csv.DictReader(handle))

    unexpected, pending = compare(rebuilt, released, bibtex_available)

    totals = {c: sum(1 for r in rebuilt if r[c] in ("1", "1.0")) for c in COLUMNS}
    print("[anchors] killed totals (rebuilt vs expected):")
    for column, expected in EXPECTED_KILLED_TOTALS.items():
        mark = "OK" if totals[column] == expected or (column == "killed_Yekta-ACO" and not bibtex_available) else "MISMATCH"
        print(f"  {column:22s} {totals[column]:>4d} vs {expected:>4d}  {mark}")
    print(f"[compare] cells differing from released: unexpected={len(unexpected)} "
          f"pending(BibTeX ACO)={pending}")
    for diff in unexpected[:10]:
        print("  DIFF", diff)

    if unexpected:
        raise SystemExit("FAIL: rebuilt matrix disagrees with the released file "
                         f"({len(unexpected)} unexpected cell diffs)")
    if not bibtex_available:
        print("[note] Yekta-ACO x BibTeX2DocBook (40 cells) pending "
              "aco/source_mutant_outcomes_aco_canonical_bibtex.csv — rebuild is partial.")

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8", newline="\n")
        print(f"[saved] {args.output}")
    if args.write:
        if not bibtex_available:
            raise SystemExit("REFUSED: --write would degrade the released matrix "
                             "while the BibTeX canonical pair file is missing.")
        byte_equal = SRC.read_bytes() == rendered.encode("utf-8")
        OUT.write_text(rendered, encoding="utf-8", newline="\n")
        print(f"[saved] {OUT.relative_to(ROOT)}"
              + (" (byte-identical to previous)" if byte_equal else " (content changed)"))
    elif not args.output:
        print("[dry-run] verified; use --output x.csv to side-write or --write to "
              "rewrite the released path (complete rebuilds only).")


if __name__ == "__main__":
    main()
