# RQ3：无多重比较校正，显著全胜/全负优先、均值回退

两组检验均使用原始双侧配对 Wilcoxon p < 0.05。当前主结果保留 A12 判断方向，另附完全由 Wilcoxon 符号秩方向决定的结果供判断是否删除 A12。
Best/Worst 需要显著胜过/输给其余全部 11 个配置；没有满足者时，从全部 12 个配置按 pooled mean EXAM 最低/最高选择。

| Formula | Best | Worst | ACO W | ACO S | ACO B |
|---|---|---|---:|---:|---:|
| ArithmeticMean | GPT-ASTMO | Qwen-ASTMO | 12 | 0 | 0 |
| Barinel | GPT-STM | Qwen-ASTMO | 10 | 2 | 0 |
| BaroniUrbaniBuser | GPT-ASTMO | Qwen-ASTMO | 10 | 2 | 0 |
| BraunBanquet | GPT-STM | Qwen-ASTMO | 10 | 2 | 0 |
| Cohen | GPT-ASTMO | Qwen-ASTMO | 12 | 0 | 0 |
| DStar2 | GPT-STM | Qwen-ASTMO | 12 | 0 | 0 |
| Kulczynski2 | GPT-ASTMO | Qwen-ASTMO | 12 | 0 | 0 |
| Mountford | GPT-STM | Qwen-ASTMO | 12 | 0 | 0 |
| Ochiai | GPT-STM | Qwen-ASTMO | 12 | 0 | 0 |
| Ochiai2 | GPT-STM | Qwen-ASTMO | 12 | 0 | 0 |
| OP2 | GPT-ASTMO | Qwen-ASTMO | 12 | 0 | 0 |
| Phi | GPT-ASTMO | Qwen-ASTMO | 12 | 0 | 0 |
| Pierce | GPT-ASTMO | Qwen-ASTMO | 12 | 0 | 0 |
| RogersTanimoto | GPT-ASTMO | Qwen-ASTMO | 12 | 0 | 0 |
| RussellRao | GPT-ASTMO | Qwen-ASTMO | 12 | 0 | 0 |
| SimpleMatching | GPT-ASTMO | Qwen-ASTMO | 12 | 0 | 0 |
| Tarantula | GPT-STM | Qwen-ASTMO | 10 | 2 | 0 |
| Zoltar | GPT-ASTMO | Qwen-ASTMO | 12 | 0 | 0 |

汇总：{"Worse": 208, "Similar": 8, "Better": 0}
A12 与 Wilcoxon 方向比较：基线分类差异 0 项；LLM 内部分类差异 6 项。
两种方向定义导致 Best/Worst 表名称不同的公式：[]。
Similar 仅表示未检出显著差异。这里的原始 p 阈值不控制整组多重比较的错误率。
校正前的逐项 p 和 A12 已与历史统计结果核对；基线仅有 ACO。所有比较均在共同击杀集上逐 mutant 配对；均值回退使用各配置自身可评价集合。
