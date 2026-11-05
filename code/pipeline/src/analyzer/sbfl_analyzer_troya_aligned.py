"""Troya-2018-aligned SBFL analysis.

Independent from sbfl_analyzer.py. The spectrum unit is one
(mutant, violated OCL assertion) pair.
"""

from __future__ import annotations

import csv
import math
import re
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Iterable

from src.analyzer.sbfl_analyzer import FORMULAE, FORMULA_ORDER, TIE_MODES


@dataclass(frozen=True)
class AssertionSpectrum:
    mutant_id: str
    assertion_id: str
    target_rules: tuple[str, ...]
    rules: tuple[str, ...]
    failed: tuple[bool, ...]
    covered_by_rule: dict[str, tuple[bool, ...]]
    source_path: str

    @property
    def total_tests(self) -> int:
        return len(self.failed)

    @property
    def total_fail(self) -> int:
        return sum(self.failed)


def _split(line: str) -> list[str]:
    return line.rstrip("\n").split(";")


def parse_troya_assertion_csv(
    path: str | Path,
    mutant_id: str,
    target_rules: Iterable[str],
) -> AssertionSpectrum:
    """Parse one Troya artifact --OCL*.csv file without using stored scores."""
    path = Path(path)
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()

    assertion_line = next(
        line for line in lines if re.match(r"^OCL[^;]+;", line)
    )
    assertion_id = assertion_line.split(";", 1)[0]

    header_idx = next(
        i for i, line in enumerate(lines) if line.startswith("Rules;TC1;")
    )
    header = _split(lines[header_idx])
    tc_columns = [
        (pos, int(cell[2:]))
        for pos, cell in enumerate(header)
        if re.fullmatch(r"TC\d+", cell)
    ]
    if not tc_columns:
        raise ValueError(f"No TC columns found: {path}")

    status_idx = next(
        i for i in range(header_idx + 1, len(lines))
        if re.match(r"^;(Pass|Fail)(;|$)", lines[i])
    )
    statuses = _split(lines[status_idx])
    failed = tuple(
        statuses[pos].strip() == "Fail"
        for pos, _ in tc_columns
    )

    covered_by_rule: dict[str, tuple[bool, ...]] = {}
    for line in lines[header_idx + 1:status_idx]:
        cells = _split(line)
        rule = cells[0].strip() if cells else ""
        if not rule:
            continue
        covered_by_rule[rule] = tuple(
            pos < len(cells) and cells[pos].strip() == "X"
            for pos, _ in tc_columns
        )

    if not covered_by_rule:
        raise ValueError(f"No rule coverage rows found: {path}")

    return AssertionSpectrum(
        mutant_id=mutant_id,
        assertion_id=assertion_id,
        target_rules=tuple(target_rules),
        rules=tuple(covered_by_rule),
        failed=failed,
        covered_by_rule=covered_by_rule,
        source_path=str(path),
    )


def compute_rule_stats(spectrum: AssertionSpectrum) -> dict[str, dict[str, int]]:
    """Build NCF/NUF/NCS/NUS for each transformation rule."""
    stats = {}
    for rule in spectrum.rules:
        coverage = spectrum.covered_by_rule[rule]
        if len(coverage) != spectrum.total_tests:
            raise ValueError(f"Coverage length mismatch for {rule}")

        ncf = nuf = ncs = nus = 0
        for covered, failed in zip(coverage, spectrum.failed):
            if failed and covered:
                ncf += 1
            elif failed:
                nuf += 1
            elif covered:
                ncs += 1
            else:
                nus += 1

        stats[rule] = {
            "NCF": ncf,
            "NUF": nuf,
            "NCS": ncs,
            "NUS": nus,
        }
    return stats


def compute_scores(
    stats: dict[str, dict[str, int]],
) -> dict[str, dict[str, float]]:
    """Apply all 18 formulas. Imported functions use ef/ep/nf/np naming."""
    scores = {}
    for formula_name in FORMULA_ORDER:
        fn = FORMULAE[formula_name]
        per_rule = {}
        for rule, values in stats.items():
            score = fn(
                values["NCF"],  # ef
                values["NCS"],  # ep
                values["NUF"],  # nf
                values["NUS"],  # np
            )
            per_rule[rule] = float(score)
        scores[formula_name] = per_rule
    return scores


def first_fault_exam(
    scores: dict[str, float],
    target_rules: Iterable[str],
    tie_scenario: str,
) -> float:
    """Return EXAM until the first faulty rule is reached.

    For multi-fault mutants, the first encountered faulty rule stops the search.
    Within the top faulty tie bucket:
      BC: faulty rule first
      WC: all tied non-faulty rules first
      AC: midpoint of BC and WC
    """
    if tie_scenario not in TIE_MODES:
        raise ValueError(f"Unknown tie scenario: {tie_scenario}")

    faulty = {rule for rule in target_rules if rule in scores}
    if not faulty:
        raise ValueError(f"No target rule is present in ranking: {list(target_rules)}")

    n_rules = len(scores)
    if not n_rules:
        raise ValueError("Cannot rank an empty transformation")

    best_fault_score = max(scores[rule] for rule in faulty)
    higher = sum(score > best_fault_score for score in scores.values())
    tied_non_faulty = sum(
        score == best_fault_score and rule not in faulty
        for rule, score in scores.items()
    )

    rank_bc = higher + 1
    rank_wc = higher + tied_non_faulty + 1
    rank_ac = (rank_bc + rank_wc) / 2.0

    rank = {
        "BC": rank_bc,
        "AC": rank_ac,
        "WC": rank_wc,
    }[tie_scenario]
    return rank / n_rules


