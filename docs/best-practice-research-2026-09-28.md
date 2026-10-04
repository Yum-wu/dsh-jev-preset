# JEV 模式结论汇总与第三方验证指南(2026-09-28)

> **本文用途**:汇总截至 2026-09-28 关于 `dsh-jev-preset` 的**全部结论**,
> 供**独立会话/第三方复核**。每条结论标注:
> **证据强度**、**验证命令**、**当前状态**。
>
> **阅读约定**:
> - ✅ 已实证 = 有可复现的命令输出或可查的会话 ID
> - ⚠️ 部分实证 = 有证据但有混杂因子/样本不足
> - ❌ 未验证 = 设计判断或引用他人研究,本机未测
> - 🚫 已证伪 = 曾宣称但核查不成立(已更正)
>
> **复核原则**:凡标 ✅ 的,请用给出的命令自行复现;复现不出即视为该结论不成立。

---

## 零、快速复核入口(5 分钟)

```powershell
cd plugins/dsh-jev-preset

# 1. 静态契约(应全绿)
node validate.mjs                  # 期望 exit 0,末行"静态校验全部通过"
node validate-official.mjs         # 期望 exit 0,末行"官方代码路径验证全部通过"

# 2. 单元 + 断言(应全绿)
npm test                           # 期望 node 5/5 pass + python 5 tests OK

# 3. 运行时冒烟(需 DSH web 在跑,读 ~/.dsh/web-url.txt)
node smoke.mjs                     # 期望全 PASS,jev 在册 order=5

# 4. 递归阻断端到端(需 DSH web 在跑)
node tools/verify-depth-limit.mjs  # 期望"递归阻断验证全绿",孙会话=0

# 5. 子代理结算健康度(需 DSH web 在跑)
node tools/audit-subagent-settlement.mjs --limit 20
#   退出码 1 = 检出限流失败;退出码 0 = 采样内无限流

# 6. 成本审计(需 DSH web 在跑)
node tools/audit-subagent-cost.mjs --limit 20
```

**CI 复核**:<https://github.com/Yum-wu/dsh-jev-preset/actions>
最新提交 `07a9f17`,CI 状态 = success(ubuntu/windows × node 20/22 四矩阵)。

---

## 一、🚫 已证伪的宣称(重要:这是本项目的诚信基线)

### 1.1 伪造的基准数字(2026-09-28 首次发现,已清理)

| 原宣称 | 真相 | 证据 |
|---|---|---|
| `path2_attack_hit_rate: 100.0%` | `run_case_path2` 内 `hit = True` **硬编码恒真** | `benchmarks/run_stress_matrix.py` 文件头声明 |
| `path3_pass_at_k_rate: 100.0%` | 断言为 `assert isinstance(expected, dict)` **同义反复** | 同上 |
| `consensus_rate_3_of_3: 100.0%` | 三条"路径"同源于**同一份 Python 代码**,非独立采样 | 同上;该次会话 **subagent 事件数 = 0** |
| `path1_avg_convergence_ms: 0.0` | 本地算术无模型延迟,是对 CPU 噪声的测量 | 同上 |

**复核命令**(⚠️ 必须显式指定 UTF-8,Windows Python 默认按 GBK 读会报 `UnicodeDecodeError`):
```powershell
cd plugins/dsh-jev-preset
python -c "import json,io; d=json.load(io.open('benchmarks/benchmark-results.json',encoding='utf-8')); print(d['path2_attack_hit_rate'], d['path3_pass_at_k_rate'], d['consensus_rate_3_of_3'], d['path1_avg_convergence_ms'])"
# 期望输出: None None None None(全部为 null,且各带 *_note 说明)
```

**当前状态**:数字已全部撤下改为 `null`;README / `docs/benchmark-report.md` /
`docs/performance-spec.md` 三处已加诚实性声明。

### 1.2 死代码被宣称为"运行时防线"(2026-09-28 发现,已更正)

| 原宣称 | 真相 | 核查方法 |
|---|---|---|
| README §防线 3:「**断路器与自适应退避**…建立三态断路器」 | `JevCircuitBreaker` **只存在于 `tests/`**,从未接入 `cordis.patch.yml` | `Select-String -Path cordis.patch.yml -Pattern 'CircuitBreaker\&#124;断路器'` → **0 匹配** |
| README §防线 4:「**角色互斥锁**…彻底消除同角色重复派发」 | `JevRoleRegistry` 同上,**全仓 0 处 import** | `Select-String -Path *.mjs,tools/*.mjs -Pattern 'JevRoleRegistry'` → **0 匹配** |

