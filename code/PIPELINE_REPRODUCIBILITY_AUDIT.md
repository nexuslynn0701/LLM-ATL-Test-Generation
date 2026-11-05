# Pipeline 可复现性核查（2026-10-15）

> **2026-10-19 增补**（下表为 10-15 当日核查记录，路径按当时布局保留）：① RQ1 校验脚本
> `check_failure_taxonomy.py`、`rule_coverage.py` 与两个测试已自 `code/reproduction/` 移至
> `code/rq1/`（`rq5_metrics.py` 移至 `code/rq5/`），unittest discover 命令相应改为
> `-s code/rq1`；② 可再生的 `code/runtime/pipeline_toolchain/` 副本已删除，重建入口
> `python code/prepare_pipeline.py`；③ 下文"RQ3 replay 依赖包外数据"一项已部分解决——
> 小件输入（zip 条目、Codex 四文件、论文 tex 快照）已收编入 `code/rq3/_replay_inputs/`
> （见其 README），剩余外部依赖为 637M 谱文件与 L1_inputs；`rq3/_replay/` 沙箱本体已删，
> 由 `python code/rq3/replay_sandbox.py` 重建。

## 结论

**目前不能认定为“只输入 API key，就能从头跑完全部实验并生成 RQ1–RQ5 正式结果”。**
包内已有输入、生成器、执行器、分析组件和大量可验证结果；但完整运行编排、Windows 执行兼容性和新运行到正式数据表的接口仍未闭合。

**已有发布数据的离线校验和部分汇总可以运行。** 本次实际运行 `verify.py`、失败分类校验、冻结 prompt 检查和复现单元测试；将 `reproduce_all.py` 的输入/输出指向隔离目录后成功生成 12 个派生文件。该脚本主函数只运行 population、RQ1、RQ2、RQ4、RQ5，没有 RQ3，不能据此宣称所有论文表都可重建。

本轮没有发送 API 请求，也没有对全部源模型×全部变异体重新执行。API 端点与指定模型的在线可用性未验证。LLM 新生成的输出及统计结果也不保证与历史样本逐字节一致。

## 阻塞完整重跑的问题

| 问题 | 直接证据 | 影响与需要补齐的内容 |
|---|---|---|
| 主脚本依赖已有实验 | `pipeline/run_pipeline.sh` 的 `wait_for_config` 无超时；阶段 2 等待旧 `GPT_core`、`GPT_fl_aware_v2` 各 300 行，未负责启动它们 | 从空目录运行会一直等待。需要一个从空目录启动的主入口，明确 6 科目×4 档×3 provider、workflow 和基线的阶段与失败处理 |
| Windows ATL 执行失败 | `pipeline/src/executor/transformation_executor.py` 两处 classpath 为 `lib/*:lib`；`data/workflow/src/executor/` 同样如此。真实执行器实测返回 1；直接启动 runner 报 `ClassNotFoundException: ATLRunner`。只在诊断命令中改成 `os.pathsep` 后成功进入 runner 参数检查 | 当前 Windows 本机不能直接执行。需修正单/多输出执行路径，并在六科目验证原转换与 mutant；本轮保留 pipeline 源码，未将诊断性控制实验当作修复 |
| 生成与 mutation/SBFL 未由同一入口串接 | `run_ladder_experiment.py` 执行生成、原转换、coverage 和 CSV；`run_workflow.py` 也是生成/原转换/反馈入口。谱导出器读取已经执行出的 mutant 文件，不负责产生这些文件 | 还需调用正式 mutant 集合上的执行、oracle 判定，再导出规则谱；不能只运行生成脚本就期望得到 RQ2/RQ3 |
| RQ1 模型大小重建不具备包内直接运行路径 | `rq1/model_size_audit/build_deliverables.py` 的 `REPO=<old-machine>/research/llm_mt_experiment`，并依赖历史审计输入；`reproduce_all.rq1()` 有意不再重建 model_size | 现有审计结果可校验；新样本的 containment-size 计算及发布还需接入 |
| RQ2 原始证据有一个明确缺口 | `rq2/rebuild_mutant_kill_matrix.py` 实测 `unexpected=0, pending(BibTeX ACO)=40`；`../results/rq2/supplementary/inputs/README.md` 说明缺少 canonical BibTeX ACO 配对矩阵 | 其他列可重建，但当前不能从包内配对证据完整重建该基线列；`--write` 会拒绝不完整覆盖。需要补件或按同一 oracle 重跑该格 |
| RQ3 replay 依赖包外数据 | `rq3/replay_sandbox.py` 使用 `<external-assets>/ppt` 谱/ZIP 及 `Documents/Codex/...` 的输入；适配版仍调用这个沙箱 | 本机已有沙箱的成功不能证明新电脑可运行。需将必需输入入包或改为直接接收新 run 的谱/配对数据，并去掉论文历史修补流程的必需依赖 |
| RQ5 新运行接口未实现 | `rq5/build_workflow_metrics.py --from-run` 明确退出并说明未实现；离线实测 54 格、312 项精确比较无 hard mismatch，但跳过 12 个 workflow coverage 格，另有 Ant/DeepSeek/workflow 一格冲突 | 该程序目前验证发布证据；尚不能自动把新 workflow 运行聚合成正式表。缺少的逐源 coverage 与冲突也需处理，不能把退出码 0 等同于全量证据齐全 |
| API 配置绑定历史网关 | Ladder 与 workflow 的 `llm_client.py` 默认使用 `api.agicto.cn`，Ladder 锁定特定模型 ID；workflow 另要求 `--atl-lib` | key 必须与配置端点匹配。需统一并外置 provider/endpoint/model/runtime 配置；本轮未联网确认这些服务 |

