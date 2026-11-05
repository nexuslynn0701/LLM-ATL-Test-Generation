# src/analyzer/metrics_collector.py

import os
import json
from datetime import datetime
from collections import defaultdict


def collect_metrics(
    generation_results: list,
    coverage_results: list,
    mutation_results: list,
    config: dict = None,
) -> dict:
    """
    聚合所有实验指标。

    参数：
        generation_results: test_generator 的输出列表
            [{"index": "0001", "source": path, "target": path, ...}, ...]

        coverage_results: coverage_analyzer.compute_rule_coverage 的输出列表
            [{"rule_coverage": 0.88, "covered_rules": [...], ...}, ...]
            与 generation_results 一一对应，失败的用 None 占位

        mutation_results: coverage_analyzer.compute_mutation_kill_rate 的输出列表
            [{"kill_rate": 0.75, "killed": [...], ...}, ...]
            与 generation_results 一一对应，失败的用 None 占位

        config: 实验配置信息（会原样写入结果）

    返回：
        完整的 metrics dict，可直接序列化为 JSON
    """
    total_generated = len(generation_results)

    # ── Transformation Execution Rate ────────────────────────────────────
    successful_runs = sum(
        1 for r in coverage_results if r is not None)
    execution_rate = successful_runs / total_generated if total_generated > 0 else 0.0

    # ── Rule Coverage（聚合：所有模型覆盖规则的并集）────────────────────
    all_covered_rules = set()
    all_rule_coverages = []
    rule_execution_totals = defaultdict(int)

    for r in coverage_results:
        if r is None:
            continue
        all_covered_rules.update(r.get("executed_rules", []))
        all_rule_coverages.append(r.get("rule_coverage", 0.0))
        for rule, count in r.get("rule_executions", {}).items():
            rule_execution_totals[rule] += count

    total_rules = coverage_results[0]["total_rules"] if coverage_results and coverage_results[0] else 0
    aggregate_rule_coverage = (
        len(all_covered_rules) / total_rules
        if total_rules > 0 else 0.0
    )
    avg_rule_coverage = (
        sum(all_rule_coverages) / len(all_rule_coverages)
        if all_rule_coverages else 0.0
    )

    # ── Mutation Kill Rate（平均）────────────────────────────────────────
    kill_rates = [
        r["kill_rate"] for r in mutation_results
        if r is not None and "kill_rate" in r
    ]
    avg_kill_rate = sum(kill_rates) / len(kill_rates) if kill_rates else 0.0

    # 聚合所有模型的 killed mutants（并集）
    all_killed = set()
    all_alive  = set()
    total_mutants = 0
    for r in mutation_results:
        if r is None:
            continue
        all_killed.update(r.get("killed", []))
        all_alive.update(r.get("alive",  []))
        if total_mutants == 0:
            total_mutants = r.get("total_mutants", 0)

    aggregate_kill_rate = (
        len(all_killed) / total_mutants
        if total_mutants > 0 else 0.0
    )

    # ── 每个模型的详细指标 ────────────────────────────────────────────────
    per_model = []
    for i, gen in enumerate(generation_results):
        cov = coverage_results[i] if i < len(coverage_results) else None
        mut = mutation_results[i]  if i < len(mutation_results)  else None
        per_model.append({
            "index":          gen.get("index"),
            "source":         gen.get("source"),
            "target":         gen.get("target"),
            "exec_success":   cov is not None,
            "rule_coverage":  cov.get("rule_coverage")  if cov else None,
            "covered_rules":  cov.get("covered_rules")  if cov else None,
            "uncovered_rules":cov.get("uncovered_rules") if cov else None,
            "kill_rate":      mut.get("kill_rate")       if mut else None,
            "killed_mutants": mut.get("killed_mutants")  if mut else None,
        })

    metrics = {
        "timestamp":    datetime.now().isoformat(),
        "config":       config or {},
        "summary": {
            "total_generated":          total_generated,
            "successful_executions":    successful_runs,
            "transformation_execution_rate": round(execution_rate, 4),
            "aggregate_rule_coverage":  round(aggregate_rule_coverage, 4),
            "avg_rule_coverage":        round(avg_rule_coverage, 4),
            "covered_rules_union":      sorted(all_covered_rules),
            "uncovered_rules":          sorted(
                set(r for cov in coverage_results
                    if cov for r in cov.get("uncovered_rules", []))
                - all_covered_rules
            ),
            "rule_execution_totals":    dict(rule_execution_totals),
            "aggregate_kill_rate":      round(aggregate_kill_rate, 4),
            "avg_kill_rate":            round(avg_kill_rate, 4),
            "killed_mutants_union":     sorted(all_killed),
            "alive_mutants_union":      sorted(all_alive - all_killed),
            "total_mutants":            total_mutants,
        },
        "per_model": per_model,
    }

    return metrics