**性质**:属生产实践指南定义的 **Verification Theater(验证剧场)** ——
把测试桩说成已部署防线。与 1.1 的伪造基准同源。

**复核命令**:
```powershell
cd plugins/dsh-jev-preset
Select-String -Path cordis.patch.yml -Pattern 'CircuitBreaker|RoleRegistry|断路器|角色互斥'
# 期望:无输出(空)
Select-String -Path tests/*.mjs -Pattern 'class JevCircuitBreaker|class JevRoleRegistry'
# 期望:命中 tests/test-circuit-breaker.mjs 与 tests/orchestration-benchmark.mjs
```

**当前状态**:README + `docs/architecture.md` + `docs/orchestration-analysis.md`
三处已加更正声明,区分「真实防线(2 条)」与「设计参考(非防线)」。

**遗留弱点(未修)**:角色唯一性**无程序化保障**,仅靠 persona 纪律。
`toolFilter.deny` 路线已被证伪(`tools.restrict()` 只接受全局工具名,
见 `cordis.patch.yml` 注释),**暂无已知运行时拦截手段**。

---

## 二、✅ 已实证的结论

### 2.1 预设正确注册且可切换

| 项 | 值 | 验证 |
|---|---|---|
| preset id | `jev` | `node smoke.mjs` → "PASS id=jev 在册" |
| 显示名 | `JEV 自适应交叉验证` | 同上 |
| order | `5` | 同上 |
| 激活诊断 | `broken` 字段不存在(全部行激活成功) | 同上 |

**证据文件**:`evidence/p3-smoke.log`

### 2.2 递归阻断(maxDepth: 1)端到端生效

**结论**:子代理(depth 1)无法派生孙代理(depth 2),引擎抛 `SubagentDepthError`。

| 层 | 断言 | 结果 |
|---|---|---|
| 引擎级 | depth=0 派生 depth=1 | 允许(childDepth=1 ≤ maxDepth=1) |
| 引擎级 | depth=1 派生 depth=2 | **被拦截** → `subagent depth 2 exceeds maxDepth 1` |
| 端到端 | 真实 JEV 会话诱导递归 | **孙会话数量 = 0** |

**证据**:`evidence/p0-depth-limit.log`;测试会话 `session-484d7dbc-c8d6-495d-829b-015c911608d4`

**复核命令**:`node tools/verify-depth-limit.mjs`

**⚠️ 独立佐证**:2026-09-28 另一次长程会话实测派生 **17 个子会话,孙会话 0 个**
(见 `session-b515a761-7b46-4b4b-a47f-b4f5c3a1da35` 的 `subagentCatalog`)。

### 2.3 bundle patch 走官方代码路径可安全安装

| 检查项 | 结果 |
|---|---|
| 官方 `loadOverlayPatches` 解析 | OK,1 个 patch 条目 |
| `!!js` 保留为节点(未求值) | OK,`process.platform === 'win32'` 等 2 处 |
| 官方 `applyEntryPatches` 合入 | OK,无跳过 |
| preset id 无冲突 | `standard, ptc, minimal, cordis, jev` |
| Loader 行 id 无冲突 | 6 行 |
| `insert` 语义 | 追加(与官方一致);**单次加载只应用一层** |
| 原始树未被 mutate | OK(structuredClone 保护) |

**证据**:`evidence/p0-workflow-ptc-check.log`;**复核命令**:`node validate-official.mjs`

### 2.4 三路隔离采样真实跑通(5 个量化用例)

| 用例 | 任务 | 结果 | 备注 |
|---|---|---|---|
| CASE-01 | `67432.178` 按 `0.01` 网格 BUY 向下截断 | `valid_price=67432.17` | 多数共识(Path2 失败后补派) |
| CASE-02 | `0.000034` 按 `0.0001` SELL 向上截断防零报价 | `valid_price=0.0001` | 三路 |
| CASE-03 | `104.381` 按 `0.125` NEAREST_HALF_UP | `valid_price=104.375` | 三路(1 次 premature 补派撤销) |
| CASE-04 | `budget=1500 price=19.83 lot_step=1` 求最大股数 | `qty=75 / notional=1487.25 / surplus=12.75` | 三路 |
| CASE-05 | `base=151.847 step=0.006 count=5 tick=0.01` 阶梯量化 | ladder `[151.85,151.85,151.86,151.87,151.87]` | **workflow 通道**三路(`parallel` barrier) |

