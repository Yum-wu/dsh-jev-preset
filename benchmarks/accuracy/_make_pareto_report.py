# -*- coding: utf-8 -*-
"""
生成 `docs/pareto-frontier.md` —— 成本–准确率帕累托前沿的**单一真源报告**。

## 为什么需要这个脚本(附录 B4)

本仓关于「三路采样到底贵多少」有**三个不同数字**,且都出自实测:

| 出处 | 数字 | 实际基准 |
|---|---|---|
| `EXP-G-THREE-PATH-VS-ASSERTION.md:29` | ×10.61 | **以 A2 为基准**(1,266,507 / 119,343) |
| `EXP-F-ASSERTION-EFFECT.md:59` | ×20 | **以 A1 为基准**(1,266,507 / 59,753 ≈ 21.2) |
| `EXP-G-THREE-PATH-VS-ASSERTION.md:194` | ×15.3 | **另一个实验**(30 题批 C3F,不是 12 题批) |

三个数**本身都不算错**,但**没有任何一处写明基准** ——
于是「三路贵 10 倍还是 20 倍」这种问题无法回答,不同文档的读者会各取一个数。

这正是 B4 要消灭的:数字散落各处、单位与基准不统一,读者无法一眼看出性价比拐点。
本脚本把**基准固定为 A1(单路+禁代码)= ×1**,其余全部换算到同一基准再出表。

## 换算依据(可复核,不是拍脑袋)

```
A1 平均 token  59,753   (EXP-F:33 / EXP-G:27)
A2 平均 token 119,343   (EXP-F:33 / EXP-G:28)   -> 119343/59753 = ×1.997 ≈ ×2.00
C3 平均 token 1,266,507 (EXP-G:29)              -> 1266507/59753 = ×21.20
```

三者的绝对 token 数在 EXP-G:27-29 有原始记录,可逐条复核。

运行:
    python -B benchmarks/accuracy/_make_pareto_report.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

from pareto import Method, render_markdown  # noqa: E402

# 强制 UTF-8:Windows 默认 stdout/stderr 是 cp936(gbk),**重定向/管道**时中文变乱码,
# 而本仓文本产物一律 UTF-8 —— 第三方 `> out.txt` 后按 UTF-8 读只会得到乱码。
# 三条约束(都由实测逼出来):
#   ① **stdout 与 stderr 都要改** —— 异常路径的 traceback 同样会被重定向进文件;
#   ② 必须容忍 `sys.stdout is None`(pythonw / GUI 宿主)—— 否则兜底分支自己会二次崩溃;
#   ③ 兜底用 `getattr(_s, 'buffer', None)`,不直接取 `.buffer`。
# 守卫:tests/test_tool_stdout_encoding.py
# 包在 `__main__` 里:否则**被 import 时**会改写调用方的 stdout/stderr 编码
# (红队 `77ed8102` 实测:`import tools.evasion_audit` 会把调用方的 latin-1 强制改成 utf-8)。
if __name__ == "__main__":
    for _name in ("stdout", "stderr"):
        _s = getattr(sys, _name, None)
        if _s is None:
            continue
        try:
            _s.reconfigure(encoding="utf-8")
        except Exception:                   # pragma: no cover - 兜底老解释器
            import io
            _buf = getattr(_s, "buffer", None)
            if _buf is not None:
                setattr(sys, _name, io.TextIOWrapper(_buf, encoding="utf-8"))
    del _name, _s

# 基准 = A1(单路 + 禁代码)。绝对 token 出自 EXP-G:27-29,换算基准在此**写明**。
BASELINE = "A1 单路+禁代码"
TOK_A1, TOK_A2, TOK_C3 = 59753, 119343, 1266507

# 注:C3 是 12 题批的结果(EXP-G:27-29),与 30 题批的 C3F(EXP-G:194,×15.3)
# **不是同一个实验**,故不进本表 —— 混进来会让「12 题 vs 30 题」的难度差异
# 被误读成方法差异。
METHODS = [
    Method("A1 单路+禁代码(基准)", 50.0, TOK_A1 / TOK_A1, 12,
           "EXP-G-THREE-PATH-VS-ASSERTION.md:27", "本表基准,×1"),
    Method("A2 单路+强制复算", 100.0, TOK_A2 / TOK_A1, 12,
           "EXP-G-THREE-PATH-VS-ASSERTION.md:28", "成本 ×2,准确率 +50pp"),
    Method("C3 JEV三路+断言", 83.3, TOK_C3 / TOK_A1, 12,
           "EXP-G-THREE-PATH-VS-ASSERTION.md:29",
           f"比 A2 **更贵 {TOK_C3/TOK_A2:.1f} 倍**且准确率低 16.7pp;"
           f"原文档写 ×10.61 是**以 A2 为基准**,此处换算到 A1 基准"),
]


def main():
    # 不需要在这里再调 verify_report:render_markdown 开头就会调(2026-10-02 Round 45 装的门),
    # 此处原有一次显式调用,装门之后成了冗余 —— 属我自己改动造成的孤儿,已删。
    body = render_markdown(METHODS)
    text = f"""# 成本–准确率帕累托前沿(自动生成,勿手改)

> 本文件由 `benchmarks/accuracy/_make_pareto_report.py` 生成。
> 手改会在下次生成时被覆盖,且 `tests/test_pareto_report.py` 会因格式不符而红。

**基准**:`{BASELINE}` = ×1。**所有成本倍数都换算到同一基准** ——
本仓此前对同一实验存在 ×10.61 / ×20 两个数字,差异全部来自基准不同(见脚本 docstring)。

**样本**:12 题批(`EXP-G` §)。30 题批的 C3F(×15.3)是**另一个实验**,不混入本表。

{body}

## 读法

- **帕累托前沿 = 「是」的行**:它们是**没有任何其他方法能以更低成本达到同等准确率**的那些。
  在本表里只有 A1 与 A2 在前沿上 —— C3 处在右上角的**劣势位**(比 A2 贵 10.6 倍且更不准),
  即**既不在前沿、也不在任何 Pareto 意义上占优**。
- 这就是「三路在断言之上增益 0」的成本侧表述:它不是「贵一点」,而是**又贵又差**。

## 已知的口径边界

- 本表只覆盖 **12 题批**。30 题批的对照在 `EXP-G` §9.4,样本不同,不可直接合并。
- 「准确率」是**判分器判定通过率**,不是收益率;`n=12` 时 Wilson 区间宽达几十个百分点,
  请连同区间一起读,不要只看点估计(R10)。
"""
    out = os.path.join(ROOT, "docs", "pareto-frontier.md")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(text)
    print(text)
    print(f"\n[written] {out}")


if __name__ == "__main__":
    main()