即使改在 Linux 上运行，Windows classpath 问题不再适用，其余编排和数据接口断点仍然存在。

## 本次实际验证

| 检查 | 结果 |
|---|---|
| `prepare_pipeline.py --check` | 6 科目、26 份 ecore、1,115 个 mutant ATL、OCL、模板和冻结清单存在；这里的 mutant 文件总数不是正式实验分母 |
| `reproduction/verify.py` | 全部检查通过，包括 9,521 个测试模型及 300 个 ACO 源文件哈希 |
| `reproduction/check_failure_taxonomy.py` | 7,200 次尝试、5,420 成功、1,780 失败；77 syntax/1,703 runtime，Table 3 和 Table 5 校验通过 |
| 冻结 prompt | 5/5 通过 |
| `unittest discover -s code/reproduction -p 'test_*.py'` | 5 项通过；首次被工具沙箱临时目录权限阻止，沙箱外重试通过，不计为项目错误 |
| Ladder/workflow `--help` | 均通过，仅证明导入与参数入口可用 |
| `reproduce_all.py` 隔离执行 | 12 个派生文件；没有运行 RQ3，也没有改写正式数据 |
| RQ2/RQ5 局部证据重算 | 如上所列，存在 pending/gap/conflict，不能当成全覆盖通过 |
| 迁移后的集成绘图总入口 | 5 组脚本实际运行成功，另单独运行方法示意图成功 |
| 迁移后文件检查 | 原 98 文件均可定位，33 个 Python 脚本语法解析通过，旧 `code/figures` 不存在 |

日志、隔离产物、移动清单与机器可读结果位于 [work/pipeline_audit_20261015](../work/pipeline_audit_20261015/)；尤其是 `offline_checks.json`、`java_classpath_control.json`、`layout_checks.json` 和 `figure_render.log`。

## 绘图迁移


| 原目录 | 当前目录 |
|---|---|
| `code/figures/01_prompt_ladder` | `code/shared/prompt_ladder`（方法图，不属于单个 RQ） |
| `code/figures/03_rq2_testing` | `code/rq2/plotting` |
| `code/figures/04_rq3_localization` | `code/rq3/plotting` |
| `code/figures/05_rq4_context_effects` | `code/rq4/plotting` |
| 更新版 Fig.4 | `code/rq2/plotting/baseline_complementarity` |
| 更新版 Fig.6 | `code/rq3/plotting/exam_distribution` |
| 更新版 Fig.7 | `code/rq5/plotting/four_metrics` |
| 更新版 Fig.8 | `code/rq5/plotting/workflow_complementarity` |
| 更新版 `run_all.py` | `code/reproduction/draw_all_figures.py` |

已更新 RQ3 适配脚本及其生成器中的公式源码路径。另修复方法图对 runtime 的导入，以及 RQ5 图对当前 `results/rq1/supplementary/subjects.csv` 的查找。历史脚本保留外部路径与溯源逻辑，它们不会因为移动目录就自动变成可独立运行的程序。