def compute_assertion_rows(spectrum: AssertionSpectrum) -> list[dict]:
    """Calculate all formula x tie-scenario rows for one assertion."""
    if spectrum.total_fail == 0:
        return []

    stats = compute_rule_stats(spectrum)
    scores = compute_scores(stats)
    rows = []

    for formula_name in FORMULA_ORDER:
        for tie_scenario in TIE_MODES:
            rows.append({
                "mutant_id": spectrum.mutant_id,
                "assertion_id": spectrum.assertion_id,
                "target_rules": "|".join(spectrum.target_rules),
                "formula_name": formula_name,
                "tie_scenario": tie_scenario,
                "EXAM": first_fault_exam(
                    scores[formula_name],
                    spectrum.target_rules,
                    tie_scenario,
                ),
                "total_rules": len(spectrum.rules),
                "total_tests": spectrum.total_tests,
                "total_fail": spectrum.total_fail,
                "source_path": spectrum.source_path,
            })
    return rows


def aggregate_per_mutant(rows: list[dict]) -> list[dict]:
    """Average assertion-level EXAM values for each mutant/formula/tie tuple."""
    grouped: dict[tuple[str, str, str, str], list[float]] = {}
    for row in rows:
        key = (
            row["mutant_id"],
            row["target_rules"],
            row["formula_name"],
            row["tie_scenario"],
        )
        grouped.setdefault(key, []).append(float(row["EXAM"]))

    result = []
    for (mutant, targets, formula, tie), values in sorted(grouped.items()):
        result.append({
            "mutant_id": mutant,
            "target_rules": targets,
            "formula_name": formula,
            "tie_scenario": tie,
            "assertion_count": len(values),
            "EXAM": mean(values),
        })
    return result


def write_csv(path: str | Path, rows: list[dict]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise ValueError(f"Refusing to write empty CSV: {path}")

    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def self_test() -> None:
    """Check first-fault semantics, including a multi-fault tie bucket."""
    scores = {
        "rule_A": 0.9,
        "rule_B": 0.8,  # faulty
        "rule_C": 0.8,
        "rule_D": 0.8,  # faulty
        "rule_E": 0.1,
    }
    targets = ["rule_B", "rule_D"]

    expected = {
        "BC": 2 / 5,
        "AC": 2.5 / 5,
        "WC": 3 / 5,
    }
    for tie, value in expected.items():
        actual = first_fault_exam(scores, targets, tie)
        if not math.isclose(actual, value):
            raise AssertionError(f"{tie}: expected {value}, got {actual}")


def parse_ocl_contracts(path: str | Path) -> dict[str, str]:
    """Parse active --OCLn sections from the dataset contract file."""
    lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    heading = re.compile(r"^\s*--\s*OCL\s*(\d+)\b", re.IGNORECASE)

    contracts: dict[str, str] = {}
    current_id = None
    expression_parts: list[str] = []

    def flush() -> None:
        nonlocal current_id, expression_parts
        if current_id and expression_parts:
            expression = " ".join(expression_parts).strip()
            # Troya CSV IDs enumerate active expressions, not comment headings.
            contract_id = f"OCL{len(contracts) + 1}"
            contracts[contract_id] = expression
        expression_parts = []

    for raw in lines:
        match = heading.match(raw)
        if match:
            flush()
            current_id = f"OCL{int(match.group(1))}"
            continue

        stripped = raw.strip()
        if not stripped or stripped.startswith("--") or stripped.startswith("---"):
            continue
        if current_id:
            expression_parts.append(stripped)

    flush()
    return contracts


def parse_atl_rule_names(path: str | Path) -> list[str]:
    """Extract named ATL matched/lazy rules in source order."""
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    names = re.findall(
        r"(?m)^\s*(?:lazy\s+|unique\s+)?rule\s+([A-Za-z_]\w*)\b",
        text,
    )
    return [name for name in names if name != "createTrace"]


def spectrum_from_trace_paths(
    mutant_id: str,
    assertion_id: str,
    target_rules: Iterable[str],
    all_rules: Iterable[str],
    trace_paths: Iterable[str | Path],
    failed: Iterable[bool],
    source_path: str,
) -> AssertionSpectrum:
    """Construct one assertion-level spectrum from original traces."""
    rules = tuple(all_rules)
    traces = [str(path) for path in trace_paths]
    failed_values = tuple(failed)
    if len(traces) != len(failed_values):
        raise ValueError("Trace and verdict lengths differ")

    executed = [_cached_parse_trace_rules(path) for path in traces]
    coverage = {
        rule: tuple(rule in reached for reached in executed)
        for rule in rules
    }
    return AssertionSpectrum(
        mutant_id=mutant_id,
        assertion_id=assertion_id,
        target_rules=tuple(target_rules),
        rules=rules,
        failed=failed_values,
        covered_by_rule=coverage,
        source_path=source_path,
    )


from functools import lru_cache


@lru_cache(maxsize=None)
def _cached_parse_trace_rules(path: str) -> frozenset[str]:
    from src.analyzer.sbfl_analyzer import _parse_trace_rules
    return frozenset(_parse_trace_rules(path))
