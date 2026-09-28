# JEV 真实三路隔离实测汇总(第 2 次闭环,Round 6)
- P0: workflow-ptc config={provider:spawn}纯字符串,无表达式;!!js仅2处平台开关,validate-official全绿。见 p0-workflow-ptc-check.log。
- P1: CASE-01(67432.17/多数共识,1失败补派)/CASE-02(0.0001/三路)/CASE-03(104.375/三路,1 premature补派撤销)/CASE-04(75股/三路)/CASE-05(ladder五笔/workflow三路,见 p1-case05-round7.md),子会话ID与stdout见 p1-case*.md。
- P1-新增: **异构模型路由实证**(见 p1-heterogeneous-route-round2.md)。同模型并发三路 → 3/3 全部 RATE_LIMIT 零产出(6次重试耗尽,~320s/路);改异构路由(combo/ds-flash + gemini-3.8-flash)同消息并发 → 2/2 零重试正常结算。已写入 persona §3.3 与降级规则。
- P1-新增(对照实验): **混杂因子已分离**(见 p1-route-confound-controlled-2026-09-28.md)。付费档 ds-flash **同模型**并发 3 路 ×3 轮 = **9/9 全成功零限流**;免费档 muse-spark 同模型并发 = 3/3 限流失败。**真凶是免费档档位,不是"同模型"**。persona 已修正:免费档禁止并发(硬要求),付费档同模型可接受(实测 9/9),异构降为"推荐"。
- P2: 28处未测量仍属实,零回填。见 p2-audit-round4.md。
- P3: npm test(node5/5+python5 OK,exit0)/smoke(全PASS,exit0)。见 p3-*.log。
- 缺口: subagent+workflow双通道已齐;未满25轮禁complete。
