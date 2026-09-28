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

**JEV 核心突破**:
- **客观门控路由 (Objective Gated Routing)**: 低危任务 Fast-Pass 单次直出，绝不浪费算力；高危任务强制裂变 3 路物理隔离子代理。
- **真·三路隔离采样 (3-Way Isolated Sampling)**: 通过底层 `provider: spawn` 派生内存与上下文完全隔离的 3 个独立子代理（严谨推导者 / 红队对抗者 / 极简执行者）。
- **执行优先裁决与一票否决权 (Pass@k Sandbox)**: 沙箱真实执行断言，代码跑不过一票否决；一致共识快速收敛，分歧经 Jev Rerank 加权重排。

---

## 🏗️ 架构全景

```mermaid
graph TD
    A[用户输入任务] --> B{客观门控路由判定}
    B -->|日常/低危任务| C[Fast-Pass 单次直出]
    B -->|量化/风控/数学/安全/重构| D[强制三路隔离采样裂变]
    
    subgraph 三路物理隔离采样 (Concurrency-Safe)
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

---

## 🧰 内建量化数学与风控标准断言函数库

为消除子代理的推理随机性与浮点数精度漂移，本预设自带 Python / PowerShell 标准断言套件：
- `packages/assertions/python/jev_assertions/`:
  - `tick.py`: Tick 截断、向上/向下取整、网格对齐、反向合约整数张数
  - `margin.py`: 阶梯维持保证金 (MMR)、分段速算扣除数、正反向强平价格
  - `slippage.py`: 深度订单簿 VWAP、Almgren-Chriss 平方根冲击、AMM 滑点、手续费垫资
  - `calendar.py`: 夏令时切换对齐 (EST/EDT)、单调时钟回退检测 (Monotonic)
  - `split.py`: 除权除息基准价、前复权对数收益率安全守卫、缩股因子反向守恒
- `packages/assertions/pwsh/JevAssertions.psm1`: 符合 Windows PowerShell 5.1 / 7 双环境兼容的带 UTF-8 BOM 标准断言模块。

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

1. **递归阻断 (maxDepth: 1)**: 子代理继承预设但被引擎硬性限制最大深度为 1，杜绝无限裂变与孙代理生成。
2. **服务私有隔离域 (isolate)**: `compaction` 与 `delegation` 严格限定于独立 realm，杜绝服务泄漏至 root realm。
3. **断路器与自适应退避**: 对 503 异常、模型超时建立三态断路器 (Closed -> Open -> Half-Open)，配合指数退避安全补派。
4. **角色互斥锁**: 运行时登记 `['Path 1 严谨推导者', 'Path 2 红队对抗者', 'Path 3 极简执行者']`，彻底消除同角色重复派发缺陷。

---

## 📜 开源协议

本项目采用 [MIT 许可证](./LICENSE)。欢迎量化交易员与 AI Agent 开发者共同演进。
