# src/experiment/run_experiment.py
# 改动：新增 --repeat N 参数，自动重复实验并输出 median 汇总

import sys
import argparse
import logging
import json
import statistics
from pathlib import Path
from datetime import datetime
import os

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.experiment.config_registry import (
    get_config, list_configs, print_registry, ExperimentConfig
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def run_from_config(cfg: ExperimentConfig, **kwargs) -> dict:
    """Run experiment from a registry config."""
    import src.experiment.multi_config_experiment as exp

    logger.info(f"\n{'='*65}")
    logger.info(f"Config:      {cfg.config_id}")
    logger.info(f"Name:        {cfg.name}")
    logger.info(f"Group:       {cfg.group}  |  RQ: {cfg.rq}")
    logger.info(f"Datasets:    {cfg.datasets}")
    logger.info(f"N models:    {cfg.n_models}")
    logger.info(f"Guidance:    {cfg.use_coverage_guidance}")
    logger.info(f"Repair:      {cfg.enable_repair}")
    logger.info(f"FL-aware:    {getattr(cfg, 'fl_aware_feedback', False)}")
    logger.info(f"Mutation:    {cfg.run_mutation}")
    logger.info(f"Hypothesis:  {cfg.hypothesis}")
    logger.info(f"{'='*65}\n")

    exp.N_MODELS              = cfg.n_models
    exp.RUN_MUTATION          = cfg.run_mutation
    exp.USE_COVERAGE_GUIDANCE = cfg.use_coverage_guidance
    exp.VERIFY_COVERAGE       = cfg.verify_coverage
    exp.LLM_PROVIDER          = getattr(cfg, 'llm_provider', 'deepseek')
    os.environ["LLM_PROVIDER"] = getattr(cfg, 'llm_provider', 'deepseek')
    exp.FL_AWARE_FEEDBACK     = getattr(cfg, 'fl_aware_feedback', False)
    exp.MIXED_MODE_FEEDBACK   = getattr(cfg, 'mixed_mode_feedback', False)
    exp.SAT_AWARE_FEEDBACK    = getattr(cfg, 'sat_aware_feedback', False)
    exp.SOURCE_ONLY_CONTEXT   = getattr(cfg, 'source_only_context', False)
    exp.NO_OCL                = getattr(cfg, 'no_ocl', False)
    exp.NO_ATL                = getattr(cfg, 'no_atl', False)
    exp.BLACKBOX_MODE         = getattr(cfg, 'blackbox_mode', False)

    generate_only = kwargs.get('generate_only', False)
    if generate_only:
        exp.RUN_MUTATION    = False
        exp.VERIFY_COVERAGE = False
        logger.info('[generate-only mode] Skipping ATL execution and mutation')

    mutation_only = kwargs.get('mutation_only', False)
    if mutation_only:
        exp.SKIP_GENERATION = True
        logger.info('[mutation-only mode] Skipping LLM generation, running mutation on existing models')

    results = exp.run_multi_config_experiment(
        configs     = [cfg.prompt_config],
        datasets    = cfg.datasets,
        config_id   = cfg.config_id,
    )

    logger.info(f"\n[DONE] Config '{cfg.config_id}' completed.")
    return results


def aggregate_repeat_results(all_runs: list[dict], config_id: str) -> dict:
    """
    跨多次运行计算 median。
    假设 results 是 dict，key 是 dataset 名，value 包含 fail_ratio / ochiai_ac 等数值。
    根据你的实际 results 结构可能需要微调这里。
    """
    if not all_runs:
        return {}

    # 收集所有 key
    all_keys = set()
    for run in all_runs:
        all_keys.update(run.keys())

    aggregated = {}
    for key in all_keys:
        values = []
        for run in all_runs:
            val = run.get(key)
            if isinstance(val, (int, float)):
                values.append(val)
            elif isinstance(val, dict):
                # 嵌套 dict：递归取 median
                if key not in aggregated:
                    aggregated[key] = {}
                for sub_key in val:
                    sub_vals = [
                        r[key][sub_key] for r in all_runs
                        if key in r and sub_key in r[key]
                        and isinstance(r[key][sub_key], (int, float))
                    ]
                    if sub_vals:
                        aggregated[key][sub_key] = {
                            "median": statistics.median(sub_vals),
                            "mean":   round(statistics.mean(sub_vals), 4),
                            "stdev":  round(statistics.stdev(sub_vals), 4) if len(sub_vals) > 1 else 0.0,
                            "values": sub_vals,
                        }
                continue
        if values:
            aggregated[key] = {
                "median": statistics.median(values),
                "mean":   round(statistics.mean(values), 4),
                "stdev":  round(statistics.stdev(values), 4) if len(values) > 1 else 0.0,
                "values": values,
            }

    return aggregated


def main():
    parser = argparse.ArgumentParser(
        description="Run experiments from config registry"
    )
    parser.add_argument("--generate-only", action="store_true",
                        help="Only generate models, skip ATL execution and mutation")
    parser.add_argument("--mutation-only", action="store_true",
                        help="Only run mutation on existing generated models, skip LLM generation")
    parser.add_argument(
        "--config", type=str,
        help="Config ID to run (e.g. B4_1_no_guidance)"
    )
    parser.add_argument(
        "--repeat", type=int, default=1,
        help="Number of times to repeat the experiment (default: 1). "
             "Results are aggregated as median across runs."
    )
    parser.add_argument(
        "--list", action="store_true",
        help="List all available configs"
    )
    parser.add_argument(
        "--group", type=str, default=None,
        help="Filter list by group"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print config details without running"
    )
    args = parser.parse_args()

    if args.list:
        print_registry() if not args.group else None
        if args.group:
            print(f"\n--- Group: {args.group} ---")
            for cfg in list_configs(args.group):
                print(f"\n  {cfg.config_id}")
                print(f"    RQ:            {cfg.rq}")
                print(f"    fl_aware:      {getattr(cfg, 'fl_aware_feedback', False)}")
                print(f"    Description:   {cfg.description}")
                print(f"    Hypothesis:    {cfg.hypothesis}")
        return

    if not args.config:
        parser.print_help()
        return

    cfg = get_config(args.config)

    if args.dry_run:
        print(f"\nDry run — config '{cfg.config_id}':")
        print(f"  prompt_config:         {cfg.prompt_config}")
        print(f"  use_coverage_guidance: {cfg.use_coverage_guidance}")
        print(f"  verify_coverage:       {cfg.verify_coverage}")
        print(f"  enable_repair:         {cfg.enable_repair}")
        print(f"  fl_aware_feedback:     {getattr(cfg, 'fl_aware_feedback', False)}")
        print(f"  n_models:              {cfg.n_models}")
        print(f"  run_mutation:          {cfg.run_mutation}")
        print(f"  datasets:              {cfg.datasets}")
        print(f"  sat_aware_feedback:    {getattr(cfg, 'sat_aware_feedback', False)}")
        print(f"  repeat:                {args.repeat}")
        return

    # ── 单次运行（原有行为）──────────────────────────────────────
    if args.repeat == 1:
        run_from_config(
            cfg,
            generate_only = getattr(args, "generate_only", False),
            mutation_only = getattr(args, "mutation_only", False),
        )
        return

    # ── 多次重复运行 ──────────────────────────────────────────────
    logger.info(f"\n[REPEAT] Running config '{cfg.config_id}' x{args.repeat} times")

    all_runs = []
    for i in range(1, args.repeat + 1):
        logger.info(f"\n{'#'*65}")
        logger.info(f"# Run {i}/{args.repeat}  —  {cfg.config_id}")
        logger.info(f"{'#'*65}")
        result = run_from_config(cfg)
        all_runs.append(result)
        logger.info(f"[Run {i}] result keys: {list(result.keys()) if result else 'None'}")

    # ── 聚合结果 ──────────────────────────────────────────────────
    aggregated = aggregate_repeat_results(all_runs, cfg.config_id)

    # 保存到文件
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path("results/repeat_runs")
    out_dir.mkdir(parents=True, exist_ok=True)

    # 原始每次结果
    raw_path = out_dir / f"{cfg.config_id}_repeat{args.repeat}_{timestamp}_raw.json"
    with open(raw_path, "w") as f:
        json.dump(all_runs, f, indent=2, default=str)

    # 聚合 median 结果
    agg_path = out_dir / f"{cfg.config_id}_repeat{args.repeat}_{timestamp}_aggregated.json"
    with open(agg_path, "w") as f:
        json.dump(aggregated, f, indent=2, default=str)

    logger.info(f"\n{'='*65}")
    logger.info(f"[REPEAT DONE] {args.repeat} runs completed for '{cfg.config_id}'")
    logger.info(f"  Raw results:        {raw_path}")
    logger.info(f"  Aggregated median:  {agg_path}")
    logger.info(f"{'='*65}")

    # 终端打印 aggregated 摘要
    print(f"\n=== Aggregated Results ({args.repeat} runs) ===")
    print(json.dumps(aggregated, indent=2, default=str))


if __name__ == "__main__":
    main()