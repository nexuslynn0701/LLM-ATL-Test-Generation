# 当前论文范围同步（2026-11-05）

当前方法：GPT、Qwen、DeepSeek 的四档提示词及 Yekta-ACO。RQ5 的 workflow 保留。历史基线的数据、方法列表、重算输出与相关绘图入口已同步清理；原件保存在仓库之外的备份目录。

- 活跃 CSV 已清除已删除基线；论文核对文件统一放在 code/experiment_results/。
- RQ3：13 个配置，76,104 条变异体/公式记录，216 项检验统一使用原始 p < 0.05。
- 发布 CSV、绘图副本、每公式显著性计数、ACO 汇总片段与桌面 experiment_results 已同步。
- 按正文恢复原始 p 值：ACO统一canonical定位后，216项为208 Worse、8 Similar、0 Better；继续使用原始p < 0.05。
- 生成次数在没有可执行配对记录的格中从生成台账计算，Qwen/CPL 的候选数为100；不再依赖任意差异豁免。
- 镜像检查验证完整列集合。operator_counts 输出完整10列。
- 新增范围检查，阻止旧方法重新混入活跃CSV。注入测试现放在 code/reproduction/，本机以外也可从正式输入构造参照样例。

本轮新增ACO canonical定位门禁：从10,600条配对及逐源覆盖重建1,944条定位记录，禁止只改evaluable而保留旧排名。验收结果见rebuild/report.md。

ACO/BibTeX的4,000条配对已补齐。剩余限制仍包括workflow覆盖证据缺失/冲突及非ACO历史定位输入；未将它们宣称为全量独立复现。

运行：

```bash
python -X utf8 code/reproduction/smoke_test.py
python -X utf8 code/reproduction/build_tables.py
python -X utf8 code/reproduction/injection_tests.py
```

论文CSV统一目录：code/experiment_results/（19个CSV，含RQ4、RQ5 Overall及Table 16/17）。详细重建记录保存在rebuild/，同步统计在rebuild/scope_sync.json。
