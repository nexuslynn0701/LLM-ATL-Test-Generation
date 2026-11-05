#!/usr/bin/env python3
"""
scripts/recompute_sbfl_ocl_oracle.py
======================================
用 Troya 的 OCL oracle 替换 XMI diff oracle，重算 CPL2SPL / UML2ER /
Ecore2Maude 的 SBFL 指标（BibTeX 无 OCL results，跳过）。

核心思路：
  - XMI diff oracle：pass_fail[i] = (mutant_output[i] != original_output[i])
  - OCL oracle     ：pass_fail[i] = (任一 OCL constraint 在 TC_i 下被违反)
  - 用 OCL vector 替换后，ef/ep/nf/np 重算 → 重算所有 SBFL 公式和 EXAM score

oracle对比关键发现（CPL2SPL core method）：
  - mutant级别：OCL ⊇ XMI（OCL多检测7个 filter/class-change 类mutant）
  - TC级别：OCL fail_ratio < XMI（OCL只在property违反时kill）
  - SBFL效果：OCL下 ochiai_AC 更高（0.44 vs 0.27），kill判定更精准

输出：
  results/sbfl_ocl/{dataset}_ocl_exam.csv     <- OCL oracle EXAM scores
  results/sbfl_ocl/{dataset}_ocl_vs_xmi.csv   <- 逐mutant对比

用法：
  python3 scripts/recompute_sbfl_ocl_oracle.py
  python3 scripts/recompute_sbfl_ocl_oracle.py --datasets CPL2SPL UML2ER
  python3 scripts/recompute_sbfl_ocl_oracle.py --no-master
"""

import argparse
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.analyzer.sbfl_analyzer import (
    BUGGY_RULES, FORMULA_ORDER, TIE_MODES,
    _parse_trace_rules, _exam_for_buggy_rules, FORMULAE,
)
from src.analyzer.coverage_analyzer import extract_rules_and_helpers

OUTPUT_DIR = ROOT / "results/sbfl_ocl"
MASTER_CSV = ROOT / "results/sbfl_export/MASTER_sbfl_exam_all.csv"

# ── 数据集配置 ────────────────────────────────────────────────────────────────
DATASET_CFG = {
    "CPL2SPL": {
        "ds_dir":   ROOT / "datasets/models_CPL2SPL",
        "atl":      ROOT / "datasets/models_CPL2SPL/transformations/CPL2SPL.atl",
        "mutants":  [f"CPL2SPL_Mutant{i}" for i in range(1, 51)],
        "core_dir": ROOT / "results/outputs/CPL2SPL/core",
        "ocl_prefix": "CPL2SPL",
        "llm_dirs": {
            "GPT_core":         ROOT / "results_v2/gpt/outputs/CPL2SPL/GPT_core",
            "QWEN_core_v2":     ROOT / "results_v2/qwen/outputs/CPL2SPL/QWEN_core_v2",
            "DeepSeek_core_v2": ROOT / "results_v2/deepseek/outputs/CPL2SPL/DeepSeek_core_v2",
        },
    },
    "UML2ER": {
        "ds_dir":   ROOT / "datasets/models_UML2ER",
        "atl":      ROOT / "datasets/models_UML2ER/transformations/SimpleUml2ER.atl",
        "mutants":  [f"SimpleUml2ER_Mutant{i}" for i in range(1, 19)],
        "core_dir": ROOT / "results/outputs/UML2ER/core",
        "ocl_prefix": "SimpleUml2ER",
        "llm_dirs": {
            "GPT_core":         ROOT / "results_v2/gpt/outputs/UML2ER/GPT_core",
            "QWEN_core_v2":     ROOT / "results_v2/qwen/outputs/UML2ER/QWEN_core_v2",
            "DeepSeek_core_v2": ROOT / "results_v2/deepseek/outputs/UML2ER/DeepSeek_core_v2",
        },
    },
    "Ecore2Maude": {
        "ds_dir":   ROOT / "datasets/models_Ecore2Maude",
        "atl":      ROOT / "datasets/models_Ecore2Maude/transformations/Ecore2Maude.atl",
        "mutants":  [f"Ecore2Maude_Mutant{i}" for i in range(1, 51)],
        "core_dir": ROOT / "results/outputs/Ecore2Maude/core",
        "ocl_prefix": "Ecore2Maude",
        "llm_dirs": {
            "GPT_core":         ROOT / "results_v2/gpt/outputs/Ecore2Maude/GPT_core",
            "QWEN_core_v2":     ROOT / "results_v2/qwen/outputs/Ecore2Maude/QWEN_core_v2",
            "DeepSeek_core_v2": ROOT / "results_v2/deepseek/outputs/Ecore2Maude/DeepSeek_core_v2",
        },
    },
}


