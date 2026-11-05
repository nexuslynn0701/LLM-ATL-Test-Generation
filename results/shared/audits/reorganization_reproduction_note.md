# 2026-10-12 目录整理：复现入口核验

整理只调整文件位置和必要的入口路径，不修改实验结果、提示词文本、OCL 或 mutant 内容。

## 验证

- 整理前后正式 artifact 检查均通过，9,521 个测试模型均存在。
- 整理后的六科目 workflow 静态输入和模板路径均可读取。
- 从分类后的文件重建原管线布局，冻结提示词五项回归检查通过。
- 在临时目录分别执行原版 `reproduce_all.py` 和适配新目录后的版本，两者生成的 12 份表格/报告内容一致（CSV 按字段与行比较，文本归一换行）。
- 未调用 LLM，未执行生成实验，未覆盖原有结果文件。

## 原有存储表与重算值的差异

原版脚本从包中现有数据重算时，也与以下两份原有汇总表存在差异，因此不是此次路径调整引入：

| 原有汇总表 | 差异示例：原有值 → 当前输入重算值 |
|---|---|
| `results/rq3/tables/rq3_formula_summary.csv` | DeepSeek / ASTM / arithmetic_mean 的 macro mean：0.402845 → 0.402842 |
| `results/rq5/tables/rq5_localization_summary.csv` | Ochiai 的 17 格配对 ASTMO / workflow：0.402425 / 0.371868 → 0.402260 / 0.371754 |

本次保留这两张表的原始内容。正式输入仍在各 RQ 的 `data/` 中；如后续执行 `python code/reproduction/reproduce_all.py`，将按照当前输入更新相应 `tables/` 文件。

机器可读记录：`code/maintenance/entrypoint_verification.json`。这份说明仅记录差异，不推断其历史来源，也未把 macro 与 pooled 口径混用。
