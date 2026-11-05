# src/experiment/experiment_runner.py

import os
import sys
import csv
import json
import logging
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from src.prompt.prompt_builder      import build_prompt, get_metamodel_paths, get_example_paths
from src.llm.llm_client import read_api_key, call_deepseek
from src.generator.test_generator   import generate_tests
from src.executor.transformation_executor import (
    run_transformation, run_all_mutants, _discover_mutants, _default_config
)
from src.analyzer.coverage_analyzer import (
    compute_rule_coverage, compute_mutation_kill_rate
)
from src.analyzer.metrics_collector import (
    collect_metrics, save_metrics, print_summary
)


# ── CSV 结果记录 ───────────────────────────────────────────────────────────────

CSV_FIELDNAMES = [
    "model_id",
    "rule_coverage",
    "rules_covered",
    "rules_total",
    "mutants_killed",
    "mutants_total",
    "kill_rate",
]


def _get_csv_path(output_base_dir: str) -> str:
    return os.path.join(output_base_dir, "metrics.csv")


def _init_csv(csv_path: str) -> None:
    """创建 CSV 文件并写入表头（如果文件不存在）。"""
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    if not os.path.isfile(csv_path):
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
            writer.writeheader()
            f.flush()


def _append_csv_row(csv_path: str, row: dict) -> None:
    """追加一行结果到 CSV 文件，写入后立即 flush。"""
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
        writer.writerow(row)
        f.flush()
        os.fsync(f.fileno())


# ── 日志配置 ──────────────────────────────────────────────────────────────────

def setup_logging(log_dir: str, run_id: str) -> logging.Logger:
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, f"{run_id}.log")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    return logging.getLogger(__name__)


# ── 默认实验配置 ───────────────────────────────────────────────────────────────

def default_experiment_config(base_dir: str) -> dict:
    dataset_dir = os.path.join(base_dir, "datasets", "models_BibTexML2DocBook")
    return {
        "base_dir":           base_dir,
        "dataset_dir":        dataset_dir,
        "template_path":      os.path.join(base_dir, "prompts",
                                           "generate_test_model.txt"),
        "atl_path":           os.path.join(dataset_dir, "transformations",
                                           "BibTeX2DocBook.atl"),
        "api_key_path":       os.path.join(base_dir, "config",
                                           "deepseek_api_key.txt"),
        "output_base_dir":    os.path.join(base_dir, "results"),
        "metamodel_configs":  ["core", "full"],
        "n_models":           10,
        "max_scenarios":      3,
        "run_mutation":       True,
    }


# ── 单次实验（一种 metamodel 配置）────────────────────────────────────────────

