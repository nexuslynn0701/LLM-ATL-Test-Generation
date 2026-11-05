# 论文替换清单 — Yekta-ACO canonical 击杀种群对齐（2026-10-19，方案 A）

依据：`code/rq3/apply_yekta_canonical_population.py`；数值源 `results/experiment_results/RQ3/top1_rates.csv`、
`rq3_pairwise_counts.csv`、`results/rq3/supplementary/rq3_baseline_columns/`；
逐格 old→new 见 `rq3_yekta_population_change.csv`。以下行号均指 `<downloads>/main1008.tex` 现版。

## 1. Table 9（tab:rq3bw-top1matrix，L1536–L1553）：18 行整行替换（仅末列 Yekta-ACO 变化）

```
Ochiai & 98.94 & \textbf{99.45} & 95.69 & 98.02 & 98.61 & 98.68 & 98.75 & \best{100.00} & 98.21 & 98.40 & 96.92 & \textbf{98.97} & 91.62 & 91.58 \\
Tarantula & 97.88 & \textbf{98.34} & 96.17 & 97.52 & 97.92 & 98.03 & \best{99.38} & 97.28 & 97.02 & 96.81 & \textbf{97.95} & 96.92 & 96.34 & 93.68 \\
DStar2 & 98.94 & \textbf{99.45} & 95.69 & 98.02 & 98.61 & 98.68 & 98.75 & \best{100.00} & 98.21 & 98.40 & 96.92 & \textbf{98.97} & 91.62 & 90.53 \\
Kulczynski2 & 98.94 & \textbf{99.45} & 96.17 & 98.02 & 98.61 & 98.68 & 98.75 & \best{100.00} & 98.21 & 98.40 & 96.92 & \textbf{98.97} & 91.62 & 91.58 \\
Mountford & 98.94 & \textbf{99.45} & 95.69 & 98.02 & 98.61 & 98.68 & 98.75 & \best{100.00} & 97.62 & 98.40 & 96.92 & \textbf{98.97} & 93.72 & 91.58 \\
Zoltar & 98.94 & \textbf{99.45} & 96.17 & 98.51 & 98.61 & 98.68 & 98.75 & \best{100.00} & 98.21 & 98.40 & 96.92 & \textbf{98.97} & 91.62 & 87.37 \\
ArithmeticMean & \best{98.94} & 98.90 & 95.22 & 97.03 & 97.92 & 98.03 & \textbf{98.75} & 97.28 & 97.02 & 97.34 & 97.44 & \textbf{98.46} & 94.24 & 91.58 \\
Barinel & 97.88 & \textbf{98.34} & 96.17 & 97.52 & 97.92 & 98.03 & \best{99.38} & 97.28 & 97.02 & 96.81 & \textbf{97.95} & 96.92 & 96.34 & 93.68 \\
BraunBanquet & 97.88 & \textbf{98.34} & 96.17 & 97.52 & 97.92 & 98.03 & \best{99.38} & 97.28 & 97.02 & 96.81 & \textbf{97.95} & 96.92 & 96.34 & 93.68 \\
BaroniUrbaniBuser & 97.35 & \best{98.34} & 96.17 & 97.03 & 96.53 & 98.03 & \textbf{98.13} & 97.28 & 97.02 & 96.28 & \textbf{97.44} & \textbf{97.44} & 95.81 & 93.68 \\
Cohen & \best{99.47} & 98.90 & 97.13 & 97.03 & 97.92 & 98.03 & \textbf{99.38} & 97.28 & 98.81 & 98.40 & 97.95 & \textbf{98.97} & 95.29 & 93.68 \\
Ochiai2 & 98.94 & \textbf{99.45} & 95.69 & 98.02 & 98.61 & 98.68 & 98.75 & \best{100.00} & 98.21 & 98.40 & 96.92 & \textbf{98.97} & 91.62 & 91.58 \\
OP2 & 98.94 & \textbf{99.45} & 96.65 & 98.02 & 98.61 & 98.68 & \textbf{98.75} & 98.64 & 98.21 & 98.40 & 97.44 & \textbf{99.49} & 94.24 & 89.47 \\
Phi & \best{99.47} & 98.90 & 97.13 & 97.03 & 97.92 & 98.03 & \textbf{99.38} & 97.28 & 98.81 & 98.40 & 97.95 & \textbf{98.97} & 95.29 & 93.68 \\
Pierce & \best{98.94} & 98.90 & 95.22 & 97.03 & 97.92 & 98.03 & \textbf{98.75} & 97.28 & 97.02 & 97.34 & 97.44 & \textbf{98.46} & 94.24 & 91.58 \\
RogersTanimoto & 97.88 & 97.79 & 94.74 & \textbf{98.02} & 97.92 & 98.03 & 96.88 & \best{99.32} & 98.21 & \textbf{98.94} & 96.92 & 97.44 & 94.77 & 92.63 \\
RussellRao & 99.47 & \textbf{100.00} & 97.13 & 97.52 & \best{100.00} & \best{100.00} & 98.75 & 99.32 & 99.40 & \textbf{100.00} & 98.97 & 98.46 & 93.72 & 76.84 \\
SimpleMatching & 97.88 & 97.79 & 94.74 & \textbf{98.02} & 97.92 & 98.03 & 96.88 & \best{99.32} & 98.21 & \textbf{98.94} & 96.92 & 97.44 & 94.77 & 92.63 \\
```

