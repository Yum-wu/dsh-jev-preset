# JEV 准确率基准(jevbench v1)

回答一个问题:**JEV 的手段里,哪个真正有效、值不值得那点成本。**
判分全部程序化,不用 LLM 评委。

## 组成

| 文件 | 作用 |
|---|---|
| `jevbench/solve.py` | 参考解(Decimal 精确运算),题面口径的唯一正典 |
| `jevbench/cases.py` | 参数化出题器:8 类数值题 + 3 类对抗题 + 12 条门控题,默认 52 题;同 seed 逐字节确定 |
| `jevbench/grading.py` | 判分、配对比较、难度筛选、错误共识统计、**无答案分离** |
| `jevbench/extract.py` | 抽取答案块与 `[JEV: ...]` 路由标识 |
| `jevbench/stats.py` | Wilson 区间、McNemar 精确检验(标准库实现) |
| `run-bench.mjs` | 逐题开真实 DSH 会话,结果写 `runs.jsonl`(含 `session_id` 可回查) |
| `runner-lib.mjs` | 各臂的约束前缀 + **收敛判据**(纯逻辑,可单测) |
| `../../tests/test_accuracy_bench.py` | 50 个用例守护上面全部逻辑 |
| `../../tests/test-accuracy-runner.mjs` | 15 个用例守护运行器逻辑(含收敛判据回归) |

## 可验证性:基准自身为什么可信

1. **参考解有三类独立证据**(`tests/test_accuracy_bench.py`):手算值;性质/暴力检验
   (tick 对齐边界、下单量可行且最优、回撤 O(n²) 暴力);独立实现比对
   (标准库 `zoneinfo` 逐日扫 4 年、仓内 `jev_assertions` 断言库)。
2. **判分器双向自检**:`selftest` 要求参考答案全判对、扰动答案全判错(测试里跑 20 个 seed)。
3. **运行失败不丢弃**:RATE_LIMIT/超时写入 `error`,判分计为错并单列 `run_errors`。
4. **原始对话可回查**:每行带 `session_id`。
5. **★ 测量链路自身有守卫**(2026-09-30 新增,见 `MEASUREMENT-BUG-2026-09-30.md`):
   - **收敛判据**:JEV 用 `backgroundMode: continuable`,派发三路后父会话 turn
     **立即**结束(子代理仍在后台)。故必须等 **本轮结束 且 无 `running` 子会话
     且(已出答案块 或 静默达标)** 才算收敛 —— 只看 `turn/end` 会把「未收敛」误判为答错。
   - **无答案分离**:判分区分「没答」与「答错」(`no_answer` 字段)。
   - **硬守卫**:某配置无答案率 >20% 时,`jevbench grade` **退出码 3** 并告警,
     拒绝让测量伪影冒充能力结论。

```powershell
npm test                                   # 含本基准 50 用例
cd benchmarks/accuracy
python -m jevbench gen --seed 20260928 --out suite.jsonl
python -m jevbench selftest --suite suite.jsonl   # 期望:全部通过
```

### 扩到足够样本量(重要)

单套 52 题**只能分辨约 20 个百分点的差距**;要看出 10 个百分点需要 **150 题以上**。
多 seed 合并即可,`merge` 会校验 id 唯一并报告题面重复度:

> ⚠️ **扩样前先想清楚检验的统计量**:McNemar 精确检验**只看不一致对**,
> 与总 n 无关。加"两边都对"的题**不会**让 p 更显著 ——
> 本仓 12 题 → 30 题扩样时 p 纹丝不动(都是 0.0312)。
> 扩样的真实收益是**收窄 Wilson 区间**,不是提高显著性。

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
node benchmarks/accuracy/run-bench.mjs --suite suite.jsonl --out runs.jsonl --config A1 --config A2 --dry-run
node benchmarks/accuracy/run-bench.mjs --suite suite.jsonl --out runs.jsonl --config A1 --config A2 --limit 3
node benchmarks/accuracy/run-bench.mjs --suite suite.jsonl --out runs.jsonl --config A1 --config A2   # 断点续跑

