"""Collect paper-facing RQ1--RQ5 CSVs into one author directory.

Published tables retain their complete historical cells. Partial rebuild
placeholders do not overwrite those released measurements.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "results/experiment_results"
FILES = {
    "RQ1/validity.csv": ("results/experiment_results/RQ1/validity.csv", "有效率：按 Generator、Cond. 选择行"),
    "RQ1/model_size.csv": ("results/experiment_results/RQ1/model_size.csv", "模型大小：n/min/median/mean/max"),
    "RQ1/rule_coverage.csv": ("results/experiment_results/RQ1/rule_coverage.csv", "规则覆盖率：covered_rules/total_rules、rule_coverage_pct"),
    "RQ2/mutation_results.csv": ("results/experiment_results/RQ2/mutation_results.csv", "变异分数：killed_mutants、eligible_mutants、mutation_score"),
    "RQ2/failure_rates.csv": ("results/experiment_results/RQ2/failure_rates.csv", "平均失败率：mean_fail_ratio_pct；保留数量、变异分数及状态"),
    "RQ2/per_mutant_failure_counts.csv": ("results/experiment_results/RQ2/per_mutant_failure_counts.csv", "逐变异体：n_killed、n_original_executable_sources、fail_ratio"),
    "RQ2/mutant_kill_matrix.csv": ("results/experiment_results/RQ2/mutant_kill_matrix.csv", "四种保留方法的逐变异体杀灭标志"),
    "RQ2/operator_counts.csv": ("results/experiment_results/RQ2/operator_counts.csv", "算子数量、算子内和套件变异分数"),
    "RQ3/wilcoxon.csv": ("results/experiment_results/RQ3/wilcoxon.csv", "216项检验：p_raw、A12、classification（原始p < 0.05）"),
    "RQ3/top1_rates.csv": ("results/experiment_results/RQ3/top1_rates.csv", "18公式×13配置的Top-1百分比"),
    "RQ3/EXAM_score.csv": ("results/experiment_results/RQ3/EXAM_score.csv", "EXAM mean/median/n"),
    "RQ3/mutant_level_exam.csv": ("results/experiment_results/RQ3/mutant_level_exam.csv", "逐mutant定位：74,160行历史输入＋1,944行canonical ACO重算结果"),
    "RQ4/rq4_ladder_four_columns_pooled.csv": ("rebuild/rq4/rq4_ladder_four_columns_pooled.csv", "LLM×context：validity_pct、coverage_pct、mutation_pct、failure_pct"),
    "RQ4/rq4_top1_exam_pooled.csv": ("results/experiment_results/RQ4/rq4_top1_exam_pooled.csv", "LLM×context：Top-1、EXAM、精确分子分母及相对SM的增量"),
    "RQ5/mutant_overlap.csv": ("results/experiment_results/RQ5/mutant_overlap.csv", "shared/astmo_only/workflow_only/neither杀灭计数"),
    "RQ5/rq5_overall_pooled.csv": ("rebuild/rq5/rq5_overall_pooled.csv", "RQ5四指标图Overall：按精确计数汇总及增量"),
    "RQ5/pooled_overall_by_formula.csv": ("rebuild/rq5/pooled_overall_by_formula.csv", "Table 16/17：从历史逐变异体记录重算Top-1、EXAM均值及中位数"),
}


def rows_from_bytes(payload: bytes):
    return list(csv.DictReader(io.StringIO(payload.decode("utf-8-sig"), newline="")))


def collect():
    """Prepare the complete paper collection before changing the destination."""
    prepared = []
    for target, (source, description) in FILES.items():
        path = ROOT / source
        if not path.is_file():
            raise FileNotFoundError(f"Missing {source}; run code/reproduction/build_tables.py first")
        payload = path.read_bytes()
        rows = rows_from_bytes(payload)
        if not rows:
            raise ValueError(f"Empty paper table: {source}")
        prepared.append((target, payload, dict(file=target, source=source,
                         rows=len(rows), columns=list(rows[0]), description=description)))
    source = "results/rq5/supplementary/workflow_metrics.csv"
    all_rows = rows_from_bytes((ROOT / source).read_bytes())
    for condition, name in [("astmo", "astmo.csv"), ("workflow", "fd_astmo.csv")]:
        selected = [r for r in all_rows if r["condition"] == condition]
        if len(selected) != 18:
            raise ValueError(f"Expected 18 {condition} workflow-metric rows")
        buf = io.StringIO(newline="")
        writer = csv.DictWriter(buf, fieldnames=list(selected[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(selected)
        payload = buf.getvalue().encode("utf-8-sig")
        target = "RQ5/" + name
        description = "ASTMO指标" if condition == "astmo" else "反馈式workflow指标"
        prepared.append((target, payload, dict(file=target, source=source,
                         filter={"condition": condition}, rows=len(selected),
                         columns=list(selected[0]), description=description)))
    assert len(prepared) == len(FILES) + 2
    return prepared


def export(output_dir: Path = DEFAULT_OUTPUT):
    output_dir = output_dir.resolve()
    protected_source = any(output_dir.is_relative_to(ROOT / name)
                           for name in ("data", "subjects"))
    protected_code = output_dir.is_relative_to(ROOT / "code")
    protected_source |= (output_dir.is_relative_to(ROOT / "results")
                         and not output_dir.is_relative_to(DEFAULT_OUTPUT))
    if output_dir == ROOT or protected_source or protected_code:
        raise ValueError("Choose a paper-output directory outside the source/evidence trees")
    prepared = collect()
    timestamp = datetime.now(timezone(timedelta(hours=8))).strftime("%Y%m%d_%H%M%S_%f")
    backup = None
    changed = [target for target, payload, _ in prepared
               if (output_dir / target).is_file() and (output_dir / target).read_bytes() != payload]
    # Back up the preexisting paper collection once before replacing any values.
    if changed:
        backup_parent = ROOT.parent if output_dir.is_relative_to(ROOT) else output_dir.parent
        backup = backup_parent / f"{output_dir.name}_backup_before_unify_{timestamp}"
        shutil.copytree(output_dir, backup)
    output_dir.mkdir(parents=True, exist_ok=True)
    for target, payload, _ in prepared:
        dst = output_dir / target
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not dst.exists() or dst.read_bytes() != payload:
            tmp = dst.with_name(dst.name + ".export.tmp")
            tmp.write_bytes(payload)
            tmp.replace(dst)
        if dst.read_bytes() != payload:
            raise RuntimeError(f"Export verification failed: {target}")
    index = sorted((item for _, _, item in prepared), key=lambda x: x["file"])
    metadata = ROOT / "rebuild/experiment_results_manifest.json"
    metadata.parent.mkdir(parents=True, exist_ok=True)
    metadata.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    return dict(output_dir=str(output_dir), csv_files=len(index), replaced_existing_files=len(changed),
                backup=str(backup) if backup else None)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    print(json.dumps(export(args.output_dir), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
