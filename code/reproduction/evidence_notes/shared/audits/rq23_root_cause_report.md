# RQ2 / RQ3 九处失败计数差异：根因核查

核查时间：2026-10-08。九处差额均已逐项解释，剩余差额为 0。没有改动实验包、原始证据或论文。

## 结论

1. **CPL2SPL 的 8 处：旧故障标签失配触发 RQ3 显式排除 Mutant47。** RQ2 保留 50 个变异体；RQ3 保留 49 个。不是四舍五入，也不是八次运行分别丢失记录。
2. **Ant2Maven/GPT/ASTMO 的 1 处：0030 修复后只更新了 RQ2，RQ3 仍保留旧执行结果。** 本次实际重放原始转换及全部 100 个变异体，确认 14 次 KILLED、72 次 ALIVE、14 次 INVALID，正好补齐 2021−2007。

## CPL2SPL：从标签到排除再到差额的完整链条

- `pipeline_toolchain/src/analyzer/sbfl_analyzer.py:155` 把 `CPL2SPL_Mutant47` 的故障规则列为 `Main, SubAction2Function`。
- `generate_legacy_mutant_manifests.py` 从 `BUGGY_RULES` 生成遗留 manifest，因此相同标签进入 manifest。
- 现有 ATL 中没有名为 `Main` 的规则；Mutant47 与原始转换的源码差异位于 `CPL2Program`（删除 Program 输出及关联绑定）和 `SubAction2Function`（修改 name 绑定）。统一 diff 已另存。
- RQ3 builder 的第 449–459 行规定：只要声明故障规则不属于当前可排名规则集合，就记录 exclusion 并跳过整个变异体。`rq3_exclusion_manifest.csv` 明确记录 Main 无法映射，因此排除 Mutant47。
- 原始 RQ2 逐变异体 CSV 中，Mutant47 的 killed 次数恰好等于全部 8 个差额：GPT 的 SM/STM/ASTM/ASTMO 为 17/5/17/17，DeepSeek 为 1/2/2/2。其余共有变异体的失败次数逐项一致。
- 因此：已发布数值符合其排除规则，但排除的根源是历史故障定位标签与当前 ATL 不匹配。若目标是两项研究使用同一组 50 个变异体，应先核正 Mutant47 映射为当前源码中的故障规则，再重建 CPL2SPL 的 RQ3 及下游汇总，不能直接补一行或猜 EXAM。
- 此排除还影响 3 个 workflow 单元格和 MM-Random；ACO 原实现保留 50 个变异体，旧报告对此另有说明。本次九处核查只覆盖静态 LLM 梯度。

## Ant2Maven：0030 的修复未传递到 RQ3

| 证据层 | 样本/变异体 | killed pairs | Failure |
|---|---|---:|---:|
| 旧 RQ2 逐变异体记录 | 95 个可执行源模型 × 100 个变异体 | 2007 | 2007 / 9500 × 100 = 21.126315789… |
| 旧 RQ3 谱矩阵 | source_count 标注 96，但 0030 的 100 个 outcome 全为 INVALID | 2007 | RQ3 不计算此 Failure 汇总 |
| 包内 RQ2 新汇总 | 96 × 100 | 2021 | 2021 / 9600 × 100 = 21.052083333… |
| 本次 0030 重放 | 100 个变异体 | 新增 14 | 72 ALIVE、14 KILLED、14 INVALID |

包内 population_policy.md 和 estar_population_audit.json 明确写明 0030 已通过证据修复重新纳入。旧 RQ3 的谱矩阵共有 9600 个源模型/变异体对，其中 FAIL=2007、PASS=5752、INVALID=1841。0030 的 100 对均 INVALID（展开为 3000 条规则谱记录），所以 source_count=96 本身不能证明它进入了定位计算。

包内 Ant/GPT/ASTMO 的 **1800 行**（100 变异体 × 18 公式）在 failing_sources、EXAM BC/AC/WC、best_rank、tie_size、evaluable 各字段与旧版本完全一致。此次从旧谱矩阵重算 EXAM-AC、best_rank、evaluable、failing_sources，也全部通过 1800 行验证，然后才加入 0030 的重放结果。

