# JEV 底层编排机制与异步协同优化分析 (Orchestration & Concurrency Analysis)

## 一、双编排模式实测对比：方式 A vs 方式 B

在 JEV 模式下，三路上下文隔离采样的执行有两种底层实现路径：

### 1. 方式 A: 原生 subagent (Continuable 异步后台 + Settlement Notice 回收)
- **底层原理**: 通过 `@deepseek-ai/dsh-tool-subagent` 派生独立子会话，主会话非阻塞返回 `started subagent <id>`，子代理独立运行，完成时通过宿主事件系统向主会话注入结算通知 (Settlement Notice)。
- **核心优势**:
  - **真正的上下文物理隔离**: 每个 subagent 拥有独立的 Memory 空间、Tool 注册表和系统指令；
  - **容错韧性极高**: 某一路子代理挂起或耗时较长时，不影响其他两路执行，支持针对单路进行精准的「2/3 + 补派」；
  - **会话持久化**: 子代理具有生命周期，支持 `list_agents` / `send_message` 二次追问。
- **代价与挑战**:
  - 异步结算通知需由主会话主动等齐，模型需具备强纪律性（收齐 3 条前禁止提前下结论）；
  - 偶发网络异常时可能丢失单路通知，需依赖超时探测器主动唤醒。

### 2. 方式 B: workflow-ptc (Parallel 同步 Barrier + 严格收集)
- **底层原理**: 通过 `@deepseek-ai/dsh-workflow-ptc` 提供的 `parallel([thunk1, thunk2, thunk3])` 构造微前端同步屏障，一次性等待所有 thunk 完成并返回结果数组。
- **核心优势**:
  - **强一致性屏障 (Barrier)**: 必须三路齐备后才向下一步流转，从物理机制上彻底消除了“提前偷跑结论”的可能；
  - **结构化收集**: 原生支持 `opts.schema` 对每路输出进行 JSON Schema 强制验证，不符合契约直接抛出 `null`；
  - **代码级可控**: 编排逻辑由 JavaScript 严格描述，无 Prompt 漂移风险。
- **代价与挑战**:
  - 木桶效应：最慢的一路决定了整体延迟；若某路发生未捕获异常，整个屏障将丢弃该项，容错粒度较粗。

---

## 二、高并发下健壮性与断路器 (Circuit Breaker)

> ⚠️ 更正声明（2026-09-28）：本节描述的"三态断路器状态机"与"自适应指数退避"
> **在 JEV 运行时并不存在**。`JevCircuitBreaker` 只定义在 `tests/test-circuit-breaker.mjs`
> 与 `tests/orchestration-benchmark.mjs` 中，**从未接入 `cordis.patch.yml`**（全仓 0 处引用）。
> 以下内容保留作为**设计参考实现**，不是已部署能力。
> 运行时真实的重试由宿主 `@deepseek-ai/dsh-llm-retry` 提供（normal mode，最多 6 次）。

当外部模型 API 遭遇突发限流 (HTTP 429)、服务不可用 (HTTP 503) 或网络超时 (Timeout) 时：
1. **三态断路器状态机**:
   - `CLOSED`: 正常状态，所有请求直接通行，统计连续失败次数；
   - `OPEN`: 连续失败达阈值 (默认 3 次) 时熔断，直接拒绝新任务，冷却时间 (默认 1000ms)，避免无效轰炸 API；
   - `HALF_OPEN`: 冷却结束尝试放行单路探测，成功则自愈回到 `CLOSED`，失败继续 `OPEN`。
2. **自适应指数退避 (Exponential Backoff)**:
   - 补派等待时间为 $t = \text{base} \times 2^{\text{attempt}} + \text{jitter}$，防止雪崩惊群效应。

---

## 三、角色防重复派发锁 (Role Unique Registry)

> ⚠️ 更正声明（2026-09-28）：本节的"角色互斥注册器"**在 JEV 运行时不存在**。
> `JevRoleRegistry` 只定义在 `tests/orchestration-benchmark.mjs`，从未接入运行时（全仓 0 处引用）。
> 实际的角色唯一性**仅靠 persona 纪律**，无程序化拦截 —— 即历史观察到的
> "派出两个 Path 3"缺陷**在程序层面仍未被修复**，只是被写进了 prompt 要求。
> 本节保留作为**设计参考**，并标注该弱点仍待实现。

在历史演化中，曾偶发模型在派发三路时派出两个 `Path 3` 而漏掉 `Path 2` 的角色混淆现象。
**设计目标**（尚未实现）：通过角色互斥注册器在派发时拦截重复角色。
- 定义标准三角色静态集合：`['Path 1 严谨推导者', 'Path 2 红队对抗者', 'Path 3 极简执行者']`；
- 在派发每个 subagent 时，必须先在注册表登记角色名，任何已存在 `in_flight` 状态的角色再次派发时直接被注册器拦截抛错；
- 仲裁前必须校验三角色集合与预期全等，彻底消除了角色重复与遗漏缺陷。

---

## 四、Compaction 压缩策略与长对话注意力保护

针对三路高危任务会产生大量中间推导与执行日志的特点：
1. **自适应工具输出修剪器 (tool-result-pruner)**:
   - 配置阈值 `thresholdChars: 8192`，保留前部 `headChars: 4096` 与尾部 `tailChars: 1024`；
   - 前部保留完整的输入参数、初始化状态与前置断言；尾部保留最终返回代码与执行结果摘要；中间截断大幅降低长会话的 Token 消耗；
2. **长对话注意力保护 (Attention Anchor)**:
   - JEV 的 Persona 在 `cordis.patch.yml` 中被声明为固定前缀模板，在上下文被滚动压缩时，系统提示词与规则锚点永不参与滑动丢弃，确保长程运行 5 小时以上依然严格遵守 JEV 铁律。
