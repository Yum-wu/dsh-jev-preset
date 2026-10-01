# dsh-jev-preset

[![CI](https://github.com/Yum-wu/dsh-jev-preset/actions/workflows/ci.yml/badge.svg)](https://github.com/Yum-wu/dsh-jev-preset/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)

[English](./README_EN.md)

一个给 [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness)（DSH）用的 agent preset（预设）bundle。

它做的事情只有一件：让模型在给出数值/风控结论之前，先真跑一次代码把数算对。

---

## 它解决什么

单会话模型在量化与风控任务上有三类失效：

1. **算错但说得很顺**。错误结论常被一段流畅推导包装，人工复核很难发现。
2. **自回归自污染**。在同一会话里让模型"分三个视角分析"，后文被前文锚定，不是真正的多路。
3. **没有物理真值**。公式和理解没在解释器里跑过，就不该放行。

## 怎么用（安装）

这是一个标准的 DSH bundle：一个 npm 包，携带一层 `cordis.patch.yml`，挂进 profile 的 loader 树。

```
dsh plugin --profile <你的 profile> add dsh-jev-preset
```

装完后校验配置层已生效（不必启动）：

```
dsh --profile <你的 profile> --dump-config
```

预期能看到一行 `# == dsh-jev-preset`。然后启动即可在预设列表里选到 **JEV 自适应交叉验证**。

卸载走同一入口：`dsh plugin --profile <你的 profile> remove dsh-jev-preset`。

> 本 bundle 不声明任何 `dependencies` / `peerDependencies`，也不写死 DSH 版本号 ——
> 声明行自带 `inject = ["agentPresets"]`，由 loader 等注册表就绪后激活，子插件路径由宿主
> `@deepseek-ai/dsh-agent-preset` 的 baseUrl 解析。0.1.7 起实测可用，0.2.0-rc.2 上验证通过。

## 门控：什么时候做什么

模型按下表判定，不需要用户干预：

| 任务类型 | 处理 |
|---|---|
| 日常/低危（检索、问答、单文件小改） | Fast-Pass 单次直出 |
| 数值计算、风控、仓位、爆仓价、指标推导 | **单路作答 + 真跑代码复算**，断言通过才放行 |
| 高危但结论不是唯一数值（安全边界、并发、方案取舍） | 裂变 3 路隔离采样 |
| 上面任一种，但断言/测试没通过 | 结论不放行，先修断言；修不动才升级三路 |

三路是兜底，不是默认。原因见下节数据。

## 实测数据

所有数字来自本仓 `benchmarks/accuracy/` 下的可复现实验。

| 手段 | 效果 | 成本 |
|---|---|---|
| 题干结构化 | +89pp（5/5 模型达 100%） | ×1 |
| **执行断言** | **24/30 → 30/30，McNemar p=0.0312** | ×2.0 |
| 换异构模型 | +89pp（部分模型） | ×5.4 |
| 三路隔离采样 | **增益 0（p=1.0）** | ×10.6 |

关键结论：**执行断言是本仓唯一统计显著的正向结果**；已跑断言后再叠三路，增益为 0（30/30 vs 30/30，p=1.0），却贵 15.3 倍，且运行失败率更高（2/12 vs 0/12）。

为什么三路救不了审题类错误：candy 陷阱题上三路的错答 5/5 全等于"盲目值"——失败全部发生在**信息提取层**（漏读条件），投票降的是方差、救不了偏差。计算题则相反，错因是零散手算错，断言能救。

> 已作废的数据：30 题批 `runs-c30-c3-sb.jsonl` 的 3.3% / p=1.0 / 盲目率 33%，该批 18/30 条受测量 bug 影响（运行器未等子代理结算即判错）。9 题批未受影响，数字有效。审计见 `benchmarks/accuracy/MEASUREMENT-BUG-2026-09-30.md`。

## 与已知研究的对应

这些结论和已发表的研究一致，便于第三方核验或反驳：

| 维度 | 来源 | 本仓对应 |
|---|---|---|
| 有验证器时采样才转化为性能 | [Large Language Monkeys](https://arxiv.org/abs/2407.21787)（UC Berkeley/CMU） | 断言 ×2.0 显著；三路 ×10.6 增益 0 |
| 定势效应导致漏读改动 | [MisguidedAttention](https://github.com/cpldcpu/MisguidedAttention)；Anthropic 2024-10 为同类问题改过系统提示词 | §3.0 关键条件诊断，+89pp |
| 多智能体从众趋同 85.5% | [arXiv:2605.00914](https://arxiv.org/html/2605.00914)、[arXiv:2503.13657](https://arxiv.org/html/2503.13657v1) | 三路禁止结果前置锚定；`maxDepth:1` |
| 异构模型存在行为纠缠，一致≠独立 | [arXiv:2604.07650](https://arxiv.org/abs/2604.07650) | 执行结果权重高于三路共识 |

## 断言库

门控判定"可写成断言"后，优先复用这里的函数，而不是临时写脚本——复用能消掉手写脚本自身的 bug 和浮点漂移。

Python：`packages/assertions/python/jev_assertions/`

- `tick.py` — Tick 截断、取整方向、网格对齐、反向合约张数
- `margin.py` — 阶梯维持保证金、速算扣除数、正反向强平价
- `slippage.py` — 订单簿 VWAP、Almgren-Chriss 冲击、AMM 滑点
- `calendar.py` — 夏令时切换、单调时钟回退
- `split.py` — 除权除息基准价、前复权收益率、缩股因子

PowerShell：`packages/assertions/pwsh/JevAssertions.psm1`（兼容 PS 5.1 / 7，带 UTF-8 BOM）

⚠ **PS 面与 Python 面能力不对等，不要当成同一套用**（2026-10-01 修）：
Python 面 **18 个**断言，PS 面**只有 3 个**（`Assert-JevTickFloor` /
`Assert-JevTieredMargin` / `Assert-JevSlippageBudget`）——**其余 15 类判定在 PS 上不存在**。
**能用断言判的量化结论，一律优先走下面的 Python CLI**；PS 面只在
「环境确实只有 PowerShell 且只需这 3 类判定」时用。

命令行直接调用全部 18 个断言。

⚠ 下面两条路径是**相对插件根目录**的，只在 `plugins/dsh-jev-preset/` 下成立。
在仓库根（默认会话 cwd）直接照抄会得到 `[Errno 2]`。先定位再用：

```powershell
$JEV = @(Resolve-Path "$env:USERPROFILE\.dsh\profiles\*\node_modules\dsh-jev-preset\packages\assertions\python\jev_assertions\cli.py" -ErrorAction SilentlyContinue | Sort-Object Path)[0].Path
if (-not (Test-Path $JEV)) { $JEV = @(Get-ChildItem . -Recurse -Depth 5 -Directory -Filter jev_assertions)[0].FullName + '\cli.py' }
if (-not (Test-Path $JEV)) { throw "断言库未找到($JEV)" }
```

```powershell
python $JEV --list

python $JEV --func tick_floor --args '{"raw_price": 67432.178, "tick_size": 0.01, "expected": "67432.17"}'
```

> `$JEV` 为空时**必须先 throw**：直接跑 `python $JEV --func ...` 会退化成
> `python --func ...`，报 `unknown option --func` —— 极易被误读为「已执行过」。

输出 JSON。**退出码契约（三值）**：

| exit | status | 含义 | 处置 |
|---|---|---|---|
| `0` | `pass` | 断言通过 | 放行 |
| `1` | `fail` | 断言跑了，**答案错** | 结论不放行，重算或升级三路 |
| `2` | `error` | **调用错，根本没跑**（缺 `--func` / 坏 JSON / 参数不匹配 / 未知断言名 / 断言内部异常） | **先修命令再重算** |
| `3` | `insufficient_data` | **输入不足以判定**（如订单簿深度不够） | **补数据再跑**，重算无意义 |

> exit 2 尤其重要：此时不存在任何数值结论。若把它误当成「断言否定结论」，
> 等于伪造一次从未发生的验证。exit 3 则相反：不是模型算错，是输入不够 ——
> 对它重算是白费力气。该契约由 `tests/test_cli_exit_codes.py` 逐格锁定
> （含不变式 `status == "error" ⟺ exit == 2`）。

> PowerShell 的 `Assert-Jev*` **只有两值**（不通过 = 1，缺参数/未知函数也 = 1），
> 没有 exit 2/3。用 PS 面时须看异常文本判断成因，不能只看退出码。
> 且如上所述，PS 面**只有 3 个函数**，覆盖面远小于 Python 面的 18 个。

## 已落实的防线（和没有的）

已核实：

- **递归阻断** `maxDepth: 1` — 子代理不可再派生，实测孙会话 0，触发抛 `SubagentDepthError`。
- **服务私有隔离域** `isolate` — compaction / delegation 限定在独立 realm，`validate.mjs` 静态核查。

没有的（别当成有）：

- **独立断路器** — 不存在。失败恢复由宿主 `@deepseek-ai/dsh-llm-retry` 提供。`tests/test-circuit-breaker.mjs` 里的只是状态机参考实现。
- **角色互斥锁** — 不存在。三路角色唯一性靠 persona 纪律，无程序化强制，模型仍可能派出两个 Path 3。

## 开发

```bash
npm test              # node 单元测试 + Python 断言 + 题库自检
npm run validate      # 校验 cordis.patch.yml 与 loader 合成规范
npm run test:benchmark  # 30 个量化边界用例清单（注意：见下）
```

`benchmarks/run_stress_matrix.py` 的四个统计指标目前全部返回 `None`——那 30 个用例只是参数清单，三路采样尚未真实执行。历史版本曾输出四行 `100.0%`，那是 `hit = True` 恒真的恒等式，不是测量值，已撤下。下游不要按数字解析历史版本，见 [`docs/benchmark-report.md`](./docs/benchmark-report.md)。

## 协议

[MIT](./LICENSE)
