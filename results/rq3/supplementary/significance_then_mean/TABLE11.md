Table 11. Representative best and worst LLM-generated test suites selected by pairwise significance tests followed by mean EXAM scores.

| Formula | Best cell | Worst cell |
|---|---|---|
| Ochiai | GPT-STM | Qwen-ASTM |
| Tarantula | GPT-STM | GPT-ASTM |
| DStar2 | GPT-STM | Qwen-ASTM |
| Kulczynski2 | GPT-STM | Qwen-ASTM |
| Mountford | GPT-STM | Qwen-ASTM |
| Zoltar | GPT-STM | Qwen-ASTM |
| ArithmeticMean | GPT-STM | Qwen-ASTM |
| Barinel | GPT-STM | GPT-ASTM |
| BraunBanquet | GPT-STM | GPT-ASTM |
| BaroniUrbaniBuser | GPT-STM | Qwen-ASTM |
| Cohen | GPT-STM | Qwen-ASTMO |
| Ochiai2 | GPT-STM | Qwen-ASTM |
| OP2 | GPT-STM | Qwen-ASTM |
| Phi | GPT-STM | Qwen-ASTMO |
| Pierce | GPT-STM | Qwen-ASTM |
| RogersTanimoto | GPT-STM | Qwen-ASTM |
| RussellRao | DeepSeek-SM | Qwen-ASTM |
| SimpleMatching | GPT-STM | Qwen-ASTM |

For each SBFL formula, the best cell has the lowest pooled mean EXAM among configurations not significantly outperformed by any other configuration. The worst cell has the highest pooled mean EXAM among configurations that do not significantly outperform any other configuration. Pairwise tests use mutants killed by both configurations, whereas pooled means use each configuration's own evaluable mutants. Two-sided paired Wilcoxon signed-rank tests use raw p < 0.05 and A12 to determine significant differences and their direction. Selected cells are representatives and are not necessarily significantly better or worse than all other configurations.

当前规则：先按显著性确定候选，再按各配置自身可评价变异体上的 pooled mean EXAM 选择代表。
均值完全相同则并列列出；本次未出现并列。每个比较的共同变异体集合可不同，候选集合不表示已经证明等效。
此前严格要求对其余全部 11 个配置获胜／落败的版本仅留作历史对照。