def run_experiment(config: dict) -> dict:
    base_dir    = config["base_dir"]
    dataset_dir = config["dataset_dir"]
    mm_config   = config["metamodel_config"]
    run_id      = f"{mm_config}_{datetime.now():%Y%m%d_%H%M%S}"

    log = setup_logging(os.path.join(base_dir, "logs"), run_id)
    log.info(f"{'='*60}")
    log.info(f"Experiment started  | config={mm_config} | n={config['n_models']}")
    log.info(f"{'='*60}")

    # ── 输出目录 & CSV ────────────────────────────────────────────────────
    generated_dir   = os.path.join(config["output_base_dir"],
                                   "generated_models", mm_config)
    transformed_dir = os.path.join(config["output_base_dir"],
                                   "transformed_outputs", mm_config)
    metrics_dir     = os.path.join(config["output_base_dir"], "metrics")
    for d in [generated_dir, transformed_dir, metrics_dir]:
        os.makedirs(d, exist_ok=True)

    csv_path = _get_csv_path(os.path.join(config["output_base_dir"], "metrics"))
    _init_csv(csv_path)
    log.info(f"CSV results → {csv_path}")

    # ── Step 1: 读取 API key ──────────────────────────────────────────────
    api_key = read_api_key(config["api_key_path"])
    log.info("API key loaded.")

    # ── Step 2: 生成测试模型 ──────────────────────────────────────────────
    log.info("Step 2: Generating test models...")
    metamodel_paths = get_metamodel_paths(dataset_dir, mm_config)
    example_paths   = get_example_paths(
        os.path.join(dataset_dir, "scenarios"),
        config["max_scenarios"])

    generation_results = generate_tests(
        template_path   = config["template_path"],
        metamodel_paths = metamodel_paths,
        ocl_path        = os.path.join(dataset_dir, "OCL_Constraints.txt"),
        example_paths   = example_paths,
        atl_path        = config["atl_path"],
        api_key         = api_key,
        output_dir      = generated_dir,
        n               = config["n_models"],
        start_index     = 1,
    )
    log.info(f"Generated {len(generation_results)} test pair(s).")

    # ── Step 3 & 4: 执行 transformation + 计算 coverage ──────────────────
    log.info("Step 3&4: Running transformations and computing coverage...")

    executor_cfg = _default_config()
    atl_file     = os.path.join(dataset_dir, "transformations",
                                "BibTeX2DocBook.atl")
    mutant_names = (_discover_mutants(executor_cfg["transformations_dir"])
                    if config.get("run_mutation") else [])

    coverage_results = []
    mutation_results = []

    for pair in generation_results:
        index_str   = pair["index"]
        source_path = pair["source"]
        output_path = os.path.join(transformed_dir,
                                   f"output_{index_str}.xmi")

        # ── 运行原始 transformation ───────────────────────────────────────
        exec_result = run_transformation(
            source_model_path   = source_path,
            output_model_path   = output_path,
            transformation_name = "BibTeX2DocBook",
        )

        if not exec_result["success"]:
            log.warning(f"[{index_str}] Transformation failed: "
                        f"{exec_result.get('error', '')}")
            coverage_results.append(None)
            mutation_results.append(None)
            # Write a partial row so every model_id is recorded
            _append_csv_row(csv_path, {
                "model_id":       index_str,
                "rule_coverage":  "",
                "rules_covered":  "",
                "rules_total":    "",
                "mutants_killed": "",
                "mutants_total":  "",
                "kill_rate":      "",
            })
            continue

        log.info(f"[{index_str}] Transformation succeeded.")

        # ── 计算 rule coverage ────────────────────────────────────────────
        trace_path = exec_result["trace"]
        if trace_path and os.path.isfile(trace_path):
            cov = compute_rule_coverage(trace_path, atl_file)
            log.info(f"[{index_str}] Rule coverage: "
                     f"{cov['rule_coverage']:.2%} "
                     f"({cov['covered_rules']}/{cov['total_rules']})")
        else:
            cov = None
            log.warning(f"[{index_str}] Trace file not found.")
        coverage_results.append(cov)

        # ── Step 5: mutation testing ──────────────────────────────────────
        mut = None
        if config.get("run_mutation") and mutant_names:
            log.info(f"[{index_str}] Running {len(mutant_names)} mutants...")
            mutant_exec_results = {}
            for name in mutant_names:
                mutant_out = os.path.join(
                    transformed_dir, f"output_{index_str}_{name}.xmi")
                res = run_transformation(source_path, mutant_out, name)
                mutant_exec_results[name] = res

            mut = compute_mutation_kill_rate(output_path, mutant_exec_results)
            log.info(f"[{index_str}] Kill rate: {mut['kill_rate']:.2%} "
                     f"({mut['killed_mutants']}/{mut['total_mutants']})")
        mutation_results.append(mut)

        # ── Write CSV row immediately after each model ────────────────────
        _append_csv_row(csv_path, {
            "model_id":       index_str,
            "rule_coverage":  round(cov["rule_coverage"], 4) if cov else "",
            "rules_covered":  cov["covered_rules"]           if cov else "",
            "rules_total":    cov["total_rules"]             if cov else "",
            "mutants_killed": mut["killed_mutants"]          if mut else "",
            "mutants_total":  mut["total_mutants"]           if mut else "",
            "kill_rate":      round(mut["kill_rate"], 4)     if mut else "",
        })
        log.info(f"[{index_str}] Row appended to {csv_path}")

    # ── Step 6: 聚合 metrics ──────────────────────────────────────────────
    log.info("Step 6: Collecting metrics...")
    metrics = collect_metrics(
        generation_results = generation_results,
        coverage_results   = coverage_results,
        mutation_results   = mutation_results,
        config             = {
            "metamodel_config": mm_config,
            "n_models":         config["n_models"],
            "run_mutation":     config.get("run_mutation", False),
        },
    )

    metrics_path = os.path.join(metrics_dir, f"{run_id}.json")
    save_metrics(metrics, metrics_path)
    print_summary(metrics)

    log.info(f"Experiment finished. Metrics → {metrics_path}")
    return metrics


# ── 运行全部实验配置（ablation study）────────────────────────────────────────

def run_all_configs(base_config: dict) -> dict:
    all_results = {}
    for mm_config in base_config.get("metamodel_configs", ["full"]):
        print(f"\n{'#'*60}")
        print(f"# Running config: {mm_config.upper()}")
        print(f"{'#'*60}")
        config = dict(base_config)
        config["metamodel_config"] = mm_config
        all_results[mm_config] = run_experiment(config)

    comparison_path = os.path.join(
        base_config["output_base_dir"], "metrics",
        f"comparison_{datetime.now():%Y%m%d_%H%M%S}.json")
    comparison = {
        cfg: {
            "rule_coverage":  r["summary"]["aggregate_rule_coverage"],
            "kill_rate":      r["summary"]["aggregate_kill_rate"],
            "execution_rate": r["summary"]["transformation_execution_rate"],
        }
        for cfg, r in all_results.items()
    }
    os.makedirs(os.path.dirname(comparison_path), exist_ok=True)
    with open(comparison_path, "w", encoding="utf-8") as f:
        json.dump(comparison, f, indent=2)
    print(f"\n[INFO] Comparison saved → {comparison_path}")
    print(json.dumps(comparison, indent=2))

    return all_results


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))

    config = default_experiment_config(base_dir)

    config["n_models"]          = 2
    config["metamodel_configs"] = ["core"]
    config["run_mutation"]      = True

    run_all_configs(config)


if __name__ == "__main__":
    main()