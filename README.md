# 北京大学本科毕业论文公开实验材料

这个仓库整理的是毕业论文中可以公开的实验脚本、数据切片与结果记录，研究主题是：

**面向软件需求澄清的大语言模型提问策略与基准适用性研究**

本仓库只作为公开实验材料包使用，帮助复现实验设计、运行流程和结果分析。论文正文、草稿、排版稿以及任何 Word / PDF / LaTeX 形式的论文成品不属于本仓库公开范围。

## 仓库结构

- `clareval/`：ClarEval 多轮需求澄清实验，比较 Direct 与 BED 风格澄清流程。
- `reqelicitgym/`：ReqElicitGym 隐式需求获取实验，比较 Direct、BED 和 aspect-aware 三类方法。
- `ambig-swe-useful-info/`：Ambig-SWE useful-information 实验，用于分析 issue reporter 可回答的额外有用信息恢复效果。

## 主要入口

每个实验目录都包含设计说明、结果分析、数据切片、运行脚本和源码。建议优先阅读：

- ClarEval：`clareval/Design.zh.md`、`clareval/Result.zh.md`、`clareval/pyproject.toml`
- ReqElicitGym：`reqelicitgym/Design.zh.md`、`reqelicitgym/Result.zh.md`、`reqelicitgym/run_experiment.py`
- Ambig-SWE useful-info：`ambig-swe-useful-info/Design.zh.md`、`ambig-swe-useful-info/Result.zh.md`、`ambig-swe-useful-info/run_experiment.ps1`

英文版设计与结果文档通常与中文版并列保存为 `Design.md` 和 `Result.md`。机器可读的实验输出位于各实验目录下的 `results/` 或 `outputs/` 子目录。

## 复现提示

三个实验包相互独立。进入对应目录后，可以根据该目录中的设计文档安装依赖、设置环境变量并运行实验。

运行真实模型实验通常需要 OpenAI-compatible API 凭据。请通过本地环境变量或本地 `.env` 文件配置密钥，不要把凭据提交到 Git。

## 公开范围说明

这个仓库只应公开：

- 实验源码与运行脚本；
- 可公开的数据切片；
- 实验结果记录与分析文档；
- 与复现相关的配置说明。

这个仓库不应公开：

- `thesis.docx`；
- `paper/` 目录；
- 任何论文正文、草稿、排版稿或查重/答辩版本；
- 任何 API key、访问令牌或私有配置。

`.gitignore` 已经对论文文档和常见运行痕迹做了强防护，但它不能删除已经进入 Git 历史或远端 GitHub 的文件。如果论文正文曾经被提交或推送过，需要单独清理 Git 历史，或将仓库保持为私有。