逐格 old→new（仅末列）：Ochiai 84.26→91.58，Tarantula 86.11→93.68，DStar2 83.33→90.53，
Kulczynski2 84.26→91.58，Mountford 84.26→91.58，Zoltar 80.56→87.37，ArithmeticMean 84.26→91.58，
Barinel 86.11→93.68，BraunBanquet 86.11→93.68，BaroniUrbaniBuser 85.18→93.68，Cohen 86.11→93.68，
Ochiai2 84.26→91.58，OP2 82.41→89.47，Phi 86.11→93.68，Pierce 84.26→91.58，
RogersTanimoto 88.89→92.63，RussellRao 69.44→76.84，SimpleMatching 88.89→92.63。
（加粗/蓝色标注不受影响：新值仍低于各公式 LLM 最大值与 MM-Random。）

## 2. tab:rq3bw-pairwise-counts（L1767–L1784）：18 行整行替换

```
Ochiai & 8 & 4 & 0 & 9 & 3 & 0 \\
Tarantula & 6 & 6 & 0 & 10 & 2 & 0 \\
DStar2 & 9 & 3 & 0 & 9 & 3 & 0 \\
Kulczynski2 & 8 & 4 & 0 & 9 & 3 & 0 \\
Mountford & 9 & 3 & 0 & 9 & 3 & 0 \\
Zoltar & 10 & 2 & 0 & 9 & 3 & 0 \\
ArithmeticMean & 11 & 1 & 0 & 8 & 4 & 0 \\
Barinel & 6 & 6 & 0 & 10 & 2 & 0 \\
BraunBanquet & 6 & 6 & 0 & 10 & 2 & 0 \\
BaroniUrbaniBuser & 2 & 10 & 0 & 8 & 4 & 0 \\
Cohen & 0 & 12 & 0 & 8 & 4 & 0 \\
Ochiai2 & 8 & 4 & 0 & 9 & 3 & 0 \\
OP2 & 11 & 1 & 0 & 8 & 4 & 0 \\
Phi & 0 & 12 & 0 & 8 & 4 & 0 \\
Pierce & 11 & 1 & 0 & 8 & 4 & 0 \\
RogersTanimoto & 10 & 2 & 0 & 10 & 2 & 0 \\
RussellRao & 10 & 2 & 0 & 8 & 4 & 0 \\
SimpleMatching & 10 & 2 & 0 & 10 & 2 & 0 \\
```

说明：vs Yekta-ACO 一侧全线更新（Worse 多为 +1）；vs MM-Random 一侧 4 行变化——
DStar2 8/4→9/3 与 Mountford 8/4→9/3、Zoltar 8/4→10/2、RussellRao 9/3→10/2
（其中后三行同时清偿了 10-07 重建后论文未同步的旧格；Better 列仍全为 0，
正文 L1681 的 "ranging from 0 to 11" 仍然成立）。

## 3. 正文两处句子

**L1674**（原）：
`Similarly, Yekta-ACO shows a wider range of Top-1 rates (ranging from 69.4\% to 88.9\%), which is consistently below the LLM-based approaches across the reported formulas. `
（改）：
`Similarly, Yekta-ACO shows a wider range of Top-1 rates (ranging from 76.8\% to 92.6\%), which is consistently below the LLM-based approaches across the reported formulas. `

**L1682**（原）：`...and 7–9 configurations are significantly worse for most formulas, with the remaining comparisons being nonsignificant.`
（改）：`...and 8–10 configurations are significantly worse for most formulas, with the remaining comparisons being nonsignificant.`

（L1673 的 MM-Random 91.6–96.3 与 LLM 94.7–100.0 两句不受影响。）

## 4. 图

Fig. `fig:rq3-formula-boxplots`（L1596 引用 `figures/rq3/exam_boxplots.png`）：用包内重跑产物替换——
`code/rq3/plotting/exam_distribution/formula_redundancy/fig_rq3red_exam_boxplots.png`（pdf/svg 同名），
源数据 `fig_rq3red_exam_boxplots_source_data.csv`（43,650 观测）。
Fig. 5（cumulative）为纯 LLM 面板，内容不变，无需更换。

## 5. 可选

- Table 10（tab:rq3bw-meanmedian）现版只有 12 个 LLM 列，本次修正不产生强制改动；
  若要并入 MM-Random/Yekta-ACO 两列，用
  `results/rq3/supplementary/rq3_baseline_columns/baseline_columns.tex`（Yekta 为修正后数值，
  如 Ochiai 0.20/0.11、RussellRao 0.27/0.22），并顺手去掉 caption 里残留的 `{\color{red}baseline data}`。
- 建议在 L651（Top-1 定义）或 RQ3 Analysis 处补一句口径披露，回应审稿分母问题，例如：
  `For every approach, Top-1 and EXAM are pooled over the mutants that its own generated
  test suite kills on the applicable subjects; for Yekta-ACO these are the 95 canonically
  killed mutants on its three applicable subjects.`
- L1534 注释行 `%$n$ & ... & 108` 为陈旧值；若解注释应改为
  `%$n$ & 190 & 182 & 210 & 203 & 144 & 152 & 160 & 147 & 169 & 189 & 196 & 196 & 192 & 95`。
- L1721 起 `tab:rq3bw-bestworst` 与 L1791 起 `tab:rq3bw-tie` 均处注释状态，其中 vs Yekta 的
  p/A12/n 若日后启用需按 `rq3_pairwise_tests.csv` 重取。
