# JEV 模式最佳实践调研(2026-09-28)

**方法**:三源交叉 —— 一手论文(arXiv)、生产实践指南、本机官方文档/源码核查。
**原则**:每条结论标注来源;未能核实的一律标"未验证"。

---

## 一、调研来源

| 来源 | 类型 | 用于 |
|---|---|---|
| [arXiv:2503.13657](https://arxiv.org/html/2503.13657v1) Why Do Multi-Agent LLM Systems Fail? (UC Berkeley) | 实证研究(150+ 轨迹,6 专家,Cohen's κ=0.88) | 失败分类 MASFT |
| [arXiv:2605.00914](https://arxiv.org/html/2605.00914) The Cost of Consensus | 受控实验(N=10 智能体 ×3 轮) | 同伴交流的危害 |
| [arXiv:2502.20379](https://arxiv.org/html/2502.20379) Multi-Agent Verification | 实验(8 基座模型 ×4 领域) | 多样验证者价值 |
| [arXiv:2604.07650](https://arxiv.org/abs/2604.07650) Auditing Behavioral Dependence | 统计框架(18 模型 / 6 家族) | 异构≠独立 |
| [arXiv:2504.01005](https://arxiv.org/html/2504.01005) When To Solve, When To Verify | 算力匹配分析 | 成本门槛依据 |
| [生产实践指南](https://www.ewok.me/blog/posts/2026-02-28-building-reliable-multi-agent-llm-systems-a-best-practice-guide.html) | 综述(整合 Berkeley/DeepMind/Anthropic) | 设计原则 |
| 本机 `cordis.patch.yml` + `tests/` + 宿主包源码 | 一手核查 | 验证宣称真伪 |

---

## 二、P0 诚信缺陷(已修)

### 缺陷:README 宣称的两条"核心防线"是死代码

**核查方法**:全仓 grep。

```
cordis.patch.yml 搜 CircuitBreaker/RoleRegistry/断路器/角色互斥 → 0 匹配
JevCircuitBreaker / JevRoleRegistry 定义位置 → 仅 tests/test-circuit-breaker.mjs
                                             与 tests/orchestration-benchmark.mjs
全仓 import/引用次数 → 0
```

**结论**:README「核心安全与工程防线」第 3 条(断路器)、第 4 条(角色互斥锁)
把**从未接入运行时的测试桩**描述为已部署防线。这与历史上的伪造基准
**同属"验证剧场 (Verification Theater)"** —— 生产实践指南将其列为
第 4 号反模式("a verifier that ... shares too much context with producing agents,
becoming a participant in collective delusion rather than an objective judge")。

**已修**:README + `docs/architecture.md` + `docs/orchestration-analysis.md` 三处
加更正声明,明确区分「真实防线(2 条)」与「设计参考(非防线)」,
并说明运行时真实重试由宿主 `@deepseek-ai/dsh-llm-retry` 提供。

### 暴露的真实弱点(仍未修)

角色唯一性**无程序化保障**,仅靠 persona 纪律。历史"派出两个 Path 3"的缺陷
在程序层面仍存在。`toolFilter` 路线已被证伪(见 cordis.patch.yml 192-198 行注释:
`tools.restrict()` 只接受全局工具名),故**暂无已知的运行时拦截手段**。

---

## 三、P1 实质优化(已实施)

### 1. 补派预算封顶(对应 MASFT FC3)

**问题**:原 persona 要求"某路失败必须重新派发同一角色补齐",**无次数上限**。
在 429 限流场景下,单路可烧 ~320 秒零产出(实测),无限补派会持续消耗配额且永不收敛。

**依据**:MASFT 14 个失败模式中,FC3「Task Verification & Termination」
(占失败 21%)明确包含「Unaware of stopping conditions」—— 不知道何时该终止。
生产指南同样列出「The Infinite Loop: No termination conditions, no budget caps,
no circuit breakers. Agents burn tokens indefinitely.」

**实施**:每角色补派**最多 1 次**(每路总计最多 2 次发射);仍失败即停止该路,
按可用路数降级(2 路 → 多数共识;1 路 → 新标识 `[JEV: 单路未验证]` + 显式置信声明)。
失败原因为配额类 → 直接串行降级,不原地重派。

### 2. 防锚定铁律(对应 MASFT FC2 + 生产指南原则 4)

**问题**:原实践把 Path 1 的结论写进 Path 2 的 prompt(如
"Path 1 候选结论 valid_price=67432.17,请攻击它")。实测已观察到 Path 2
会**顺着给定前提展开**,只做局部质疑 —— 这不是独立验证,是**附和+微调**。

**依据**(两条独立来源):
- 生产指南原则 4:「The judge/verifier agent must be independent — **separate context,
  separate prompts, not influenced by the producing agents' reasoning chains**」
- [arXiv:2605.00914](https://arxiv.org/html/2605.00914):同伴推理会引发
  **从众趋同**(modal adoption 最高 **85.5%**)、**语境脆弱性**(正确推理被推翻率最高 **70.0%**)、
  以及**共识崩塌**(oracle gap 最高 **32.3 个百分点** —— 正确答案已在生成池中却被投票丢弃)。

**实施**:派发 Path 2/3 时**禁止**写入 Path 1 的结论/数值/中间量;
三路各自拿原始任务独立求解,回收后由裁决节点交叉比对。
例外仅限"任务本质就是审查给定产出",且须明确标注"该产出可能有错"。

### 3. 异构 ≠ 真独立(认知边界)

**问题**:JEV 把"异构模型路由"当作独立性保障,但这一假设本身需要限定。

**依据**:[arXiv:2604.07650](https://arxiv.org/abs/2604.07650) 对 18 个模型 / 6 个家族
的统计审计发现,共享预训练数据、蒸馏与对齐流程会诱导**行为纠缠(latent entanglement)**,
表现为相关推理模式与**同步失败** —— 表面一致实为**共享错误模式**。
该纠缠与 judge 过度认可偏见显著相关(BEI ρ=0.508, CIG ρ=0.520, p<0.01)。

**实施**:persona 明确写入「三路一致**不构成正确性证明**,只是未发现分歧」;
高资金风险场景下**客观执行断言权重必须高于三路共识**。
这也为原有的"执行优先裁决"提供了外部理论根据(原先只是直觉)。

### 4. 成本门槛的理论根据(补强原有设计)

**依据**:[arXiv:2504.01005](https://arxiv.org/html/2504.01005) 在**固定算力预算**下
对比自一致性(SC)与生成式验证(GenRM):SC 在**低预算下更划算**,
GenRM 需要 **8× 算力**才追平,需 **128× 算力**才获得 3.8% 增益;
最优策略是**扩大采样比扩大验证更激进**(1.5–2×)。

**实施**:persona 第六节新增"设计依据"段,说明 Fast-Pass 与三路的成本门槛
并非拍脑袋 —— 低危任务上启动三路验证是**负收益**(生产指南:「Base model accuracy
>45% on the task → single agent likely sufficient; MAS adds noise」)。

---

## 四、未采纳的建议(附理由)

| 建议 | 来源 | 不采纳理由 |
|---|---|---|
| 集中式编排(Orchestrator + Specialists)优于去中心化辩论 | 生产指南(DeepMind 排序) | JEV 的三路**本就不是辩论**——是**隔离并行采样**,无同伴通信。指南的批评针对"去中心化辩论",不适用。 |
| 智能体数量在 ~4 处饱和,别超过 | 生产指南(DeepMind) | JEV 固定 3 路,已在此阈值内。 |
| 用 JSON Schema 强制 agent 间消息 | 生产指南原则 5 | 三路之间**无直接通信**(隔离采样),不适用。若要强制,应作用于**子代理返回契约**,但当前 `subagent` 工具的 `opts.schema` 仅 workflow 通道支持 —— 属可探索项。 |
| 引入独立 judge 模型打分 | 生产指南原则 4 | 需要额外模型调用成本,且 arXiv:2604.07650 表明 judge 本身有行为纠缠风险。当前以"执行断言"替代,更客观。 |

---

## 五、本次调研未覆盖 / 待验证

- **异构路由是否真能降低行为纠缠**:本次只引用了他人的纠缠度量,**未在本机实测**
  三路所用模型(ds-flash / gemini-3.8-flash / muse-spark)之间的 BEI/CIG。
  若要做,需构造同步失败样本集,成本较高。
- **补派上限设为 1 次是否最优**:1 次是保守取值,依据是"429 场景下单路烧 320s"的
  单点实测 + 无限循环的理论风险,**未做不同上限的对照实验**。
- **防锚定的实际效果**:改为"不传 Path 1 结论"后,Path 2 的独立发现率是否提升,
  **未做 A/B 实测**。历史上 Path 2 确有独立纠正 prompt 错误前提的记录
  (见 `p1-route-confound-controlled-2026-09-28.md`:三轮 Path 2 独立指出
  "835.5 前提有误,真中点应 104.4375")—— 但那是在**传了**错误前提的情况下发生的,
  说明传前提未必总是导致附和,机制比预期复杂。
- **本机 DSH 官方文档**:运行时 `dsh-0.1.7-rc.2` 目录下**无 `docs/` 子树**
  (仅 `node_modules`),故"遵循官方文档"只能依据**各包的 README**(如
  `dsh-tool-subagent/README.md` 的配置契约表),已据此核对 `agentOptions`、
  `maxDepth`、`modelSelectionSettings` 等字段语义。
