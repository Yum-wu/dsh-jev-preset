# P1 CASE-01 三路证据快照(Round 1)
- Path1 6576f6d9: 结论 valid_price=67432.17 tick_diff=0.008(商6743217.8/取整6743217); closing文本偏薄,实质推导经send_message通道回传(已存)。
- Path3 27a639db: 已结算,全文本含9行代码+命令+stdout(valid_price=67432.17000000 tick_diff=0.00800000 PASS),专属临时目录执行。
- Path2 b5f038a7: 原路经ping无实质文本后撤销(判无结果,疑似超长未结算);补派544953f8经message通道回传反例链:int(1.15/0.01)*0.01=1.1400000000000001本地复现一致;float极小值项本机实测3.4e-05与Path2预期3.399999e-05有平台浮点差异(攻击逻辑成立,数值按本机为准);补派closing仅回"静默等待"(文本经message通道已收齐)。
- 本轮裁决: P1/P3 valid_price=67432.17硬一致,Path2为攻击视角 → [JEV: 2/3 Majority Consensus]相当。
- 本地复算: valid_price=67432.17 tick_diff=0.008(已跑)。
- P0证据: evidence/p0-workflow-ptc-check.log(validate-official全绿 + provider=spawn纯字符串结论)。
