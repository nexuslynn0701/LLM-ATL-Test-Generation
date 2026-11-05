# RQ3：原始 p 值版本

两张表均使用双侧配对 Wilcoxon 原始 p < 0.05，不做多重比较校正。
Table 11 先筛选无显著败绩／无显著胜绩的候选，再按各配置自身可评价变异体的平均 EXAM 选最低／最高者。

## Table 11

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

显著性比较使用双方共同击杀集；A12 判断方向。Similar 不表示已证明等效。
Table 11 的代表不一定显著优于／劣于其余全部配置。显著性使用原始p值。
论文原稿尚未替换；本目录与 results/rq3/tables/table11_raw_p.tex、table12_raw_p.tex 为本次交付。