# ── OCL kill矩阵 ──────────────────────────────────────────────────────────────

def build_ocl_kill_matrix(ds: str, n_tcs: int = 100) -> dict:
    """
    {mutant_id: {tc_idx: killed(bool)}}
    任一OCL file中TC_i为Fail → killed=True
    """
    cfg         = DATASET_CFG[ds]
    results_dir = cfg["ds_dir"] / "results"
    prefix      = cfg["ocl_prefix"]
    matrix      = {}

    n_mutants = len(cfg["mutants"])
    for mid in range(1, n_mutants + 1):
        ocl_files = list(results_dir.glob(f"*Mutant{mid}--OCL*.csv"))
        tc_killed = {i: False for i in range(1, n_tcs + 1)}
        for f in ocl_files:
            content = f.read_text(encoding="utf-8", errors="replace")
            for line in reversed(content.splitlines()):
                if re.match(r'^;(Pass|Fail)', line):
                    tokens = line.split(";")
                    for i, tok in enumerate(tokens[1:], start=1):
                        if tok.strip() == "Fail":
                            tc_killed[i] = True
                    break
        matrix[mid] = tc_killed

    n_killed = sum(1 for tcs in matrix.values() if any(tcs.values()))
    print(f"    OCL kill: {n_killed}/{n_mutants} mutants killed")
    return matrix


# ── SBFL重算 ──────────────────────────────────────────────────────────────────

def compute_sbfl_ocl(
    mutant_name: str,
    trace_paths: list,
    tc_indices: list,
    ocl_kill_vector: dict,
    all_rules: list,
    buggy_rules: list,
) -> dict:
    n = len(trace_paths)
    pass_fail = [ocl_kill_vector.get(tc_indices[i], False) for i in range(n)]
    total_fail = sum(pass_fail)

    rule_stats = {r: {"ef": 0, "ep": 0, "nf": 0, "np": 0} for r in all_rules}
    for i, tp in enumerate(trace_paths):
        executed = _parse_trace_rules(tp)
        failed   = pass_fail[i]
        for rule in all_rules:
            s = rule_stats[rule]
            if rule in executed:
                if failed: s["ef"] += 1
                else:      s["ep"] += 1
            else:
                if failed: s["nf"] += 1
                else:      s["np"] += 1

    scores = {}
    for fname in FORMULA_ORDER:
        fn = FORMULAE[fname]
        scores[fname] = {
            r: fn(rule_stats[r]["ef"], rule_stats[r]["ep"],
                  rule_stats[r]["nf"], rule_stats[r]["np"])
            for r in all_rules
        }

    exam_scores = {}
    for fname, svals in scores.items():
        for mode in TIE_MODES:
            exam_scores[f"{fname}_{mode}"] = _exam_for_buggy_rules(
                svals, buggy_rules, all_rules, mode
            )

    return {
        "total_tests": n,
        "total_fail":  total_fail,
        "fail_ratio":  round(total_fail / n, 4) if n > 0 else 0,
        "exam_scores": exam_scores,
    }


