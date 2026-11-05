# Subjects：六个数据集

- [Ant2Maven](Ant2Maven/)
- [BibTeX2DocBook](BibTeX2DocBook/)（原目录名 `models_BibTexML2DocBook`）
- [CPL2SPL](CPL2SPL/)
- [Ecore2Maude](Ecore2Maude/)
- [Grafcet2PetriNet](Grafcet2PetriNet/)
- [UML2ER](UML2ER/)

每个数据集保留元模型 `.ecore`、原始/插桩转换 `transformations/` 和 `scenarios/`。

9,521 个实验生成的测试 XMI 已集中到 [data/test_cases](../data/test_cases/README.md)。第一层为六个数据集；每个数据集内并列 `sm`、`stm`、`astm`、`astmo`、`workflow`，每种条件内再按 provider 排列。600 个随机基线用例分放于各数据集的 `_baselines/random/`。

另从 ACO 冻结包补入的 300 个源用例分放于 BibTeX2DocBook、CPL2SPL、UML2ER 各自的 `_baselines/aco/`。

OCL 已集中到 `../data/ocl/<subject>/`；mutants、编译产物及清单集中到 `../data/mutants/<subject>/`。原数据集的历史 `results/Results` 已移至 `../results/archive/legacy_subject_results/<subject>/`。

本目录的 `README.md` 是原测试模型包的说明，保留作来源记录；当前目录结构以本索引为准。
