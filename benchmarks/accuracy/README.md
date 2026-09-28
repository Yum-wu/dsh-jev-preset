# JEV 准确率基准(jevbench v1)

回答一个问题:**JEV 三路(C3)是否比单路+执行代码(C1)更准,值不值得多出的成本。**
判分全部程序化,不用 LLM 评委。

## 组成

| 文件 | 作用 |
|---|---|
| `jevbench/solve.py` | 参考解(Decimal 精确运算),题面口径的唯一正典 |
| `jevbench/cases.py` | 参数化出题器:8 类数值题 + 3 类对抗题 + 12 条门控题,默认 52 题;同 seed 逐字节确定 |
| `jevbench/grading.py` | 判分、配对比较、难度筛选、错误共识统计 |
| `jevbench/stats.py` | Wilson 区间、McNemar 精确检验(标准库实现) |
| `run-bench.mjs` | 逐题开真实 DSH 会话,结果写 `runs.jsonl`(含 `session_id` 可回查) |
| `../../tests/test_accuracy_bench.py` | 30 个用例守护上面全部逻辑 |

## 可验证性:基准自身为什么可信

1. **参考解有三类独立证据**(`tests/test_accuracy_bench.py`):手算值;性质/暴力检验
   (tick 对齐边界、下单量可行且最优、回撤 O(n²) 暴力);独立实现比对
   (标准库 `zoneinfo` 逐日扫 4 年、仓内 `jev_assertions` 断言库)。
2. **判分器双向自检**:`selftest` 要求参考答案全判对、扰动答案全判错(测试里跑 20 个 seed)。
3. **运行失败不丢弃**:RATE_LIMIT/超时写入 `error`,判分计为错并单列 `run_errors`。
4. **原始对话可回查**:每行带 `session_id`。

```powershell
npm test                                   # 含本基准 33 用例
cd benchmarks/accuracy
python -m jevbench gen --seed 20260928 --out suite.jsonl
python -m jevbench selftest --suite suite.jsonl   # 期望:全部通过
```

### 扩到足够样本量(重要)

单套 52 题**只能分辨约 20 个百分点的差距**;要看出 10 个百分点需要 **150 题以上**。
多 seed 合并即可,`merge` 会校验 id 唯一并报告题面重复度:

```powershell
python -m jevbench merge --seeds 20260928,20260929,20260930 --out suite150.jsonl
# 已合并 3 个 seed → 168 题(唯一题面 155)
python -m jevbench selftest --suite suite150.jsonl
```

⚠️ 门控题模板数量有限(16 条),合并多 seed 时会有少量题面重复 ——
`merge` 会打印重复条数。重复题不影响判分正确性,但对统计无增益,
若需更高唯一度可继续扩充 `cases.py` 的 `GATE_TEMPLATES`。

## 跑评测

```powershell
node benchmarks/accuracy/run-bench.mjs --suite suite.jsonl --out runs.jsonl --config C1 --config C3 --dry-run
node benchmarks/accuracy/run-bench.mjs --suite suite.jsonl --out runs.jsonl --config C1 --config C3 --limit 3
node benchmarks/accuracy/run-bench.mjs --suite suite.jsonl --out runs.jsonl --config C1 --config C3   # 断点续跑

cd benchmarks/accuracy
python -m jevbench grade   --suite ..\..\suite.jsonl --runs ..\..\runs.jsonl --out report.json
python -m jevbench compare --suite ..\..\suite.jsonl --runs ..\..\runs.jsonl --a C1 --b C3
```

| 配置 | 预设 | 约束 |
|---|---|---|
| C0 | standard | 单次直答,禁工具 |
| C1 | standard | 单路,可执行代码,禁子代理(**关键基线**) |
| C3 | jev | 无约束,persona 自行门控(被测对象) |

## 读结果

- `answer_accuracy` + `wilson95`:区间重叠大 = 样本不够,不下结论。
- `compare` 的 `mcnemar_p < 0.05` 才算显著;`only_C1_correct`/`only_C3_correct` 看差异方向。
- `false_consensus`:C3 标「Consensus」却答错的比例 —— 三路最该盯的风险。
- `gate_accuracy`:只对 C3 有意义,12 题里 6 该 Fast-Pass、6 该三路。
- `mean_tokens`:含子代理会话。

## 注意(实测)

- **`--provider/--model` 会改你的全局默认模型**:官方 `session/selectModel` 在后台 `saveSelection`
  (`dsh-api-session-controller/lib/types/commands.js:141-166`)。不传则用当前默认模型,两配置同路由即可比。
- 单题实测约 6.4–6.8 万 token(含系统提示词缓存读),C3 走三路会更多;先 `--limit` 小跑估算。
- 会话留在侧栏(DSH 无删除端点),`cwd` 在 `%TEMP%\jevbench\`。
- 样本量:52 题只能看出 ~20 个百分点级差异;要看 ~10 点需 150+ 题(用 `merge` 合并多个 seed)。
- 先用 `--config C0 --reps 3` 跑 + `python -m jevbench filter --config C0` 筛掉全对/全错题,再比 C1/C3。
- **Windows 需要 `pip install tzdata`**:Windows 的 Python 不自带 IANA 时区库(`TZPATH` 为空),
  缺它时 `test_ny_open_vs_zoneinfo` 这条**最强的独立证据会被跳过**(输出带 ⚠️ 告警)。
  CI 已显式安装 tzdata 并校验其可用,不允许静默跳过。
- **中文输出编码**:`jevbench` 入口已强制 stdout UTF-8(Windows 控制台默认 cp1252 会抛
  `UnicodeEncodeError`,实测)。若自行 import 其函数并 print,需同样处理。
