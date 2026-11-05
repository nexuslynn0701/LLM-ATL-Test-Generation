from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "results"
OUTPUTS = ROOT / "results"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def pct(numerator: int, denominator: int) -> float:
    return round(100.0 * numerator / denominator, 1)


def output_path(name: str) -> Path:
    import re
    match = re.match(r"rq([1-5])_", name)
    folder = OUTPUTS / (f"rq{match[1]}" if match else "shared") / "tables"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / name