### 重放方法与边界

使用包内 `test_cases/Ant2Maven/gpt/astmo/0030.xmi`、100 个 accepted manifest 变异体、对应 trace ASM、ATL/EMF 运行库和原始 `compare_xmi_models`。仅比较 OUTMaven 和 OUTProject；TM 不进入 oracle。原始转换执行成功，trace 覆盖 11 条规则，与旧覆盖谱的 0030 完全相同。新增 14 次 KILLED 全属于原本已经被其他源模型杀死的变异体，因此 suite mutation score 仍为 41/100。

Windows 的 Java 路径需要 URI：只在本地工作副本把 runner 的 `.getAbsolutePath()` 改为 `.toURI().toString()` 并重新编译，classpath 使用 Windows 分隔符；模型、转换和比较逻辑未改。完整命令、日志与输出保存在 `<codex-sessions>\2026-10-07\c-users-<user>-desktop-llm-mt\work\ant0030_replay`。这是一轮当前本机的可复现验证，不伪称找到了历史修复运行日志。

### 对论文结果的实测影响

- Top-1 不变（18 个公式均不变），killed mutants 仍为 41。
- EXAM-AC 只有 **Mutant144 的 cohen、phi** 两项从 17/120 变为 19/120；两公式科目级均值从 0.237195121951… 变为 0.237601626016…。
- Ant/GPT/ASTMO 的 18 公式宏均值增加 1/22140；GPT/ASTMO 六科目 Overall EXAM 增加 1/132840。
- GPT/ASTMO Overall EXAM：`0.407246690538393 → 0.407254218391449`。两位值仍 **0.41**，相对 SM 的改善量仍 **+0.00**。RQ4 的其他 71 个绝对值不因本次 0030 补录而变化。
- 这只量化 0030 修复。**没有把 CPL2SPL 的 Mutant47 重新纳入**；因此不代表完成了统一 50 变异体口径的全套重建。

## 九处逐项对账

| 科目 | 方法 | RQ2 | RQ3 | 已解释差额 | 未解释 |
|---|---|---:|---:|---:|---:|
| Ant2Maven | GPT-ASTMO | 2021 | 2007 | 14 | 0 |
| CPL2SPL | GPT-SM | 618 | 601 | 17 | 0 |
| CPL2SPL | GPT-STM | 184 | 179 | 5 | 0 |
| CPL2SPL | GPT-ASTM | 633 | 616 | 17 | 0 |
| CPL2SPL | GPT-ASTMO | 554 | 537 | 17 | 0 |
| CPL2SPL | DeepSeek-Flash-SM | 33 | 32 | 1 | 0 |
| CPL2SPL | DeepSeek-Flash-STM | 74 | 72 | 2 | 0 |
| CPL2SPL | DeepSeek-Flash-ASTM | 75 | 73 | 2 | 0 |
| CPL2SPL | DeepSeek-Flash-ASTMO | 65 | 63 | 2 | 0 |

## 交付文件与建议

- `rq23_reconciliation_9.csv`：九处对账，剩余差额全部为 0。
- `rq23_ant0030_old_spectra.csv`：旧版 0030 的 3000 条谱记录。
- `rq23_ant0030_replay.csv`：当前重放的 100 个 outcome。
- `rq23_ant0030_formula_impact.csv` / `rq23_ant0030_mutant_impact.csv`：公式及变异体级影响。
- `rq4_values_72_after_ant0030_replay.csv` / `rq4_deltas_54_after_ant0030_replay.csv`：仅补录 0030 后的高精度修订版；保留已发布的 CPL2SPL 排除口径。
- `rq23_cpl_mutant47.diff`：Mutant47 相对原始转换的实际差异。

建议先修复 RQ3 对 0030 的输入同步，再核正 Mutant47 的 fault map 并统一声明/重建 CPL2SPL 定位语料。不要通过修改 RQ2 计数来强行抹平两类差异。

## 关键来源

