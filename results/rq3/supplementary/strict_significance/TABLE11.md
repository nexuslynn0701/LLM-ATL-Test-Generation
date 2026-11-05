Table 11. LLM-generated test suites with significantly lower or higher EXAM scores than all other 11 LLM configurations under each SBFL formula.

| Formula | Best cell | Worst cell |
|---|---|---|
| Ochiai | None | None |
| Tarantula | None | None |
| DStar2 | None | None |
| Kulczynski2 | None | None |
| Mountford | None | None |
| Zoltar | None | None |
| ArithmeticMean | None | None |
| Barinel | None | None |
| BraunBanquet | None | None |
| BaroniUrbaniBuser | None | None |
| Cohen | None | None |
| Ochiai2 | None | None |
| OP2 | None | None |
| Phi | None | None |
| Pierce | None | None |
| RogersTanimoto | None | None |
| RussellRao | None | None |
| SimpleMatching | None | None |

Each comparison uses EXAM scores on mutants killed by both configurations. Two-sided paired Wilcoxon signed-rank tests use raw p-values. A configuration qualifies as best (worst) only if all 11 comparisons have raw p < 0.05 and A12 favors that configuration (its opponent). None indicates that no configuration meets this criterion; it does not establish equivalence. No mean-based fallback is applied.

中文说明：无配置满足严格标准时标注 None（无）。均值排序不再用于此表。
全部检验使用原始p < 0.05。
