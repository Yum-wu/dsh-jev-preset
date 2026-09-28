# P1 异构模型路由实证(2026-09-28,Round 2)

## 背景:同模型并发是反模式(实测)

JEV persona §3 原写"同一条 assistant 消息内并发发射 3 个 subagent 即是隔离与并行的物理保证"。
2026-09-28 按该纪律**严格遵守**派发三路(全部 `opencodex/combo/ds-flash`),结果**三路全灭**:

| 子会话 | 重试次数 | 限流事件 | turn/end | closing |
|---|---|---|---|---|
| `0133ab8d-5d32-4875-b9fe-56f4cbac96d7` | 6 | 7 | `RATE_LIMIT` | 无 |
| `c2dd617c-acfe-4fe6-af5c-5050ce404efe` | 6 | 7 | `RATE_LIMIT` | 无 |
| `f529f435-a6f6-4f62-8d2b-8515a02e5287` | 6 | 7 | `RATE_LIMIT` | 无 |

失败链(从子会话 zstd 日志解出,非推测):
```
[22] assistant/attempt → finish.reason.error = 429 rate_limit_exceeded
[23..39] llm/retry ×6   退避 1.4s → 3.3s → 5.4s → 10.3s → 20s → 20s
[42] turn/end reason=error code=RATE_LIMIT
```
单路耗时约 320 秒,零产出。三路合计约 16 分钟算力全废。

## 修法:异构模型路由(§3.3)

三路各用**不同** provider/model,把并发压力分散到不同上游配额:

| 路 | 路由 | 理由 |
|---|---|---|
| Path 1 严谨推导者 | `opencodex/combo/ds-flash` | 强推理档,需完整中间量 |
| Path 2 红队对抗者 | `opencodex/google-antigravity/gemini-3.8-flash` | **异构模型**才有真对抗价值 |
| Path 3 极简执行者 | 低延迟档(路由不足时串行降级) | 只出最小可跑代码 |

## 验证结果:异构并发 2/2 成功

同一时间点、同一任务(CASE-03 `raw=104.381 tick=0.125 NEAREST_HALF_UP`)、**同消息并发**发射:

| 子会话 | 路由 | 重试 | 限流 | closing |
|---|---|---|---|---|
| `f1807136-6ac6-4a8d-acab-cc4c58beb500` | `combo/ds-flash` | 0 | 0 | `[Path 1 严谨推导者]` |
| `e23737cc-9200-4940-a694-3d3183b875ac` | `google-antigravity/gemini-3.8-flash` | 0 | 0 | `[Path 2 红队对抗者]` |

两路均**零重试、零限流、正常结算**,并各自回显路标身份。

## 执行断言裁决(最高仲裁权)

| 方案 | 样本 | 结算成功 | 限流失败 | 结论 |
|---|---|---|---|---|
| 同模型并发(旧纪律) | 3 | 0 | 3 | **否决** |
| 异构路由并发(新纪律) | 2 | 2 | 0 | **采纳** |

数值一致性:两路对同一任务的结论**独立且一致** ——
Path 1 得 `ticks_count=835 / valid_price=104.375 / tick_diff=+0.006`;
Path 2 独立给出中点 `104.4375/0.125=835.5` 的 HALF_UP vs HALF_EVEN 分歧档位
(`835` vs `836`,差 0.125),以及 float 漂移与 0.01 截断两类反例。
两者不冲突,且 Path 2 补充了 Path 1 未覆盖的中点平局边界。

## 副产品:结算健康度审计工具

`tools/audit-subagent-settlement.mjs` —— 把上述失败模式机读化,退出码 1 即提示需异构路由。
首版有假阴性(`s.chunk.finish.reason` 误写为 `s.chunk.finish.reason.failure` 路径),
经与原始日志逐字段比对修正:`0133ab8d` 等三例由 `rateLimit=0` 变为 `rateLimit=7`,检出恢复。

## 结论

1. **同模型并发 = 反模式**,已写入 persona §3 顶部警告。
2. **异构路由同时解决两个问题**:反限流 + 提升"独立验证"的实质独立性(不同模型权重,非同源偏见)。
3. 降级路径明确:2 路由→部分串行;1 路由→全串行并标 `[JEV: 串行降级-单路由]`。
