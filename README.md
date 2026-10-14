# RV4PPTL

Reproducibility code and data for *RV4PPTL: A Runtime Verification Methodology Based on PPTL*, manuscript V2.5 (2026-10-14).

本仓库提供当前论文的固定边界 PPTL 监控器、语义核验、微博处理数据、代理标签，以及历史原型的复现代码。只需要 Python 标准库，无需安装第三方包、调用网络或安装 PPTL2BA。

## 快速开始 / Quick start

需要 Python 3.10 或更新版本；本次实际核验环境为 Windows、CPython 3.13.3。在仓库根目录打开终端：

```console
python reproduce.py
```

该命令会实际执行语义检查、从存档自动机重建旧原型、从 CSV 重新运行两个 cohort 的五个检测阈值、回放 26 条轨迹，并重新计算论文四张表。聚类分数使用存档的基线输出名单。所有结果均与论文期望值比较，不一致时以非零状态退出。

完整重跑三个聚类基线，执行：

```console
python reproduce.py --rerun-baselines
```

完整模式还会从 2,690 个 evaluation 话题的标题重新计算相似度，运行 Single-pass、HAC 和 medoid-style K-means，并要求输出名单逐项匹配存档。它需要更长时间和更多内存。HAC 的分数缓存优化见下文。

也可以在任意目录用脚本的绝对路径运行；代码不依赖上级论文目录。Linux/macOS 若没有 `python` 命令，可使用 `python3`。

成功时显示 `PASS`，生成：

| 输出文件（默认在 `outputs/`） | 内容 |
|---|---|
| `paper_tables.md` | 可直接查看的论文四张表 |
| `results.json` | 数值、比对状态、实际运行环境和耗时 |
| `semantic_validation.json` | 1,024 个输入、11,264 次前缀判断及边界检查 |
| `selected_topic_replay.json` | 26 个历史选中话题的逐条回放 |
| `historical_selections.json` | 从数据重跑的旧原型五组阈值检测名单 |

指定其他输出位置：`python reproduce.py --output outputs/check2`。程序不会改写输入数据或期望结果。

## 与论文的对应 / Paper coverage

| 论文位置 | 实际运行内容 | 应得结果 |
|---|---|---|
| §4.2、Theorem 2 | 固定边界构造，性质为 `((len(d1),...,len(dm)) prj (len(m) and B)); true` | 热点实例 21 个可达状态，字母表大小 4 |
| §5.1 | CSV 统计、6 小时最大热度、按首次正热度划分 cohort | 32,942 行、634 个快照、8,061 个标题；2,737 / 2,690 个有效话题 |
| §5.2、Table 1 | 原适配器 512 个窗口与两组诊断轨迹 | true / false / inconclusive 为 256 / 160 / 96；96 个末采样遗漏 |
| §5.2 | 新后端与独立判据比较 | 1,024 个输入、11,264 次比较、0 个不一致 |
| §5.2 | 历史选中话题在新后端回放 | 17+9 个话题全部满足流性质，均在第 9 次观测后 true |
| §5.3、Table 2 | 从正、负存档图重建 NFA、DFA、最小 DFA、旧乘积 | 正分量 30/30/21/21；负分量 21/21/28/15；22 个分配状态 |
| §5.5、Table 3 | 重跑旧原型，结合校准 cohort 的存档标签和事件映射计算分数 | 与论文五行阈值结果一致 |
| §5.5、Table 4 | 重新计算旧 RV 和三个基线的代理标签分数 | RV 行 9/8/6，P=0.889、D=0.750、H_PD=0.814 |

`expected/paper_results.json` 是对照值；计算函数不使用它生成结果。先计算，再比较。`data/retained_results.json` 提供历史检测与聚类名单；快速模式仅对聚类名单采用回放，完整模式还重新执行聚类。

**这两类监控器不能混为一个性能结果。** `rv4pptl/monitor.py` 是当前论文证明的固定边界后端；`rv4pptl/legacy.py` 保留旧适配器，包含论文诊断出的末采样问题。Table 3–4 描述旧原型的历史选择集。仓库没有把这些分数冒充为新后端在全部话题上的检测性能。

