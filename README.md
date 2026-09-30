# dsh-jev-preset

[![CI Status](https://github.com/Yum-wu/dsh-jev-preset/actions/workflows/ci.yml/badge.svg)](https://github.com/Yum-wu/dsh-jev-preset/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![DSH Compatibility](https://img.shields.io/badge/DSH-0.1.7-green.svg)](https://github.com/deepseek-ai)

[English Documentation](./README_EN.md)

**JEV (Judgment-Execution-Verification) 自适应交叉验证模式** agent preset —— 面向 DeepSeek Harness (DSH) 官方生态的工业级标准 bundle。

---

## 🌟 核心理念与解决痛点

在量化金融推导、资金风控计算、安全边界判定与复杂系统重构中，单模型会话存在三大致命风险：
1. **过度自信的虚假自洽**: 单会话模型即使发生严重数值错误，也能给出极其流畅优雅的文字伪证。
2. **同上下文自回归污染**: 在同一上下文让模型“分身多视角分析”，模型后续 token 严格被前文概率所锚定，纯属伪多路。
3. **缺少物理执行真值**: 纸上谈兵无法替代沙箱运行。代码或公式未在真实解释器中执行通过，绝不可作为放行依据。

**JEV 核心突破**(2026-09-30 按实测数据重排优先级):
- **① 断言优先 (Assertion-First)**: 计算/数值类任务**单路作答 + 真跑一次代码复算**。
  实测 30 道计算题:强制复算把正确率 **24/30 → 30/30**(McNemar **p=0.0312**,零例反向),
  成本仅 **×2.0**。这是本项目**唯一统计显著**的正向结果。
- **② 客观门控路由 (Objective Gated Routing)**: 低危任务 Fast-Pass 单次直出;
  仅在**无法写成断言**的高危任务(安全边界、并发/状态机、非唯一数值的取舍)才裂变 3 路。
- **③ 真·三路隔离采样 (3-Way Isolated Sampling)**: 通过 `provider: spawn` 派生上下文完全隔离的
  3 个独立子代理(严谨推导者 / 红队对抗者 / 极简执行者)。
  ⚠ **兜底路径,非默认**:实测已跑断言时再加三路**增益为 0**(10/10 vs 10/10,p=1.0),
  成本却贵 **×10.6**,且运行失败率更高(2/12 vs 0/12)。

---

## 🏗️ 架构全景

```mermaid
graph TD
    A[用户输入任务] --> B{客观门控路由判定}

    B -->|日常/低危| C[Fast-Pass 单次直出]
    B -->|① 计算/数值类,答案可写成断言| P[单路作答]
    B -->|② 无法写成断言的高危任务| D[三路隔离采样]

    P --> Q[真跑代码复算 · 断言]
    Q -->|断言失败| R[不得放行:先修断言]
    R --> D
    Q -->|断言通过| S[输出 [JEV: 断言通过]]

    subgraph 三路物理隔离采样 · 兜底路径 (Concurrency-Safe)
        D --> E1[Path 1 严谨推导者: 第一性原理自底向上推导]
        D --> E2[Path 2 红队对抗者: 专攻极值/除零/溢出/精度陷阱]
        D --> E3[Path 3 极简执行者: 最小代码阶梯 + 沙箱真跑]
    end

    E1 --> F[回收屏障 Barrier / 结算通知]
    E2 --> F
    E3 --> F

    F --> G{沙箱执行 Pass@k 检查}
    G -->|代码执行抛错/断言失败| H[一票否决! 熔断重试或触发补派]
    G -->|沙箱执行通过| I{共识仲裁引擎}

    I -->|3/3 全等收敛| J[输出 [JEV: 3/3 Independent Consensus]]
    I -->|2/3 多数一致| K[输出 [JEV: 2/3 Majority Consensus]]
    I -->|单路崩溃/超时| L[断路器指数退避 -> [JEV: 2/3 + 补派]]
    I -->|不可调和分歧| M[Jev Rerank 终审加权重排]
```

### 手段优先级(实测,2026-09-30)

| 优先级 | 手段 | 效果 | 成本 | 适用 |
|---|---|---|---|---|
| 1 | **题干结构化** | +89pp(5/5 模型) | **×1** | 审题/注意力类缺陷 |
| 2 | **执行断言** | **24/30 → 30/30(p=0.0312)** | **×2.0** | 计算/数值类(可写成断言) |
| 3 | 换异构模型 | +89pp(部分模型) | ×5.4 | 审题类,结构化不够时 |
| 4 | 三路隔离采样 | **增益 0**(p=1.0) | ×10.6 | 仅在既不能断言、又不能换模型时 |

> **机制**:candy 审题陷阱题上三路错答 **5/5 全部是「漏读关键条件」型**(bias,投票救不了);
> numeric 计算题上错答是零散手算错(variance,断言可救)。
> 同一句统计学原理的两面:`voting reduces variance, not bias`。
> 与 [Large Language Monkeys](https://arxiv.org/abs/2407.21787) 一致 —— 只有在**有自动验证器**的领域,
> 增加采样才转化为性能。
>
> 证据:`benchmarks/accuracy/EXP-F-ASSERTION-EFFECT.md`(断言)、
> `EXP-G-THREE-PATH-VS-ASSERTION.md`(三路 vs 断言)、
> `MEASUREMENT-BUG-2026-09-30.md`(此前数据为何作废)。

### 📋 实测证据摘要(全部可复现)

| 结论 | 数字 | 出处 |
|---|---|---|
| **执行断言有效** | 30 题 **24/30 → 30/30**,McNemar **p=0.0312**,成本 ×2.0 | `EXP-F` |
| 断言增益 ∝ headroom | 弱模型 +20.0%(p=0.031)→ 强模型 +6.7%(p=0.5) | `EXP-F` §7 |
| **三路在断言之上无增益** | 30 题 **30/30 vs 30/30**,**p=1.0**,成本 **×15.3** | `EXP-G` §9.3 |
| 三路失败风险更高 | 旧门控 2/12 运行失败(含白烧 86.7 万 token),单路 0/12 | `EXP-G` §10 |
| 题干结构化有效 | **+89pp**,5/5 模型达 100%,成本 ≈×1 | `EXP-D` |
| 三路对审题盲区无效 | 9 题 +33pp 但 **p=0.25**;30 题错答 **5/5 全等于盲目值** | `CANDY-C1-VS-C3` |
| 常规数值题无 headroom | C0 纯推理已 **29/30 = 96.7%** | `DIFFICULTY-CALIBRATION` |
| 递归阻断有效 | `maxDepth:1` → 孙会话 **0**,抛 `SubagentDepthError` | `evidence/p0-depth-limit.log` |

> ⚠️ **已作废的数据**:30 题批 `runs-c30-c3-sb.jsonl` 的 3.3% / p=1.0 / 盲目率 33% / ×6.3
> —— 该批 18/30 条受测量 bug 影响(运行器未等子代理结算即判错)。
> **9 题批未受影响**,数字有效。审计见 `MEASUREMENT-BUG-2026-09-30.md` §8。

---

## 📊 30 个高危量化计算极端边界测试表现

> ⚠️ 诚实性声明（2026-09-28）：下表历史版本曾给出四行 `100.0%`，但那是
> `benchmarks/run_stress_matrix.py` 本地 if-elif 硬编码（`hit = True` 恒真、
> `assert isinstance(expected, dict)` 同义断言）的恒等式，**不是**真实三路隔离
> 采样的测量值（该次会话零 subagent 事件）。数字已全部撤下，见
> [`docs/benchmark-report.md`](./docs/benchmark-report.md) 二节声明。
> 目前**真实可用的实证**只有一条：本仓 [`notes/`](../../notes/jev-three-path-run-2026-09-28.md)
> （一次仓位计算任务的真实 4 子会话隔离采样全归档）。

30 个用例（5 大风险域：Tick 截断 / 阶梯保证金 / 双边滑点 / 时区夏令时 / 复权除零）
目前仅为**用例参数清单**，三路采样尚未真实执行。`benchmarks/run_stress_matrix.py`
的四个统计指标现全部返回 `None`（未测量），不再编造数字。

> 📖 字段口径（`benchmarks/benchmark-results.json`，2026-09-28 起）：
> `path1_avg_convergence_ms` / `path2_attack_hit_rate` / `path3_pass_at_k_rate` /
> `consensus_rate_3_of_3` 四字段恒为 `null`，各配 `*_note` 说明未测量原因；
> 唯一可消费的机器字段是 `case_inventory_count`（=30）与 `results[]` 用例清单。
> 旧版曾输出 `100.0%`，那是恒等式不是测量值，下游**不得**按数字解析历史版本。

---

## 🧰 内建量化数学与风控标准断言函数库(★ 首选路径的核心工具)

> **这是 JEV 实测最有效手段(`EXP-F`:p=0.0312)的落地工具。**
> 门控 §二① 判定"可写成断言"后,应**优先复用这些函数**做真跑复算,
> 而不是自己临时写脚本 —— 复用能消除手写脚本本身的 bug 与浮点漂移。

为消除子代理的推理随机性与浮点数精度漂移，本预设自带 Python / PowerShell 标准断言套件：
- `packages/assertions/python/jev_assertions/`:
  - `tick.py`: Tick 截断、向上/向下取整、网格对齐、反向合约整数张数
  - `margin.py`: 阶梯维持保证金 (MMR)、分段速算扣除数、正反向强平价格
  - `slippage.py`: 深度订单簿 VWAP、Almgren-Chriss 平方根冲击、AMM 滑点、手续费垫资
  - `calendar.py`: 夏令时切换对齐 (EST/EDT)、单调时钟回退检测 (Monotonic)
  - `split.py`: 除权除息基准价、前复权对数收益率安全守卫、缩股因子反向守恒
- `packages/assertions/pwsh/JevAssertions.psm1`: 符合 Windows PowerShell 5.1 / 7 双环境兼容的带 UTF-8 BOM 标准断言模块。

### 命令行一键调用 (Universal CLI Runner)
通过内置的标准泛化 CLI，可一键验证全部 18 个量化与风控断言：
```bash
# 查看所有支持的断言与参数签名
python packages/assertions/python/jev_assertions/cli.py --list

# 传入 JSON 参数执行断言 (返回标准 JSON 结构，通过 exit 0，未通过 exit 1)
python packages/assertions/python/jev_assertions/cli.py --func tick_floor --args '{"raw_price": 67432.178, "tick_size": 0.01, "expected": "67432.17"}'
```

---

## 🚀 快速上手与使用

### 安装与挂载

本预设是面向 DSH 0.1.7 的纯声明式 Cordis Bundle。将本插件目录挂载至 profile 的 Loader 树中：

```yaml
- insert:
    - id: preset-jev
      name: '@deepseek-ai/dsh-agent-preset'
      config:
        id: jev
        name: JEV 自适应交叉验证
        order: 5
        plugins: [ ... ]
```

零运行时依赖、零 `peerDependencies`、不写死 DSH 版本号。

### 本地测试与回归验证

```bash
# 运行全部测试 (JavaScript 单元测试 + Python 断言守护)
npm test

# 运行 30 个高危量化极端边界基准压测
npm run test:benchmark

# 验证 Cordis Patch 语法与 Loader 合成规范
npm run validate
```

---

## 🛡️ 核心安全与工程防线

> ⚠️ **更正声明（2026-09-28）**：本节历史版本列了四条"防线"，其中第 3、4 条
> **不成立** —— `JevCircuitBreaker` 与 `JevRoleRegistry` 两个类**只存在于 `tests/`
> 目录**（`test-circuit-breaker.mjs`、`orchestration-benchmark.mjs`），
> **从未被 `cordis.patch.yml` 或任何运行时路径引用**（已核查：全仓 0 处 import）。
> 它们是**未被接入的死代码桩**，不是"运行时防线"。此类"把测试桩说成已部署防线"
> 的错误与历史上的伪造基准同属**验证剧场 (Verification Theater)**，已按
> [最佳实践指南](https://www.ewok.me/blog/posts/2026-02-28-building-reliable-multi-agent-llm-systems-a-best-practice-guide.html)
> 的告诫予以更正。

**真实存在且已核实的防线（2 条）**：

1. **递归阻断 (maxDepth: 1)**: 子代理继承预设但被引擎硬性限制最大深度为 1，杜绝无限裂变与孙代理生成。
   已端到端实证：`tools/verify-depth-limit.mjs` 全绿，孙会话数量为 0。
2. **服务私有隔离域 (isolate)**: `compaction` 与 `delegation` 严格限定于独立 realm，杜绝服务泄漏至 root realm。
   已由 `validate.mjs` 静态核查通过。

**降级为"设计参考"（非运行时防线）**：

3. ~~断路器与自适应退避~~ → 仅为 `tests/test-circuit-breaker.mjs` 中的**状态机参考实现**。
   运行时实际的失败恢复由宿主 `@deepseek-ai/dsh-llm-retry` 提供
   （normal mode：`RATE_LIMIT`/`SERVER`/`TIMEOUT`/`TRANSPORT`/`EMPTY_RESPONSE` 最多重试 6 次）。
   JEV 自身**没有**独立断路器。
4. ~~角色互斥锁~~ → 仅为 `tests/orchestration-benchmark.mjs` 中的**设计参考**。
   运行时角色唯一性**靠 persona 纪律**（派发前自行核对 Path1/2/3 不重复），
   **无程序化强制**。这是已知弱点：模型仍可能派出两个 Path 3。

---

## 🔬 业界公认基准与学术验证依据 (Academic & Industry Benchmarks)

JEV 的设计思想与实测有效性与顶尖工业界、学术界的权威研究成果高度收敛：

| 验证维度 | 对应公认基准 / 论文 | 学术与工业界核心结论 | JEV 模式工程落地与实测效果 |
|---|---|---|---|
| **代码物理执行优先** | **Large Language Monkeys**<br>([arXiv:2407.21787](https://arxiv.org/abs/2407.21787), UC Berkeley / CMU) | 增加采样或多模型投票只有在**存在确定性代码验证器 (Execution Verifier)** 的场景下才能产生突破，否则性能迅速饱和。 | **EXP-F 实证**：30 道复合计算题纯推理仅 24/30 (80%)，强制代码复算提升至 **30/30 (100%)**，McNemar **p = 0.0312**（零例反向）。 |
| **定势思维审题盲区** | **MisguidedAttention**<br>([GitHub](https://github.com/cpldcpu/MisguidedAttention) / Anthropic 2024-10 Release) | 大模型因训练集记忆产生“定势效应 (Einstellungseffekt)”，极易漏读微调条件。**Anthropic 官方专门为此要求“显式引用原句列出约束”**。 | **§3.0 门控原句诊断**：在糖果定势题上，普通模式盲抽答错 (24)，JEV 识别手感可辨约束并真跑 9720 维全状态搜索命中全局最优解 (14)。准确率 **+88.9pp (5/5 模型 100%)**。 |
| **多 Agent 防从众与防暴走** | **MASFT 多智能体故障分类**<br>([arXiv:2503.13657](https://arxiv.org/html/2503.13657v1), UC Berkeley) | 多智能体无隔离时存在 **85.5% 从众趋同**；FC3 缺陷揭示多 Agent 最普遍失败是“不知道何时该停 (Unaware of stopping conditions)”。 | **防锚定铁律 + maxDepth: 1**：禁止结果前置传入子代理，限制递归深度为 1，单路补派硬设 1 次上限，根除无限裂变与 Token 消耗风暴。 |
| **共识代价与纠缠偏差** | **The Cost of Consensus**<br>([arXiv:2605.00914](https://arxiv.org/html/2605.00914) & [arXiv:2604.07650](https://arxiv.org/abs/2604.07650)) | 未隔离的同伴交流导致语境脆弱（最高 70% 推翻正确答案），且异构模型间存在预训练纠缠（共识不等于正确）。 | **执行断言一票否决权**：物理代码执行 (Pass@k) 权重大于一切文字与三路共识，彻底粉碎语言自洽伪证。 |

---

## 📜 开源协议

本项目采用 [MIT 许可证](./LICENSE)。欢迎量化交易员与 AI Agent 开发者共同演进。
