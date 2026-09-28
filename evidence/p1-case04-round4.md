# P1 CASE-04 三路证据快照(Round 4)
- Path1 86d6f332: 商75.64/qty=75/notional=1487.25/surplus=12.75,校验>50通过;复算命令输出75/1487.2499999999998/12.750000000000227/True,closing全文本齐。
- Path3 17c2038f: 10行Decimal代码+专属临时目录stdout(qty=75/notional=1487.25/surplus=12.75,EXIT 0),双断言通过,closing齐。
- Path2 77d70d64: 反例链(76股1507.08越界7.08/49.99买2股39.66被minNotional拒单/浮点漂移),命令四行输出全复现一致,closing待收但message实质齐,判有效。
- 本地复算: q=75/n=1487.25/s=12.75/ceil76=1507.08 over=7.08;float_q=75.642965204236/1487.2499999999998;Path2四行反例全一致,三stdout贴。
- 本轮裁决: 三路qty=75硬一致(红队攻击成立亦佐证floor正确) → [JEV: 3/3 Independent Consensus]相当。无失败,无补派。
- 累计: P1已完成4/30组(CASE-01多数,02三路,03三路,04三路)。已达目标3~5组下限,下轮做P2未测量核对或补第5组CASE-05。