def recompute_core(ds: str, ocl_matrix: dict, all_rules: list) -> pd.DataFrame:
    """core method：TC编号直接对应OCL TC编号，替换最干净。"""
    cfg      = DATASET_CFG[ds]
    core_dir = cfg["core_dir"]
    if not core_dir.exists():
        print(f"    [SKIP] core_dir不存在: {core_dir}")
        return pd.DataFrame()

    def fmt(i): return f"{i:04d}"
    available = sorted(
        int(f.stem.split("_")[1])
        for f in core_dir.glob("output_[0-9][0-9][0-9][0-9]_trace.xmi")
    )
    print(f"    core: {len(available)} scenarios")

    rows = []
    for mutant_name in cfg["mutants"]:
        mid   = int(re.search(r'Mutant(\d+)', mutant_name).group(1))
        buggy = BUGGY_RULES.get(mutant_name, [mutant_name])
        valid = [i for i in available
                 if (core_dir / f"output_{fmt(i)}_{mutant_name}.xmi").exists()]
        if not valid:
            continue
        traces = [str(core_dir / f"output_{fmt(i)}_trace.xmi") for i in valid]
        res = compute_sbfl_ocl(mutant_name, traces, valid,
                               ocl_matrix.get(mid, {}), all_rules, buggy)
        row = {"dataset": ds, "method": f"core_ocl", "oracle": "ocl",
               "mutant": mutant_name, "buggy_rules": "|".join(buggy),
               "total_tests": res["total_tests"], "total_fail": res["total_fail"],
               "fail_ratio": res["fail_ratio"]}
        row.update(res["exam_scores"])
        rows.append(row)
    return pd.DataFrame(rows)


# ── 对比分析 ──────────────────────────────────────────────────────────────────

def build_comparison(ds: str, df_ocl: pd.DataFrame,
                     df_xmi: pd.DataFrame) -> pd.DataFrame:
    xmi = df_xmi[(df_xmi["dataset"] == ds) &
                 (df_xmi["method"] == "core")].copy()
    ocl = df_ocl[df_ocl["method"] == "core_ocl"].copy()

    rows = []
    for _, orow in ocl.iterrows():
        mutant = orow["mutant"]
        xrow   = xmi[xmi["mutant"] == mutant]
        if len(xrow) == 0:
            continue
        xrow = xrow.iloc[0]
        xfr  = xrow.get("fail_ratio", np.nan)
        ofr  = orow["fail_ratio"]
        xac  = xrow.get("ochiai_AC", np.nan)
        oac  = orow.get("ochiai_AC", np.nan)
        rows.append({
            "dataset":             ds,
            "mutant":              mutant,
            "buggy_rules":         orow["buggy_rules"],
            "fail_ratio_xmi":      xfr,
            "fail_ratio_ocl":      ofr,
            "fail_ratio_diff":     round(ofr - xfr, 4) if not np.isnan(xfr) else np.nan,
            "ochiai_AC_xmi":       xac,
            "ochiai_AC_ocl":       oac,
            "ochiai_AC_diff":      round(oac - xac, 4)
                                   if not (np.isnan(oac) or np.isnan(xac)) else np.nan,
            "was_zero_failratio":  int(xfr == 0),
            "oracle_gap_resolved": int(xfr == 0 and ofr > 0),
            "xmi_only_kill":       int(xfr > 0 and ofr == 0),
        })
    return pd.DataFrame(rows)