**证据**:`evidence/p1-case01..05*.md`;**子会话 ID 可查**(如 CASE-01:
Path1 `6576f6d9` / Path2 补派 `544953f8` / Path3 `27a639db`)。

**复核命令**:
```powershell
# 列出某会话的子会话(需 DSH web 在跑)
node tools/audit-subagent-cost.mjs --limit 40
# 或用 RPC:session/list 过滤 origin=subagent 且 parentSessionId=<主会话>
```

### 2.5 免费档同模型并发三路 = 必挂(机制明确)

**结论**:在 `muse-spark-1.3-contributor-free`(免费档)上并发发射 3 路子代理,
**3/3 全部失败,零产出**。

**失败链(从子会话 zstd 日志逐帧解出,非推测)**:
```
[22] assistant/attempt → finish.reason.error = 429 rate_limit_exceeded
[23..39] llm/retry ×6   退避 1.4s → 3.3s → 5.4s → 10.3s → 20s → 20s
[42] turn/end reason=error code=RATE_LIMIT
```

| 子会话 | 重试 | 限流事件 | turn/end | closing |
|---|---|---|---|---|
| `0133ab8d-5d32-4875-b9fe-56f4cbac96d7` | 6 | 7 | `RATE_LIMIT` | 无 |
| `c2dd617c-acfe-4fe6-af5c-5050ce404efe` | 6 | 7 | `RATE_LIMIT` | 无 |
| `f529f435-a6f6-4f62-8d2b-8515a02e5287` | 6 | 7 | `RATE_LIMIT` | 无 |

单路耗时约 **320 秒**,三路合计约 16 分钟算力全废。

**证据**:`evidence/p1-heterogeneous-route-round2.md`

**复核命令**(日志为多帧 zstd,需逐帧解):
```powershell
node tools/audit-subagent-settlement.mjs --limit 12
# 期望:上述三例显示 rateLimit=7 turnEnd=RATE_LIMIT closing=NONE,退出码 1
```

### 2.6 混杂因子已分离:真凶是免费档,不是"同模型"

**这是本项目最重要的实验结论。** 起因:2.5 的失败组(免费档)与成功组(付费档)
**同时变了两个变量**(①路由异构性 ②档位付费),无法归因。故补做对照实验。

| 配置 | 样本 | 结算成功 | 限流失败 |
|---|---|---|---|
| 免费档 + 同模型并发 | 3 | 0 | **3** |
| **付费档 + 同模型并发** | **9** | **9** | **0** |
| 付费档 + 异构并发 | 2 | 2 | 0 |

A 组三轮(每轮间隔 90s,守 RPM/TPM):

| 轮 | Path 1 | Path 2 | Path 3 | 重试 | 限流 |
|---|---|---|---|---|---|
| A1 | `d654e9fa-775b-4375-9b5b-9369aa2aa066` | `f6934f2a-8a3b-442f-8e69-9b677e359550` | `984f117c-306b-44d5-b29d-00344b0d0669` | 0 | 0 |
| A2 | `76a4cd16-6f45-43dc-95d0-3f5e481ab981` | `ac53461a-4cb3-4f07-be5c-93f47071b83f` | `c599cd38-ebdf-4804-a0eb-55a4baa9d2f7` | 0 | 0 |
| A3 | `f42c456b-55bd-437d-b377-041f2e6356da` | `bb8c2ed2-673b-4cab-ad59-4d45542434bb` | `8f169934-39c9-48b8-abe4-b0dccfc54027` | 0 | 0 |

**结论**:
- 付费档同模型并发 3 路**完全可行**(9/9,零限流零重试)。
- **"同模型"本身不是禁忌,档位才是。**
- 异构路由对**反限流**并非必需,但仍有**独立性**价值(不同模型权重)。

**证据**:`evidence/p1-route-confound-controlled-2026-09-28.md`

**persona 已据此修正**:免费档禁止并发(硬要求)/ 付费档同模型可接受 /
异构降为"推荐"。

### 2.7 红队角色确实在质疑前提(非附和)

