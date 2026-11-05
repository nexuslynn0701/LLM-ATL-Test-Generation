# RQ3 配对显著性结果（原始 p 值）

每项比较按 subject + mutant_id 配对，在双方共同 killed mutants 上取逐 mutant 的 EXAM-AC；双侧 Wilcoxon 原始 p < 0.05 判显著。A12 报告效应量及方向。没有均值选择或多重比较校正。

## Table 11

| Formula | Best candidates | Worst candidates |
|---|---|---|
| Ochiai | GPT-STM | GPT-ASTM / Qwen-ASTM |
| Tarantula | GPT-STM | GPT-ASTM |
| DStar2 | GPT-STM | GPT-ASTM / Qwen-ASTM |
| Kulczynski2 | GPT-STM | GPT-ASTM / Qwen-ASTM |
| Mountford | GPT-STM | GPT-ASTM / Qwen-ASTM |
| Zoltar | GPT-STM | GPT-ASTM / Qwen-ASTM |
| ArithmeticMean | GPT-STM | GPT-ASTM / Qwen-ASTM |
| Barinel | GPT-STM | GPT-ASTM |
| BraunBanquet | GPT-STM | GPT-ASTM |
| BaroniUrbaniBuser | GPT-STM / DeepSeek-STM | GPT-ASTM / Qwen-ASTM |
| Cohen | GPT-STM / DeepSeek-STM | Qwen-ASTM / Qwen-ASTMO / DeepSeek-ASTMO |
| Ochiai2 | GPT-STM | GPT-ASTM / Qwen-ASTM |
| OP2 | GPT-STM | GPT-ASTM / Qwen-ASTM |
| Phi | GPT-STM / DeepSeek-STM | Qwen-ASTM / Qwen-ASTMO / DeepSeek-ASTMO |
| Pierce | GPT-STM | GPT-ASTM / Qwen-ASTM |
| RogersTanimoto | GPT-STM | GPT-ASTM / Qwen-ASTM |
| RussellRao | GPT-STM / DeepSeek-SM | GPT-ASTM / Qwen-ASTM |
| SimpleMatching | GPT-STM | GPT-ASTM / Qwen-ASTM |

## Table 12

| Formula | Yekta Worse | Yekta Similar | Yekta Better |
|---|---:|---:|---:|
| Ochiai | 12 | 0 | 0 |
| Tarantula | 10 | 2 | 0 |
| DStar2 | 12 | 0 | 0 |
| Kulczynski2 | 12 | 0 | 0 |
| Mountford | 12 | 0 | 0 |
| Zoltar | 12 | 0 | 0 |
| ArithmeticMean | 12 | 0 | 0 |
| Barinel | 10 | 2 | 0 |
| BraunBanquet | 10 | 2 | 0 |
| BaroniUrbaniBuser | 10 | 2 | 0 |
| Cohen | 12 | 0 | 0 |
| Ochiai2 | 12 | 0 | 0 |
| OP2 | 12 | 0 | 0 |
| Phi | 12 | 0 | 0 |
| Pierce | 12 | 0 | 0 |
| RogersTanimoto | 12 | 0 | 0 |
| RussellRao | 12 | 0 | 0 |
| SimpleMatching | 12 | 0 | 0 |

Table 11 的 Best candidates 为没有显著败绩的配置；Worst candidates 为没有显著胜绩的配置。
Table 12 的 Better/Worse 方向相对于 LLM。两表的逐项 p、A12、共同 mutant 数分别保存在两个 pairwise_tests.csv。
未检出显著差异不表示两种配置等效。论文原稿尚未替换。
