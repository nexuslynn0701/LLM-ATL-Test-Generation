# RQ4 梯子表（tab:rq4-ladder）生成链条

表结构：3 LLM（GPT/Qwen/DeepSeek）× 4 context（SM/STM/ASTM/ASTMO）× 6 指标
（Validity/Coverage/Mutation/Failure/Top-1/EXAM），SM 为基线行，其余行带对 SM 增量。

## 包内链条（全部可复算）

```
表  results/rq4/tables/rq4_ladder.tex
 ← 聚合脚本  code/rq4/build_rq4_ladder_table.py
    ├─ 池化 CSV  results/rq4/data/rq4_top1_exam_pooled.csv（Top-1/EXAM 两列）
    │   ← 变异体级数据  results/rq3/data/mutant_level_exam.csv（81,288 行）
    │       口径：LLM×context 的全部 evaluable 变异体（跨科目、跨 18 公式）直接池化；
    │       Top-1 = #(best_rank≤1)/n；EXAM = 逐变异体 EXAM-AC 均值（先恢复到
    │       2×rule_count×n_faulty_rules 秩格上的精确分数再平均）。
    │       全程精确分数，显示 ROUND_HALF_EVEN 两位；增量由未舍入值作差
    │       （Top-1 与 EXAM 均为 context−SM，EXAM 负值=改善）。
    └─ 四指标  results/rq4/supplementary/rq4_values_72_current.csv + rq4_deltas_54_current.csv
        ← 复算脚本  code/rq4/recompute_rq4_values72.py
           输入（全在 results/ 内）：
             rq1/data/validity.csv；shared/population/estar_population_by_cell.csv；
             rq1/data/rule_coverage.csv；rq2/data/mutation_score.csv；
             rq2/data/failure_rate_summary.csv；rq3/supplementary/cell_formula_scores.csv；
             rq3/data/mutant_level_exam.csv
           口径：科目等权（Failure 为非 N/A 科目等权：GPT/DeepSeek 6 科、Qwen 5 科；
           Qwen 空 CPL2SPL 在 Coverage/Mutation 按 0 计）；Top-1/EXAM 层为
           科目×公式单元等权（此为 values_72 自身口径，与表中池化列不同源，
           2026-10-15 复算与现有 CSV 逐位一致）。
```

复算入口：

```bash
python code/rq4/recompute_rq4_values72.py   # 校验（--write 可重生成）
python code/rq4/build_rq4_ladder_table.py   # 生成池化CSV+tex（--paper 可对论文做逐格 diff）
```

## 包外依赖（链条最底层，存在于本机但未打包）

- `results/rq3/data/mutant_level_exam.csv` 由 `<codex-sessions>\2026-10-07\c-users-<user>-desktop-llm-mt\work\mutant47_rebuild.py`（Mutant47 重建，2026-10-07）生成；
  其输入谱文件 `rq3_test_rule_spectra_long.csv` 位于
  `<external-assets>/ppt\rqx_final_exec_validity_0901\rqx_final_exec_validity_0901\03_rq3_localization\01_latest_execution_conditioned\`
- values_72/deltas_54 原版脚本为同目录 `recompute_rq4.py`（读的是重组前的 github_minimal_reproduction 路径）；包内 `recompute_rq4_values72.py` 为其路径适配+校验版，算术不变。

## 与当前论文（paper1014 及其后版本）的已知数值差

池化列在 2026-10-14 交付版中有 9 个边界格滑误（3 绝对值差 0.01，连带 6 个增量），
本脚本生成的规范值为：

| 单元格 | 交付/论文 | 规范值 |
|---|---|---|
| GPT/ASTM Top-1 | 96.00 | **96.01** |
| Qwen/ASTM EXAM | 0.42 | **0.43** |
| DeepSeek/STM EXAM | 0.38 | **0.39** |
| Qwen Top-1 增量（STM/ASTM/ASTMO） | +0.16/+0.45/+0.37 | **+0.17/+0.46/+0.38** |
| Qwen/ASTM EXAM 增量 | +0.00 | **+0.01** |
| DeepSeek/STM EXAM 增量 | −0.02 | **−0.01** |
| DeepSeek/ASTMO EXAM 增量 | +0.00 | **+0.01** |

（paper1014 的 Qwen Failure 列仍是旧 6 科目含 CPL2SPL 记 0 的 54.26 系；
截图版论文已改为 values_72 的 65.11 系，与本脚本一致。）