def save_metrics(metrics: dict, output_path: str) -> None:
    """将 metrics dict 保存为 JSON 文件。"""
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2, ensure_ascii=False)
    print(f"[INFO] Metrics saved → {output_path}")


def load_metrics(path: str) -> dict:
    """从 JSON 文件加载 metrics。"""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def print_summary(metrics: dict) -> None:
    """在终端打印 metrics 摘要。"""
    s = metrics["summary"]
    print("\n" + "="*60)
    print("EXPERIMENT SUMMARY")
    print("="*60)
    print(f"  Timestamp                  : {metrics['timestamp']}")
    print(f"  Config                     : {metrics.get('config', {})}")
    print(f"  Total generated            : {s['total_generated']}")
    print(f"  Execution rate             : {s['transformation_execution_rate']:.2%}")
    print(f"  Aggregate rule coverage    : {s['aggregate_rule_coverage']:.2%}  "
          f"({len(s['covered_rules_union'])}/{s['total_generated']} rules covered)")
    print(f"  Avg rule coverage/model    : {s['avg_rule_coverage']:.2%}")
    print(f"  Covered rules (union)      : {s['covered_rules_union']}")
    print(f"  Aggregate mutation kill    : {s['aggregate_kill_rate']:.2%}  "
          f"({len(s['killed_mutants_union'])}/{s['total_mutants']} mutants killed)")
    print(f"  Avg kill rate/model        : {s['avg_kill_rate']:.2%}")
    print("="*60)


# ── main：用于手动测试 ────────────────────────────────────────────────────────

def main():
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    # 用 executor_test 的结果构造模拟数据测试
    root    = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))
    dataset = os.path.join(root, "datasets", "models_BibTexML2DocBook")
    atl     = os.path.join(dataset, "transformations", "BibTeX2DocBook.atl")
    trace   = os.path.join(root, "results", "executor_test",
                           "test_output_trace.xmi")
    output  = os.path.join(root, "results", "executor_test",
                           "test_output.xmi")

    from src.analyzer.coverage_analyzer import (
        compute_rule_coverage,
        compute_mutation_kill_rate,
    )

    # 模拟 1 个生成结果
    generation_results = [
        {"index": "0001",
         "source": os.path.join(dataset, "scenarios", "scenario1",
                                "AutomaticModel_BibTex1.xmi"),
         "target": output}
    ]

    # 计算 coverage
    cov = compute_rule_coverage(trace, atl)
    coverage_results = [cov]

    # 模拟 mutation 结果（用 executor_test 里的文件）
    mutant_dir = os.path.join(dataset, "transformations")
    mutant_names = [
        f.replace(".asm", "")
        for f in sorted(os.listdir(mutant_dir))
        if f.endswith(".asm") and "Mutant" in f
    ]
    # 为了测试，模拟所有 mutant 都成功执行但输出与原始相同（都 alive）
    fake_mutant_results = {
        name: {"success": True, "output": output}
        for name in mutant_names
    }
    mut = compute_mutation_kill_rate(output, fake_mutant_results)
    mutation_results = [mut]

    # 聚合 metrics
    config = {"metamodel_config": "full", "n_models": 1}
    metrics = collect_metrics(
        generation_results, coverage_results, mutation_results, config)

    # 保存
    out_path = os.path.join(root, "results", "metrics", "test_metrics.json")
    save_metrics(metrics, out_path)

    # 打印摘要
    print_summary(metrics)


if __name__ == "__main__":
    main()