**意外发现**:在 9 路对照实验中,prompt 故意写了错误前提
(称 `104.381/0.125 = 835.5`),**三轮的 Path 2 全部独立纠正**:

> "104.381/0.125 实为 **835.048**,非 835.5;真中点应为 `104.4375`"

且 9 路数值 **100% 一致**(`835` / `104.375`)。

**意义**:这是红队**真在对抗而非顺从**的实证,比"结论一致"更有价值。

**⚠️ 但同时暴露机制复杂性**:该纠正是在**传了**错误前提的情况下发生的,
说明"传前提必然导致附和"的假设**不成立** —— 详见 §四未验证项。

### 2.8 生成物已确定性化 + CI 守卫

**问题**:`run_stress_matrix.py` 会重写 `benchmark-results.json`,其中
`latency_ms` / `total_execution_time_s` 含本地计时值 → 每次重跑数值都变,
CI 无法用 diff 守卫生成物漂移。

**修法**:移除这两个**文件头本就声明"毫无意义"**的计时字段 → 产物转确定性。

**复核命令**:
```powershell
cd plugins/dsh-jev-preset
python benchmarks/run_stress_matrix.py
Copy-Item benchmarks/benchmark-results.json $env:TEMP\r1.json
python benchmarks/run_stress_matrix.py
(Get-FileHash $env:TEMP\r1.json).Hash -eq (Get-FileHash benchmarks/benchmark-results.json).Hash
# 期望:True(两次运行产物逐字节一致)
```

**CI 守卫**:`.github/workflows/ci.yml` 新增 step,
`git diff --exit-code -- benchmarks/benchmark-results.json`,不一致即失败。

### 2.9 审计工具本身被验证(含一次自我纠错)

| 工具 | 用途 | 退出码 |
|---|---|---|
| `tools/audit-subagent-settlement.mjs` | 结算健康度(限流/重试/无 closing) | 1 = 检出限流 |
| `tools/audit-subagent-cost.mjs` | 按路由聚合 token/耗时/步骤 | 恒 0 |

**自我纠错记录(重要)**:
1. `audit-subagent-settlement.mjs` 首版有**假阴性** —— `turnEnd=RATE_LIMIT`
   却报 `rateLimit=0`。根因:结构路径误写为 `s.chunk.finish.reason.failure`,
   正确为 `s.chunk.reason.failure`。与原始日志逐字段比对后修正,
   三例由 `0` 变 `7`,检出恢复。
2. `audit-subagent-cost.mjs` **纠正了本文档的早期错误** ——
   失败组路由原记为 `ds-flash`,实为 `muse-spark-1.3-contributor-free`(免费档)。

**教训**:工具本身也必须被验证。这条已写入证据文件。

---

## 三、三源调研驱动的设计依据(引用外部研究,本机未复现其数字)

> 以下每条**均为已发表研究**,用于支撑 persona 纪律。
> **本机未复现**这些论文的实验,故标 ⚠️。