**计时和翻译范围。** 论文中的 2.386 秒从 `data/two_proposition_check.log` 读取，属于原机器上的历史记录。本仓库从存档 PPTL2BA 输出图开始重建旧链路；不重新执行外部 PPTL2BA，也不声称重现其原始耗时。当前后端接收采样间隔和布尔语法树，不是任意 PPTL 文本解析器。

## API

```python
from rv4pptl import hot_event_monitor, simulate, At, And, Not, compile_projection

monitor = hot_event_monitor()
trace = [{"p": True, "q": i in (0, 8)} for i in range(10)]
verdicts = simulate(monitor, trace)
assert verdicts[8] == "?"
assert verdicts[9:] == ["TRUE", "TRUE"]

# 投影位置 0、1、2 对应原轨迹位置 0、2、5。
another = compile_projection([2, 3], ["p", "q"],
                             And(At("p", 0), Not(At("q", 2))))
```

`simulate` 包含初始输出，因此索引 `n` 是读取 `n` 个观测后的结果。内部编码 `TRUE / FALSE / ?` 对应论文的 `true / false / inconclusive`；复现报告采用论文的完整单词。该例监控初始窗口，不进行滑动窗口搜索。

## 数据与来源 / Data provenance

原始数据源：[weibo-hot-hub 热搜档案](https://github.com/lonnyzhang423/weibo-hot-hub)。本仓库提供 2023-05-28 至 2023-06-24 的处理后小时 CSV，覆盖复现所需输入；快照下载和原始网页解析不在本次重跑范围内。

- `data/weibo/`：小时数据、保留的正负代理标签、事件去重映射。
- `data/legacy_automata/`：两命题版本的正、负自动机输出图。
- `data/retained_results.json`：原始存档输出，包含更早三命题版本的构造元数据。**不能用其中的 `monitor` 字段代替当前 Table 2**；Table 2 由两命题存档图重新构建。
- `data/two_proposition_check.log`：两命题构造和计时记录。
- `data/provenance.json`：输入的来源、SHA-256、代码迁移说明及对应论文源码哈希。

文件名中的 `ground_truth` 是历史命名。这些标签是新闻启发式产生的代理判断，不是完整人工标注；没有每个标签的完整新闻证据链。代码遇到缺失标签会报错，不把未知话题当作负例。D=E/H 是 distinctness，H_PD 是 precision–distinctness 调和分数；二者不是 recall / 标准 F1。

## 实现与检查

核心后端从论文配套实现原样复制。旧适配器与预处理函数保留原函数体，移除了机器绝对路径、外部工具启动入口和导入时创建目录的副作用。

`rv4pptl/baselines.py` 为历史 HAC 保留簇合并、堆更新、代表选择及并列处理顺序，缓存已有簇成员的相似度累计分数以减少重复计算。候选代表的分数按原表达式重新求和，处理浮点并列。原始 HAC 仍保存在 `rv4pptl/case_study.py`，测试使用多组带并列的小样本逐项比较两种实现；完整模式另验证论文数据上的输出名单。

```console
python -m unittest discover -s tests -v
```

所有运行输出、缓存和虚拟环境均由 `.gitignore` 排除。输入数据通过 `.gitattributes` 保持原始字节，便于跨平台校验。没有额外引入软件或数据的开源许可证；原第三方材料的权利归属不变。

## 后续绑定 GitHub

本地仓库使用 `main` 分支，尚未配置远端或进行任何上传。先在 GitHub 创建名为 `RV4PPTL` 的空仓库，**不要在网页端添加 README、许可证或 .gitignore**，再在本地执行：

```console
git remote add origin https://github.com/YOUR_ACCOUNT/RV4PPTL.git
git push -u origin main
```

把 `YOUR_ACCOUNT` 替换为真实账号。之后将真实链接填入论文 Data-Availability Statement；本地准备完成不等于已经公开归档。