cd benchmarks/accuracy
python -m jevbench grade   --suite ..\..\suite.jsonl --runs ..\..\runs.jsonl --out report.json
python -m jevbench compare --suite ..\..\suite.jsonl --runs ..\..\runs.jsonl --a A1 --b A2
```

### 配置臂一览

| 臂 | 预设 | 约束 | 用途 |
|---|---|---|---|
| C0 | standard | 单次直答,禁工具 | 最弱基线 |
| C1 | standard | 单路,可执行代码,禁子代理 | 关键基线 |
| C3 | jev | 无约束,persona 自行门控 | 被测对象(2026-09-30 起在计算题上走「单路+断言」) |
| **A1** | standard | 单路,**禁代码** | **执行断言实验的对照臂** |
| **A2** | standard | 单路,**必须真跑代码复算** | **执行断言实验的处理臂** |
| **C3F** | jev | **显式强制三路** | **复现「三路 vs 断言」**(C3 改版后不再自动走三路) |

> **为什么需要 C3F**:门控改为「断言优先」后,裸 `C3` 在计算类题上**不再派生三路**
> (实测 30/30 `sub=0`)。要测三路本身,必须用 C3F 显式指定。

### A1/A2 的变量隔离(设计要点)

A1 与 A2 **唯一差别**是是否强制跑代码复算;两臂**都禁子代理**。
故 `A1 → A2` 隔离出「断言」的净效应;若用 C1 vs C3 则混入"多路采样"变量,无法归因。

隔离有效性验证:`_check_arms.py` 检查两臂 token 是否约 **×2**
(实测 59,753 vs 119,343)。

## 读结果

- `answer_accuracy` + `wilson95`:区间重叠大 = 样本不够,不下结论。
- **`no_answer`**:「没答」的条数与占比。**`untrustworthy: true` 时正确率不可信**,
  先查测量链路(多半是没等到收敛)。
- `compare` 的 `mcnemar_p < 0.05` 才算显著;`only_A_correct`/`only_B_correct` 看差异方向。
- `false_consensus`:C3 标「Consensus」却答错的比例 —— 三路最该盯的风险。
- `gate_accuracy`:只对 C3 有意义,12 题里 6 该 Fast-Pass、6 该三路。
- `mean_tokens`:含子代理会话。
- `peak_subagents` / `saw_running_child`(每行):留证"这题到底派了几路"。

## 注意(实测)

- **`--provider/--model` 会改你的全局默认模型**:官方 `session/selectModel` 在后台 `saveSelection`
  (`dsh-api-session-controller/lib/types/commands.js:141-166`)。不传则用当前默认模型,两臂同路由即可比。
- **`--settle` 控制静默收敛阈值**(默认 120s):子会话停跑且无答案块时,等这么久才收工。
- 单题实测约 6 万 token(A1)/ 12 万(A2)/ 13 万(C3 新门控)/ **185 万(C3F 三路)**。
- 会话留在侧栏(DSH 无删除端点),`cwd` 在 `%TEMP%\jevbench\`。
- 样本量:52 题只能看出 ~20 个百分点级差异;要看 ~10 点需 150+ 题(用 `merge` 合并多个 seed)。
- 先用 `--config C0 --reps 3` 跑 + `python -m jevbench filter --config C0` 筛掉全对/全错题,再比。
- **Windows 需要 `pip install tzdata`**:Windows 的 Python 不自带 IANA 时区库(`TZPATH` 为空),
  缺它时 `test_ny_open_vs_zoneinfo` 这条**最强的独立证据会被跳过**(输出带 ⚠️ 告警)。
  CI 已显式安装 tzdata 并校验其可用,不允许静默跳过。
- **中文输出编码**:`jevbench` 入口已强制 stdout UTF-8(Windows 控制台默认 cp1252 会抛
  `UnicodeEncodeError`,实测)。若自行 import 其函数并 print,需同样处理。

## 实验脚本索引

`_` 前缀的脚本是实验/取证链的一部分,**已入库**(可用 `git log` 追溯当时怎么跑的):

| 脚本 | 用途 |
|---|---|
| `_audit_measurement.py` | **逐文件审计历史 runs 的测量可信度**(判断哪些数字可引用) |
| `_audit_9q.py` | 核实 9 题批未受测量 bug 影响 |
| `_exp_assert_headroom.py` | headroom 预检(发现常规题 C0 已 96.7%) |
| `_mk_assert_suite.py` | 构造断言实验题集(按题面长度取最难题) |
| `_check_arms.py` | 验证 A1/A2 变量隔离(token ×2) |
| `_grade_expD.py` / `_grade_expD_sens.py` | 三路 vs 断言 + 两口径敏感性分析 |
| `_grade_expA30.py` / `_grade_strong.py` | 30 题 / 强模型判分 |
| `_grade_gate30.py` | 新门控 30 题行为验证 |
| `_grade_c3f_partial.py` | C3F 中途/最终分析(可在跑批中运行) |
| `_diag_c3_fail.py` / `_diag_c3fail2.py` | C3 运行失败根因诊断 |
| `_analyze_blind*.py` | 错答分类:盲目型 vs 其它错 |
| `_probe_turns.mjs` | **多轮收敛诊断**(修复测量 bug 的工具) |
| `_verify_gate.mjs` | 门控端到端验证 |

> 一次性排查脚本用 `_probe_*` 前缀,不入库(例外:`_probe_turns.mjs` 是可复用工具)。
- **Windows 需要 `pip install tzdata`**:Windows 的 Python 不自带 IANA 时区库(`TZPATH` 为空),
  缺它时 `test_ny_open_vs_zoneinfo` 这条**最强的独立证据会被跳过**(输出带 ⚠️ 告警)。
  CI 已显式安装 tzdata 并校验其可用,不允许静默跳过。
- **中文输出编码**:`jevbench` 入口已强制 stdout UTF-8(Windows 控制台默认 cp1252 会抛
  `UnicodeEncodeError`,实测)。若自行 import 其函数并 print,需同样处理。
