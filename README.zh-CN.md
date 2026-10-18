# dsh-yum-preset

[![CI](https://github.com/Yum-wu/dsh-yum-preset/actions/workflows/ci.yml/badge.svg)](https://github.com/Yum-wu/dsh-yum-preset/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Platform: DeepSeek Harness](https://img.shields.io/badge/Platform-DeepSeek%20Harness-black.svg)](https://github.com/deepseek-ai/deepseek-harness)

> [English](README.md) | **简体中文**


**面向 [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness)（DSH）的自适应交叉验证与客观真值护栏（JEV 架构）。**

它解决大模型在软件工程、复杂逻辑推导与关键决策中的核心痛点：**拒绝自回归自嗨，让大模型在给出关键结论之前，先真跑代码/测试把事实跑对；遇到高危不确定性决策，通过物理隔离多路采样交叉验证。**

---

## 💡 它解决什么（通用工程与多领域决策）

大语言模型（LLM）在面对复杂任务时有三大经典失效模式：

1. **算错/测错但表述极度自洽**：错误结论常被一段流畅且看似合理的推导逻辑包装，人工肉眼复核极难发现。
2. **同会话多视角自欺（自回归污染）**：在同一个会话中让模型“分三个视角辩驳”，后文必定被前文的概率采样所锚定，并非真正的独立多路。
3. **缺乏物理真值（Execution-First）**：代码改动未跑测试、数学公式未过解释器验证，无论语言多么自信，都是潜在的逻辑漏洞。

JEV 架构将任务严格分级：**日常任务单次高速直出；确定性任务单路写出后必须真跑代码/测试验证；重大取舍与并发架构裂变为物理隔离的三路异构模型并行求解。**

- **「先跑 20 条」不是一句承诺,是一个能跑的模块** —— `small_sample.py` 输出**预注册块**(`case_ids` + `sha256` + 覆盖度),第三方拿 `(suite, n, seed)` 可独立重建。
- **准入规则要能防新增,不能只列一次性修复清单** —— T3 改成**棘轮**:遗留清单冻结、新增漏网即红、清单里修好一个也必须删一行(只往紧的方向转)。

---

## 🚀 快速开始（安装）

这是一个标准的 DSH bundle：一个 npm 包，携带一层 `cordis.patch.yml`，挂进 profile 的 loader 树。

```bash
dsh plugin --profile <你的 profile> add dsh-yum-preset
```

装完后校验配置层已生效（不必启动服务）：

```bash
dsh --profile <你的 profile> --dump-config
```

预期能看到一行 `# == dsh-yum-preset`。然后启动 DSH 即可在会话预设列表里选到 **JEV 自适应交叉验证**。

卸载走同一入口：`dsh plugin --profile <你的 profile> remove dsh-yum-preset`。

> 本 bundle 不声明任何 `dependencies` / `peerDependencies`，也不写死 DSH 版本号 ——
> 声明行自带 `inject = ["agentPresets"]`，由 loader 等注册表就绪后激活，子插件路径由宿主
> `@deepseek-ai/dsh-agent-preset` 的 baseUrl 解析。0.1.7 起实测可用，0.2.0-rc.2 上验证通过；
> 0.2.1-rc.2 上子代理身份迁进独立预设（见下文「子代理身份：独立预设」）。

### 🔗 运行时半区：自动思考程度（2026-10-05 起，2026-10-13 合体进本包）

JEV 的提示词半区是**纯提示词**；它的三路隔离采样与结构化重算都以「按任务复杂度选思考档位」为前提 ——
档位太低，断言算错没人发现。这段逻辑 2026-10-13 起**就在本包里**：

| | |
|---|---|
| 代码位置 | 本包 `lib/`（`index.js` 运行时插件、`auto-reasoning.js` 计分、`jev-client.js` SystemOne 通道、`client.js` 胶囊） |
| 声明位置 | 与 `preset-yum` **同一个 insert 组**里的第三条声明行（`id: plugin-yum-runtime`，自挂本包） |
| 做什么 | ① 把模型配置里的 `reasoningEffort: auto` 哨兵换算成该模型自己的合法档位；② 数「本轮实际发射了几路」（发射台账） |
| 历史 | 2026-10-05 → 2026-10-13 期间它在**另一个 npm 包** [`dsh-auto-reasoning`](https://github.com/Yum-wu/dsh-auto-reasoning) 里，由本 bundle 的这行**引用**进来 |

#### 为什么合体：同 id 重复会**静默覆盖**，而不是报错

合体前本 bundle 的那行是 `id: plugin-auto-reasoning` / `name: 'dsh-auto-reasoning'`，
而 `dsh-auto-reasoning` **自己也是 bundle** —— 它的 `cordis.patch.yml` 插入**同 id** 的行。
实测（2026-10-13，预检脚本 `compose-check.mjs` 走运行时自己的 `loadProfileDirectory` + `composeEntries`）：
合成层确有 **2 条** `plugin-auto-reasoning`。

> ⚠ 本仓 2026-10-05 那版注释写的「Loader entry id 重复会让 profile 起不来」在 **0.2.0-rc.2 上不成立，已推翻**：
> `@deepseek-ai/cordis-plugin-loader/src/config/group.ts:48-65` 的 `EntryGroup.update()` 用
> `Object.fromEntries(config.map(o => [o.id, o]))` 建映射 ⇒ **同 id 只创建一条 entry，后者胜**
> （`this.tree.store[id] ??= new Entry(...)` 复用同一实例）。全仓 grep `duplicate loader entry id` = **0 命中**。
>
> 真正的危害是**静默覆盖**：bundle 层顺序 = `dsh.profile.bundles` 顺序，`dsh-auto-reasoning`
> 当时排在本包**之后** ⇒ 它自己那条赢，**本包写在该行 config 里的值全部失效**。

合体后本包**自挂**（`name: 'dsh-yum-preset'`），同 id 重复的入口消失。
`node validate.mjs` 会校验「每条 preset 声明行的 config.id / 结构 / isolate / 子插件可解析」，
附属声明行必须是 `plugin-yum-runtime` 且自挂本包，
并**显式否决**旧的 `plugin-auto-reasoning` 形态。

#### ⚠ 安装 / 升级须知

- **全新安装**：只需装本包，运行时半区随包自带，**不必**再 `add dsh-auto-reasoning`。
- **从 2026-10-13 之前的版本升级**：若你的 profile 的 `dsh.profile.bundles` 里列了
  `dsh-auto-reasoning`，**必须移除** —— 否则它自己的 bundle 层会再挂一份旧代码，
  两个实现同时接管 `agent/request`。
  判据：profile 的 `cordis.patch.yml` 里 `plugin-codemode` 段的注释曾说明这一点。
- **profile 的 `cordis.patch.yml` 不得再单独 insert `plugin-yum-runtime`** ——
  同 id 重复会按上面的规则**静默覆盖**（不是报错，更难查）。
- ⚠ **连带取舍**：卸载 jev preset = 一并失去档位换算，思考档位回落到**模型默认档**
  （不是 `high` —— 哨兵没了就没有任何人做换算）。
- ⚠ **auto 只对新会话生效**。宿主 `dsh-agent` 的后置拾取器只认 session request header 里
  持久化的 UI 选择，改配置对已有会话无效。

#### 子代理身份：独立预设（2026-10-17 起）

`subagent` 每派一次，子代理的 persona 与工具面都由一个 **Agent Preset** 决定。
0.2.0 之前本包把覆盖用的 `persona:` 直接写在 `tool-subagent` 行上；**0.2.1-rc.2** 起
`dsh-tool-subagent` 的 `apply()` 见到该键就抛：

```
tool-subagent: persona is no longer supported; configure persona and tool plugins
in an Agent Preset and select it with agentPreset (spawn only)
```

抛点在**preset 挂载时**，不是启动时 —— 宿主照常响应，而**任何**用 `agentPreset: jev`
（含注册表 default）建会话的路径都以 `agent-preset/invalid` 失败。2026-10-17 本机实测：
`POST /api/session/create` 可复现该错，同时 DSH 进程健康、端口在听。
用户侧看到的现象就是「DSH 更新后起不来了」。

迁移：多一条声明行 `preset-yum-executor`（`config.id: yum-executor`），它自带执行者 persona
**和**整套工具行；`tool-subagent` 行只剩 `agentPreset: jev-executor`。
⚠ 独立选中的 preset **不继承**父 preset 的组合（`dsh-subagent/README.md`：显式 id 挂载的是
当前可用修订，不是父组合），所以两份 plugins 列表必须逐行一致；唯一允许的差异是
`delegation` 组 —— 执行者预设里**没有**它，递归阻断由此从「提示词自律」变成「结构上无工具可调」。
漂移守卫：`tests/test-subagent-preset-migration.mjs`。

#### 发射台账（2026-10-13 加）

persona §三 3.1 要求「裁决时记录本轮实际发射数（含补派）」，过去**纯靠模型自觉** ——
实测 C3F 30 题里 11 题（36.7%）派出 4~5 路而标识仍写 3/3。现在同一事实由**运行时**计数：
在 `subagent` / `subagent_fork` / `workflow` 的结果尾部追加一行台账，
并在 `GET /api/auto-reasoning.effort` 的 `emissions` 字段里暴露（按会话、随新一轮用户消息重置）。
配置开关 `emissionLedger`（默认 `true`）。判分器**不校验**标识里的数字，这是唯一的事后审计入口。

> ⚠ 若你的 profile 里 `plugin-codemode` 配了 `autoReasoning: true`，请删掉。
> 该键已于同日从 codemode 移除；cordis 按整条 entry 校验配置，未知键会让
> 整条 `plugin-codemode` 不激活，表现为「codemode 工具凭空消失」。

---

## 🧭 门控决策：什么时候做什么

模型按客观条件动态判定执行路径，无需用户人工介入：

| 任务类型 | 范例场景 | 执行路径与仲裁规则 |
|---|---|---|
| **日常 / 低危** | 语法查询、常规问答、日志查看、单文件小改 | **Fast-Pass**：单次快速直出，不浪费额外算力 |
| **确定性计算 / 逻辑推导** | 数值计算、参数推导、规则判定、数据转换、单元测试 | **单路作答 + 真跑代码复算**：客观断言通过才放行，代码结果压过文字自洽 |
| **高危 / 架构决策** | 并发状态机、鉴权安全、重大重构方案取舍 | **裂变 3 路物理隔离采样**：派出 3 个异构子代理独立求解，由主线程重排裁决 |
| **客观断言失败 / 语法异常** | 测试跑错、断言失败、数据不守恒 | **立即拦截**：先修复断言与数据，无法收敛时自动升级至 3 路采样隔离仲裁 |

**门控判不出来时怎么办**（2026-10-13 加，照 magpie 的 intent 分类器失败矩阵）：

门控是助手，不是闸门 —— 判不出该走哪条路时**绝不阻塞交付**：按最保守的路径走完，并把「判不出来」的原因显式写进结论。静默降级是排障灾难。

- 三类特征都不命中（既非数值计算、也非高危、也非日常）→ Fast-Pass 单次直出。
- 命中高危但多路发射能力不可用（无 subagent 工具 / 路由不足）→ 降级单路，标 `[JEV: 单路未验证]`，写明是「能力不可用」而非「判定为单路」。
- 断言库不可用（CLI 定位不到 / 环境缺 python）→ 先定位；定位失败则**不得声称跑过断言**，改走 Fast-Pass 或三路。
- 断言 `exit 2`（调用错，根本没跑）→ 先修命令再重算；此时不存在任何数值结论，严禁当成「断言否定了结论」。
- 断言 `exit 3`（输入不足以判定）→ 补数据再跑，重算无意义。
- 同一手段本轮连续失败 2 次 → 该手段本轮休息，不再重试，换下一条路径并写明换了哪条。

> 本矩阵**不新增标识** —— 只规定「判不出来时用哪个既有标识」。新增标识会同时改判分器白名单与附录状态表。

---

## ⚡ 真实实测数据对比（学术级基准）

所有数据来自本仓 `benchmarks/accuracy/` 下可复现的评测矩阵：

| 验证机制 | 准确率提升 | 边际成本 | 统计显著性 (McNemar) |
|---|---|---|---|
| **题干关键条件结构化** | +89pp（5/5 模型达 100%） | **×1.0** | 彻底消除审题漏读偏差 |
| **执行断言真跑 (Execution-First)** | **24/30 → 30/30 (100%)** | **×2.0** | **p=0.0312 (统计学显著)** |
| **换异构大模型** | +89pp（部分模型） | ×5.4 | 消除同款模型系统性盲区 |
| **单纯同模型 3 路投票** | 增益 0 | ×10.6 | **p=1.0 (无显著增益)** |

> **核心结论**：**“执行断言真跑”是本仓唯一统计显著的正向提质手段**。若缺乏物理执行器检验，单纯在同会话中增加投票轮次只会增加 10 倍以上 Token 消耗，却无法纠正模型的先验理解偏差。

---

## 🔬 业界研究对应与学术背书

这些设计与前沿大模型工程研究高度吻合：

| 理论维度 | 顶级学术文献 / 业界实践 | JEV 架构对应实现 |
|---|---|---|
| **采样必须配合验证器才有效** | [Large Language Monkeys](https://arxiv.org/abs/2407.21787) (UC Berkeley/CMU) | 强调代码断言优先（×2.0 显著，消灭无序盲投） |
| **定势效应导致漏读上下文** | [MisguidedAttention](https://github.com/cpldcpu/MisguidedAttention) / Anthropic 2024 系统提示词改进 | §3.0 关键条件结构化诊断，准确率提升 89pp |
| **多智能体从众趋同陷阱** | [arXiv:2605.00914](https://arxiv.org/html/2605.00914) / [arXiv:2503.13657](https://arxiv.org/html/2503.13657v1) | 3 路必须采用子进程物理隔离，严禁前文锚定上下文 |
| **异构模型行为纠缠** | [arXiv:2604.07650](https://arxiv.org/abs/2604.07650) | 代码物理执行结果权重永远高于文字共识 |

---

## 🛠 内置标准断言库

门控判定“可写成断言”后，优先复用本套断言库，避免临时手写脚本引入浮点漂移或实现 bug。

- **Python 端（全量 18 个核心断言）**：`packages/assertions/python/jev_assertions/`
  - 涵盖数值截断对齐、阶梯维持计算、订单簿与滑点冲击、时区与日历切换、收益率复权等。
- **PowerShell 端（轻量 3 个核心断言）**：`packages/assertions/pwsh/JevAssertions.psm1`
  - 提供 `Assert-JevTickFloor`、`Assert-JevTieredMargin`、`Assert-JevSlippageBudget`。

⚠ **PS 面与 Python 面能力不对等，不要当成同一套用**：
Python 面 **18 个**断言，PS 面**只有 3 个**（`Assert-JevTickFloor` / `Assert-JevTieredMargin` / `Assert-JevSlippageBudget`）——**其余 15 类判定在 PS 上不存在**。能用断言判定的结论，一律优先走 Python CLI；PS 面仅在纯 PowerShell 极简环境且只需这 3 类判定时使用。

### 命令行调用规范与退出码契约

```powershell
# 1. 动态定位断言 CLI 入口
$JEV = @(Resolve-Path "$env:USERPROFILE\.dsh\profiles\*\node_modules\dsh-yum-preset\packages\assertions\python\jev_assertions\cli.py" -ErrorAction SilentlyContinue | Sort-Object Path)[0].Path
if (-not (Test-Path $JEV)) { $JEV = @(Get-ChildItem . -Recurse -Depth 5 -Directory -Filter jev_assertions)[0].FullName + '\cli.py' }
if (-not (Test-Path $JEV)) { throw "断言库未找到($JEV)" }

# 2. 列出可用断言或执行判定
python $JEV --list
python $JEV --func tick_floor --args '{"raw_price": 67432.178, "tick_size": 0.01, "expected": "67432.17"}'
```

**四值退出码契约（Exit Code Contract）**：

| Exit Code | Status 状态 | 含义解释 | 正确处置动作 |
|---|---|---|---|
| **`0`** | `pass` | 断言物理验证通过 | 结果可信，放行结论 |
| **`1`** | `fail` | 断言执行完毕，**计算/逻辑结果错误** | **拦截结论**，重新检查推导 |
| **`2`** | `error` | **调用异常，根本未执行**（坏 JSON、缺参数、脚本内部错） | **严禁当作验证失败！先修命令再跑** |
| **`3`** | `insufficient_data` | **输入数据不足以支撑判定**（如深度缺失） | **补充输入数据**，重算无意义 |

---

## 🛡 系统边界：已落实的防线（和没有的）

已核实：

- **递归阻断** `maxDepth: 1` — 子代理不可再派生，实测孙会话 0，触发抛 `SubagentDepthError`；2026-10-17 起执行者预设里**根本没有** `subagent` / `workflow` 行，无从调用 —— 深度限制退为第二道。
- **服务私有隔离域** `isolate` — compaction / delegation 限定在独立 realm，`validate.mjs` 静态核查。
- **断言库护栏逐条覆盖** — 护栏补测与变异测试（`mutation testing`）全量覆盖，通过反向与变异用例杜绝假绿。
- **退出码契约四值互斥** — 四值退出码由单测逐格锁定，杜绝将调用错误误报为计算错误。
- **18 项断言逐项 CLI 可达** — 每项都用一组经复算的正确值调用并要求 `status=pass`；18 项全部通过。
- **跨实现一致性** — PS 面 3 个函数与 Python 侧算法与舍入严格对齐，由 C3 用例锁定。
- **变异测试基础设施** — 判据入库在临时副本上变异验证，杜绝空转。
- **G5 规避率全流程审计** — 建立预注册台账与规避监控脚本，严密监控模型违背指令的逃逸行为。
- **结构性边界门控与循环终止判据 (Boundary Check & Termination)** — `tools/boundary_check.py` 提供机械化门控: 候选缺陷命中已声明结构性边界（B1–B7 / H1–H5）输出 `exit 3` 拦截; 连续多轮缺陷属于同一形态输出 `exit 4` 终止自优化循环; `--scan-rot` 提供文档与注释可腐烂值扫描 (R17)。

没有的（别当成有）：

- **独立断路器** — 不存在。失败恢复由宿主 `@deepseek-ai/dsh-llm-retry` 提供，非硬件级独立断路器。
- **角色互斥锁** — 不存在。三路角色唯一性靠 persona 提示词纪律，无操作系统级进程互斥。
- **PS 面的完整覆盖** — PS 面只有 3 个函数，Python 面有 18 个，其余 15 类在 PS 上不存在。
- **仓内真正的防篡改** — 不存在。台账审计依赖 Git HEAD 基线锚，非区块链去中心化防篡改。

---


## 🧭 自优化轮次(R68 起)

> ⚠ **本节在 Round 79 被发现整段缺失**(README_EN.md 有 8 条,README.md 0 条),**没有任何判据守着文档内容**。权威轮次记录在 `docs/self-optimize-rounds.md`。

- **R73–R76:「凡在两台账上取值巧合一致的变异,全部不可见。」** 四轮连续收口,每轮都被红队当场证明**还差一层**。**R73** 把鉴别力从一个变异类推广成**预注册矩阵**(6 类 × 5 数 = 30 格,集合完全相等才算过)—— 红队立刻给出 2 条【严重】:聚合方向(`sum`→`len({结算轮})`)与放宽方向(`n<1 or n>9999`)**全套件 `Ran 24 OK`** 而值真的算错。**R74** 加**第三张台账**(形状刻意不同:同一轮内两条**同值**不可解析行、一条 `结算轮=100000`、同一轮多条同轮行)→ 聚合四连 **4/4 真检出**;⚠ 我第一版把两条不可解析行放在**不同轮** → 照样全绿 —— 根因 `build_report` **按轮**算完再求和,**聚合变异只有在同一轮内有重复值时才露馅**。**R75** 把人类面断言从 `assertIn("… 4 条")`(红队证明它**既过严又过松**)改成**数值正则 + 三张台账全钉**。**R76** 修**自洽循环**:`backfilled_evaded` 的期望值**取自生产自己的 JSON** ⇒ 恒等,红队 N1b(`min(1,sum)` 按轮封顶)全套件全绿而真值 99 被报成 23 —— 现改为**独立重算 + 预注册常量**;`re.search` → `re.findall` 且断言**恰好命中 1 处**。⚠ **未修**:F-4 规则同源、真台账四数零守卫、跨运行漂移(需**外部锚**)。⚠ **记账缺口**:红队 R75 查出**台账只到 72、rounds 文档里搜不到 R73/R74** —— R76 补记。**「靠记性堵不住,只能靠机制」第六次实例。**
- **R78–R79:变异判定框架本身 —— 崩溃 ≠ 检出。** 红队 R77 反证我一条声称,我复核跑出 `rc=1` **看似红**,但 `Ran 25 tests in 1.7s` **快得反常** —— 追下去:**25 条全是 ERROR,直接跑审计报 `SyntaxError`**。根因:**我的变异锚点是「多行 f-string 的第一物理行」**,插在它后面会切断语句拼接;而我的判定只看 `rc != 0 and "Ran " in out` ⇒ **把崩溃记成了检出**。红队 R78 进一步实测:崩溃会产生 `Ran 25 tests` + **13 条真 `FAIL:` 行**。**这正是本仓老病「我跑了变异 ≠ 我跑到了该跑的那条」的第三次复发。** 修:三分(崩溃/等价/真检出)做成机制 `tools/mutation_harness.py`(**在仓内**,带判据自检与沙箱路径护栏)。⚠ 红队随即抓到**这个新框架自己的两个 bug**:① 预检 grep `Traceback` 误伤 `tests/`(**unittest 的 FAIL 块本身就含这一行**)⇒ 把真检出改判成崩溃;② `classify` 对**测试数完全免疫**。均已修 —— **但「用例被阉」仍不可见**。另:归一化改按 **Unicode 字符类别**剥 `Cf`/`Mn`(**类别规则,不是清单**),堵住 U+00AD;⚠ 繁体 `條`、汉字数字、词分隔 `共` 这类**语义同形**仍能绕过。**「靠记性堵不住,只能靠机制」第七次实例。**

## 🧪 自动化测试套件

```bash
npm test                    # 全量（Node 单元 + Python 断言/审计/形状守卫 + 双版本 PowerShell 兼容性）
npm run audit:evasion       # 跑 G5 规避审计，**并自动提交** docs/evasion-audit.log
npm run audit:evasion:nocommit  # 同上但不提交（只看结果时用）
npm run validate            # 校验 cordis.patch.yml 编排规范

> ⚠ 为什么审计后必须提交：`tools/evasion_audit.py` 的防篡改基线读的是 `git show HEAD:docs/evasion-audit.log`。
> 不提交 = HEAD 里的日志停在旧值 = 基线停滞 = 回退检测灵敏度逐轮衰减。该文件每轮 dirty 是设计使然，但必须每轮提交掉。
> ⚠ 另：`npm test` 链里的 G5 门也会跑审计并追加日志，所以**跑完测试后它同样会 dirty**。
```

---

## 💡 开源致谢与前沿借鉴 (Acknowledgements & Prior Art)

本预设早期把「自动化思考深度调节（Auto Reasoning Effort）」写进了 persona，要求模型自己在回复首行报一个 `Auto (<level>)` 审计标签。**2026-10-04 已删除该段**：标签是模型自估的，与真实档位无关（实测 12 轮里 4 轮档位不一致，11/12 一律说 `low`）。调节逻辑现由独立插件 `dsh-auto-reasoning`（**2026-10-05 从 codemode 拆出的独立插件**，<https://github.com/Yum-wu/dsh-auto-reasoning>）在 `agent/request` 上**确定性算出并改写**，真实档位显示在输入框下方的 Auto 胶囊，可经 `GET /api/auto-reasoning.effort` 读取。下列开源项目是该插件的设计来源：

- **[luckeyfaraday/auto-reasoning](https://github.com/luckeyfaraday/auto-reasoning)** (MIT License): 借鉴了面向 Agentic AI 任务的确定性复杂度计分、固定模型防漂移阶梯以及全链路可追溯的审计事件流（`classified` / `effort_selected` / `effort_escalated`）设计思想。
- **[ruban-24/switchboard](https://github.com/ruban-24/switchboard)** (MIT License): 借鉴了模型/思考度动态路由体系以及会话级 `Auto (<level>)`（如 `Auto (low)`、`Auto (medium)`、`Auto (high)`、`Auto (max)`）的状态感知表示约定。
- **[@pixu1980/pi-reasoning](https://pi.dev/packages/@pixu1980/pi-reasoning)**: 借鉴了轻量级状态指示器与阶梯状态定义。

---

## 📄 开源协议

本项目采用 [MIT License](./LICENSE) 开源协议。