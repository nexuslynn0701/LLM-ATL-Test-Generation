# 整理后的 workflow 运行方式

从整个实验包根目录运行：

```powershell
python data/workflow/run_workflow.py --help
python data/workflow/run_workflow.py --subject Ant2Maven --provider gpt --n 100 --atl-lib code/pipeline/lib
```

第二条会实际调用模型，运行前需自行配置 `OPENAI_API_KEY`、`QWEN_API_KEY` 或 `DEEPSEEK_API_KEY`，以及 Python 依赖和 Java。目录整理和本次验证没有执行这条生成命令。

- 完整代码：`src/`。
- 静态输入：`assets/<subject>/`。
- 提示词模板：`prompts/template.txt`；六份初始渲染文本：`prompts/<subject>.txt`。
- 默认新结果：包根目录的 `results/rq5/new_workflow_runs/`；可用 `--output-root` 指定其他目录。
- Java runner 源码：`runtime_sources/`；本地实验包携带的 ATL/EMF jars 和编译类位于 `../../code/pipeline/lib/`。

`README.md` 保留原工作流算法说明及历史包路径；当前运行路径以本文件为准。后续覆盖反馈动态追加到提示词，六份文本是初始提示词，不是整个交互日志。
