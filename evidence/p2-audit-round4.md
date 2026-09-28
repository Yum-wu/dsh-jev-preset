# P2 未测量标注核对(Round 4)
- 核对命令: `python benchmarks/run_stress_matrix.py` stdout(末2行中文乱码实为控制台编码问题,关键行可辨: 总用例30/三路验证指标全None未测量)+ benchmark-results.json 四指标 null 确认。
- 结论: docs/benchmark-report.md 二节4行未测量、docs/performance-spec.md 一节7行+二节P50/P99未测量、benchmark-results.json 四 null 标注,本轮仍属实(P1仅4个案,非30矩阵统计口径,不得回填)。
- 唯一可写回的实证: evidence/p1-case*.md 四组(01多数,02/03/04三路),属个案归档,非矩阵指标。P2不改任何数字,只确认标注有效。
- 下轮: P3跑全量 npm test 与 smoke.mjs。

- Round18复核: README.md: 1 / README_EN.md: 1 / docs/benchmark-report.md: 4 / docs/performance-spec.md: 13。仍属实,零回填。