def print_summary(ds: str, df_cmp: pd.DataFrame):
    resolved = df_cmp["oracle_gap_resolved"].sum()
    xmi_only = df_cmp["xmi_only_kill"].sum()
    both     = ((df_cmp["fail_ratio_xmi"] > 0) &
                (df_cmp["fail_ratio_ocl"] > 0)).sum()
    xmi_kill = (df_cmp["fail_ratio_xmi"] > 0).sum()
    ocl_kill = (df_cmp["fail_ratio_ocl"] > 0).sum()
    print(f"\n  {ds} core method:")
    print(f"    XMI kill: {xmi_kill}/{len(df_cmp)}  "
          f"OCL kill: {ocl_kill}/{len(df_cmp)}  "
          f"both: {both}/{len(df_cmp)}")
    print(f"    OCL-only (gap resolved): {resolved}  "
          f"XMI-only: {xmi_only}")
    print(f"    fail_ratio mean: XMI={df_cmp['fail_ratio_xmi'].mean():.4f}  "
          f"OCL={df_cmp['fail_ratio_ocl'].mean():.4f}")
    print(f"    ochiai_AC mean:  XMI={df_cmp['ochiai_AC_xmi'].mean():.4f}  "
          f"OCL={df_cmp['ochiai_AC_ocl'].mean():.4f}")
    if resolved > 0:
        gap = df_cmp[df_cmp["oracle_gap_resolved"] == 1]
        print(f"    修复的mutants:")
        for _, r in gap.iterrows():
            print(f"      {r['mutant']:35s} "
                  f"fr: {r['fail_ratio_xmi']:.3f}→{r['fail_ratio_ocl']:.3f}  "
                  f"ochiai: {r['ochiai_AC_xmi']:.3f}→{r['ochiai_AC_ocl']:.3f}")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="OCL oracle重算SBFL（三数据集）")
    parser.add_argument("--datasets", nargs="+",
                        default=["CPL2SPL", "UML2ER", "Ecore2Maude"],
                        choices=list(DATASET_CFG.keys()))
    parser.add_argument("--no-master", action="store_true",
                        help="不追加到MASTER CSV")
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    df_xmi = pd.read_csv(MASTER_CSV)
    all_ocl_dfs = []
    all_cmp_dfs = []

    print("=" * 60)
    for ds in args.datasets:
        print(f"\n[{ds}]")
        cfg = DATASET_CFG[ds]

        # 加载rules
        atl_info  = extract_rules_and_helpers(str(cfg["atl"]))
        all_rules = atl_info["rules"]
        print(f"  {len(all_rules)} rules")

        # OCL kill矩阵
        ocl_matrix = build_ocl_kill_matrix(ds)

        # 重算core method
        df_ocl = recompute_core(ds, ocl_matrix, all_rules)
        if len(df_ocl) == 0:
            print(f"  [SKIP] 无有效结果")
            continue

        all_ocl_dfs.append(df_ocl)

        # 保存OCL EXAM
        out = output_dir / f"{ds}_ocl_exam.csv"
        df_ocl.to_csv(out, index=False)
        print(f"  → {out}")

        # 对比
        df_cmp = build_comparison(ds, df_ocl, df_xmi)
        all_cmp_dfs.append(df_cmp)
        cmp_out = output_dir / f"{ds}_ocl_vs_xmi.csv"
        df_cmp.to_csv(cmp_out, index=False)
        print_summary(ds, df_cmp)

    # 合并summary
    if all_cmp_dfs:
        pd.concat(all_cmp_dfs).to_csv(
            output_dir / "all_datasets_ocl_vs_xmi.csv", index=False
        )

    # 追加到MASTER
    if not args.no_master and all_ocl_dfs:
        print("\n追加core_ocl到MASTER CSV...")
        master_cols = pd.read_csv(MASTER_CSV, nrows=0).columns.tolist()
        for df_ocl in all_ocl_dfs:
            for col in master_cols:
                if col not in df_ocl.columns:
                    df_ocl[col] = np.nan
            df_ocl[[c for c in master_cols if c in df_ocl.columns]].to_csv(
                MASTER_CSV, mode="a", header=False, index=False
            )
        print(f"  → {MASTER_CSV}")

    print(f"\n输出 → {output_dir}")


if __name__ == "__main__":
    main()