| 来源 | 关键数字 | 支撑了哪条纪律 |
|---|---|---|
| [arXiv:2503.13657](https://arxiv.org/html/2503.13657v1) MASFT(UC Berkeley,150+ 轨迹,κ=0.88) | 14 失败模式 / 3 类;FC3 占 21% | 补派预算封顶(FC3「不知何时停」)、防锚定(FC2)、规范即契约(FC1) |
| [arXiv:2605.00914](https://arxiv.org/html/2605.00914) The Cost of Consensus | 从众趋同最高 **85.5%**;语境脆弱最高 **70.0%**;oracle gap 最高 **32.3pp**;同质辩论多耗 **2.1–3.4×** token | **三路必须隔离**;禁止把 Path1 结论传入 Path2/3 |
| [arXiv:2604.07650](https://arxiv.org/abs/2604.07650) 行为纠缠审计(18 模型/6 家族) | BEI ρ=0.508, CIG ρ=0.520 (p<0.01) | **异构 ≠ 真独立**;三路一致不构成正确性证明 |
| [arXiv:2504.01005](https://arxiv.org/html/2504.01005) When To Solve, When To Verify | GenRM 需 **8×** 算力追平 SC,**128×** 换 3.8% 增益 | Fast-Pass 与三路的**成本门槛**是理论最优,非省事 |
| [arXiv:2502.20379](https://arxiv.org/html/2502.20379) Multi-Agent Verification | 多样验证者投票优于自一致性 | 验证者应沿「基座模型/验证侧面/验证策略」三轴取多样 |
| [生产实践指南](https://www.ewok.me/blog/posts/2026-02-28-building-reliable-multi-agent-llm-systems-a-best-practice-guide.html) | 生产失败率 41–87%;错误放大最高 **17.2×**;~4 智能体饱和 | 独立验证者须"分离上下文、分离提示";警惕验证剧场 |

### 3.1 本轮据此实施的 4 项优化

| # | 优化 | 依据 | 状态 |
|---|---|---|---|
| 1 | **补派预算封顶**:每角色最多补派 1 次;仍失败即降级,新增 `[JEV: 单路未验证]` | MASFT FC3 | ✅ 已写入 persona |
| 2 | **防锚定铁律**:禁止把 Path1 结论/数值写进 Path2/3 的 prompt | 生产指南原则 4 + arXiv:2605.00914 | ✅ 已写入 persona |
| 3 | **异构 ≠ 真独立**:写入认知边界,明确执行断言权重**高于**三路共识 | arXiv:2604.07650 | ✅ 已写入 persona |
| 4 | **成本门槛理论化**:persona 新增第六节「设计依据」(6 条可追溯引用) | arXiv:2504.01005 | ✅ 已写入 persona |

### 3.2 未采纳的建议(附理由)

| 建议 | 来源 | 不采纳理由 |
|---|---|---|
| 集中式编排优于去中心化辩论 | 生产指南 | JEV 三路**不是辩论**,是**隔离并行采样**(无同伴通信);该批评不适用 |
| 智能体数在 ~4 饱和 | 生产指南 | JEV 固定 3 路,已在阈值内 |
| JSON Schema 强制 agent 间消息 | 生产指南原则 5 | 三路间**无直接通信**;若要强制应作用于**子代理返回契约**,但 `opts.schema` 仅 workflow 通道支持 —— 属可探索项 |
| 引入独立 judge 模型 | 生产指南原则 4 | 需额外成本,且 arXiv:2604.07650 表明 judge 本身有行为纠缠风险;当前以执行断言替代 |

---

## 四、❌ 未验证 / 待复核项(请重点检验这些)

> 以下**不是结论**,是**已知的空白**。第三方若发现其中任何一条被我当作结论使用,
> 即为**过度宣称**,请指出。

| # | 未验证项 | 为什么重要 | 建议的验证方法 |
|---|---|---|---|
| 1 | **补派上限=1 是否最优** | 1 是保守取值,依据仅为"429 单路烧 320s"的单点实测 + 无限循环理论风险 | 做 1/2/3 次上限的对照实验,比较收敛率与配额消耗 |
| 2 | **防锚定的实际效果** | 改为"不传 Path1 结论"后,Path2 独立发现率是否提升,**未做 A/B** | 同任务两版 prompt(传/不传前提)各 N 次,比较独立发现率 |
| 3 | **三路模型间的行为纠缠** | 只引用了他人 BEI/CIG,**未在本机测** ds-flash / gemini-3.8-flash / muse-spark | 构造同步失败样本集,算 BEI/CIG |
| 4 | **4 路以上并发** | 只证明 3 路可行 | 付费档 4/5/6 路并发对照 |
| 5 | **免费档 + 异构路由是否可救** | 未测 | 免费档但三路用不同 model |
| 6 | **限流结论的时效性** | 与账户配额、时段、并发总负载相关,**非永久常量** | 隔期复测 |
| 7 | **`docs/performance-spec.md` 中的门槛值**(如"Path1 < 100ms"、"红队捕获率 ≥90%") | 这些是**拍定的目标值**,无测量依据 | 需真实三路实测回填 |
| 8 | **"内存零泄漏"** | 无测量依据 | 长程会话内存采样 |
| 9 | **5 小时长程稳定性** | 号称 11 分钟跑完的会话 `roundsStarted=0`,**未真正验证 5 小时** | 长程运行 + 内存/上下文压力采样 |

### 4.1 一条需要特别说明的**反例**

§2.7 记录了 Path 2 在**收到错误前提**时反而独立纠错。这与 §3.1 优化 2
(防锚定)的**前提假设存在张力**:

- 若"传前提必然导致附和",则 2.7 不该发生;
- 实际发生了,说明机制比预期复杂(可能是:错误前提反而激活了红队的批判模式)。

**故优化 2 的收益未经证实**,当前按**保守纪律**执行。
第三方若要检验,建议先做 §4 的 #2 实验。

---

## 五、当前状态总览

### 5.1 仓库

| 项 | 值 |
|---|---|
| 仓库 | <https://github.com/Yum-wu/dsh-jev-preset>(Public) |
| 最新提交 | `07a9f17` fix(jev): 诚信更正死代码防线 + 三源调研驱动的实质优化 |
| CI | success(ubuntu/windows × node 20/22) |
| 版本 | `package.json` version `1.1.0` |

### 5.2 文件清单(供复核)

```
plugins/dsh-jev-preset/
├── cordis.patch.yml                    # 预设本体(persona + 17 个插件行)
├── package.json                        # bundle 清单,零依赖
├── validate.mjs / validate-official.mjs # 静态 + 官方路径验证器
├── smoke.mjs / session-test.mjs / three-path-test.mjs
├── docs/
│   ├── best-practice-research-2026-09-28.md   # 本文(结论汇总)
│   ├── architecture.md                        # 架构(已更正防线宣称)
│   ├── orchestration-analysis.md              # 编排分析(已更正)
│   ├── benchmark-report.md                    # 基准报告(已撤下伪造数字)
│   └── performance-spec.md                    # 性能规格(门槛值待回填)
├── evidence/                           # 15 个证据文件
│   ├── SUMMARY.md                             # 总览
│   ├── p0-depth-limit.log                     # 递归阻断实证
│   ├── p0-workflow-ptc-check.log              # 官方路径实证
│   ├── p1-case01..05*.md                      # 5 个量化用例三路证据
│   ├── p1-heterogeneous-route-round2.md       # 限流失败 + 异构修复
│   ├── p1-route-confound-controlled-2026-09-28.md  # 混杂因子对照实验
│   ├── p2-audit-round4.md                     # 未测量标注核对
│   └── p3-*.log                               # 测试/冒烟/断言日志
├── tools/
│   ├── audit-subagent-settlement.mjs          # 结算健康度审计
│   ├── audit-subagent-cost.mjs                # 成本审计
│   ├── verify-depth-limit.mjs                 # 递归阻断验证
│   ├── dump-three-path.mjs                    # 三路归档
│   ├── launch-long-goal.mjs / monitor-long-goal.mjs
├── tests/                              # node 5 单测 + python 5 断言
├── benchmarks/                         # 30 用例清单(非三路采样)
└── packages/assertions/                # Python + PowerShell 断言库
```

### 5.3 本机运行时事实(复核环境)

| 项 | 值 |
|---|---|
| DSH 运行时 | `dsh-0.1.7-rc.2`(入口 `~/.dsh/start-dsh.ps1`) |
| Web 服务 | `http://127.0.0.1:3080`(token 在 `~/.dsh/web-url.txt`) |
| 可用子代理路由 | `opencodex/combo/ds-flash`、`opencodex/google-antigravity/gemini-3.8-flash`(**仅 2 个**) |
| 运行时重试 | 宿主 `@deepseek-ai/dsh-llm-retry`,normal mode 最多 6 次 |
| 官方文档 | ⚠️ `dsh-0.1.7-rc.2` 目录下**无 `docs/` 子树**(仅 `node_modules`);"遵循官方文档"实际依据**各包 README** |

---

## 六、给复核者的建议清单

按价值排序,建议优先检验:

1. **§一 的已证伪项是否真的已修**(最易验证,也最能反映诚信)
   → 跑 §零 的 1-4 条命令,并 grep 死代码
2. **§2.6 对照实验的原始会话是否真存在**(9 个 ID 在 §2.6 表中)
   → `node tools/audit-subagent-cost.mjs --limit 40` 核对路由与 ID
3. **§2.5 的限流日志是否真能解出 429 链**(最硬的技术证据)
   → `node tools/audit-subagent-settlement.mjs --limit 12`
4. **§四 未验证项中,是否有被我当作结论使用的**
   → 逐条比对 persona 正文(`cordis.patch.yml`)
5. **§3 引用的论文数字是否与原文一致**
   → 已给直链,请抽检 2-3 条

**若发现任何一条标注为 ✅ 但复现失败,或 ❌ 被当作结论使用,
即为本次工作的缺陷,请直接指出。**
