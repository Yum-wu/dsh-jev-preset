# dsh-jev-preset 工作区规则

> 本文件只管**本插件特有**的约定;通用规则(沟通方式、红线、自主边界)在 `~/.dsh/AGENTS.md`;
> **BOM 表与其余本机运维硬规则已迁到 `Desktop\DeepSeekHarness\AGENTS.md`**(2026-10-07,只在该工作区自动注入)。
> 使用者说明见 `README.md` / `README_EN.md`;设计取舍见 `docs/architecture.md`。

## 这是什么

JEV(Judgment-Execution-Verification)自适应交叉验证 preset:一个注入 persona 的宿主插件 + 一套可执行断言库 + 一份持续自优化的实测台账。

- **persona 正典在 `cordis.patch.yml` 的 `prefix` 块里,不在任何 `.md`** —— md 只是它的影子。
- `docs/` 是**结论载体**(台账 / 附录状态 / 结构性边界)。改代码不同步 md = 制造「已闭环」假象。
- 本目录是**独立 git 仓库**;父仓 `DeepSeekHarness/.gitignore` 忽略 `plugins/`,故父仓看不到它。

## 硬规则(踩坑固化)

1. **改 persona 必须同步 `README.md` 与 `README_EN.md`** —— `tests/test_ps_python_parity.py` 守卫三处一致(实测踩过:persona 改了,两个 README 完全没同步)。
2. **persona 里的效果数字必须带基线 + 样本量 + 仓内出处** —— 只报终值(如「正确率 100%」)会被 `tests/test_no_unsupported_claims.py` 判红;还必须声明「本仓当前题集下的观测,非普适保证」。
3. **套件数是预注册棘轮**:`tests/pre_registered.py` 的 `SUITE_FILES` / `SUITE_TESTS` / `HARNESS_TESTS` / `TOTAL_ASSERTIONS_FLOOR` 是常量。**新增测试文件必须同步 `SUITE_FILES`**,否则 `tools/g_check.py` 的 `g1()`(`suites == expected == declared`)恒假,`tests/test_no_silent_skips.py` 直接红。
4. **`npm test` 是一条 `&&` 长链,只暴露第一个失败** —— 改了多处必须逐个 suite 跑,否则后面的红永远看不见(实测一次潜伏 3 处)。
5. **改 `docs/structural-boundaries.md` 前必读该文件 §一 B7**:一切会随代码变动而腐烂的值(行号、计数)**必须删除或改指权威源**,不要在文档里写新值 —— 改写下一轮即腐。
6. **文档机械约束(全仓扫描器,写错就红)**:
   - 表格每行格数必须等于表头格数;正文里的裸竖线写成 `&#124;`(`tests/test_markdown_tables.py`)
   - 任何承载文本的文件不得出现 U+FFFD 替换字符(`tests/test_no_encoding_damage.py`)
   - `docs/` 与 `benchmarks/` 下的 `.md` 写 `k/n` 与百分比区间时,Wilson 区间必须算对(`tools/_wilson_doc_scan.py`)
   - 新增 `.md` 一律 UTF-8、LF、不带 BOM

## 命令

```powershell
npm test                          # 全链;⚠ 只暴露第一个失败
npm run audit:evasion             # 跑 G5 规避审计,日志有变动则自动 commit docs/evasion-audit.log
npm run audit:evasion:nocommit    # 同上但不提交
npm run validate
```

## 目录指针

| 路径 | 是什么 |
|---|---|
| `cordis.patch.yml` | persona 正典(`prefix` 块)+ preset 配置 |
| `packages/assertions/` | 断言库:Python CLI(`--func <名>`)+ PS 模块 `JevAssertions.psm1`;CLI 退出码契约 0/1/2/3 |
| `tools/g_check.py` | 总闸:`g1()` 形状门(suites == expected == declared)+ G5 规避审计门 |
| `tools/mutation_harness.py` | 变异测试台;棘轮常量在 `tests/pre_registered.py` |
| `tools/boundary_check.py` | 结构性边界门控 + 文档可腐烂面扫描(`--scan-rot`) |
| `docs/structural-boundaries.md` | 固有边界 B1–B7 + 需人工拍板的 H1–H5 |
| `docs/evasion-ledger.md` | **只追加**的规避台账,不改历史条目 |
| `docs/self-optimize-rounds.md` | **只追加**的轮次台账 |
| `docs/appendix-status.md` | persona 附录逐条状态表 |
| `tests/` | 元判据(计数 / 路径 / 编码)集中在此;套件数以 `tests/pre_registered.py` 的 `SUITE_FILES` 为准 |
