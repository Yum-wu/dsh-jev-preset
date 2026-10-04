# -*- coding: utf-8 -*-
r"""扫描本仓文档里的 Wilson 区间,独立复算核对(只读,不写回仓库)。

## 动机(Round 44/45)

我在 Round 44 记账时写「A1/A2 的 Wilson 与 EXP-G 原文逐位一致」,实际**只有 A1 与 C3 一致**,
A2 不一致(`[75.8%,100%]` vs 复算 `[75.7%,100.0%]`,精确 75.749924%)——
**拿两个对上就说三个都对**。本脚本把「逐行核对每一个」变成机械动作。

## 判据(避免三类误报,均为实测踩过的)

1. **只查表格行**(以 `|` 开头)。散文句里的 `Wilson 区间 [34%,100%]` 的 x/y 与区间无关,
   初版把它当 p/n 读 → 误报。
2. **取区间之前最近的 x/y**。G5 审计表的列序是 `轮次 … Wilson 检出/总数`,
   `0/4` 落在区间**之后**,不是它的 p/n;初版取全行第一个 x/y → 误报 8 处。
3. **精度自适应**:文档写整数百分比(`89%`)时,真值 88.648291 四舍五入到整数就是 89,
   这是**正确**的。判据 = 文档值与该精度的正确舍入值之差 ≤ 半格(0.5×10⁻ᵈ)。
   初版固定 0.051 容差 → 把 12 处正确的整数舍入全报成错。

## 它查得出什么

真错:文档写 `88.7%` 而真值 88.648291(一位小数应为 88.6,差 0.0517 > 半格 0.05)。
这正是红队 a3d373a8 查出的那类**转抄错误**。
"""
import os
import re
import sys
from decimal import Decimal, getcontext

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

getcontext().prec = 50
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
#: ⚠ Round 67:本脚本也是**全仓扫描器**,同样要「不走出仓根」——
#: Round 66 给三个 `.py` 扫描器加了剪枝,却漏了 `.md` 扫描器(`tests/test_markdown_tables.py`)
#: 与**本脚本**(AST 普查才发现)。**原语只有一个定义**(`tests/_fs_guard.py`),
#: 这里 import 它而不是再抄一遍 —— 抄第 N 遍就是下一次复发的种子。
#: ⚠ 但**不在模块级 import**:Round 67 红队实测,模块级 `sys.path.insert` 会在
#: **被 import 时**把 `tests/` 插进调用方的 `sys.path`(残留副作用)。挪进函数里,
#: 只在真要遍历时才加载。
def _fs_guard_module():
    sys.path.insert(0, os.path.join(ROOT, "tests"))
    import _fs_guard
    return _fs_guard

PAIR = re.compile(r"(\d+)\s*/\s*(\d+)")
INTERVAL = re.compile(r"\[\s*(\d+(?:\.\d+)?)\s*%\s*,\s*(\d+(?:\.\d+)?)\s*%\s*\]")


def wilson(p, n, z=Decimal("1.96")):
    p, n = Decimal(str(p)), Decimal(str(n))
    if n <= 0:
        return Decimal(0), Decimal(1)
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * ((p * (1 - p) / n + z * z / (4 * n * n)).sqrt()) / den
    return c - h, c + h


def _decimals(text):
    """文档里该数字写了几个小数位。"""
    return len(text.split(".")[1]) if "." in text else 0


def check_line(line):
    """返回该行所有「可核对」的 (lo_txt, hi_txt, p, n) 与不满足的项。"""
    if not line.lstrip().startswith("|"):
        return []                       # 规则 1:只查表格行
    pairs = [(m.start(), int(m.group(1)), int(m.group(2))) for m in PAIR.finditer(line)]
    out = []
    for iv in INTERVAL.finditer(line):
        # 规则 2:取区间之前**最近的** x/y
        before = [p for p in pairs if p[0] < iv.start() and p[2] > 0]
        if not before:
            continue
        _pos, k, tot = before[-1]
        out.append((iv.group(1), iv.group(2), k / tot, tot, iv.start()))
    return out


def main():
    fsg = _fs_guard_module()
    checked = skipped = bad = 0
    for sub in ("docs", "benchmarks"):
        base = os.path.join(ROOT, sub)
        for dirpath, _dirs, files in os.walk(base):
            # ⚠ Round 67:参照系必须是**本循环自己那个 root**(`base`),不是 `ROOT` ——
            # 初版传 `os.path.realpath(ROOT)` 而 walk 根是 `base`(= ROOT/docs 或
            # ROOT/benchmarks),`inside()` 对 `base` 下的一切恒真 → **剪枝完全空转**。
            # 是红队绕过 5 的**同一形状**让我发现的(「空转判据」)。
            fsg.prune_escaped(dirpath, _dirs, os.path.realpath(base))
            if ".git" in dirpath:
                continue
            for f in sorted(files):
                if not f.endswith(".md"):
                    continue
                fp = os.path.join(dirpath, f)
                rel = os.path.relpath(fp, ROOT)
                with open(fp, encoding="utf-8") as fh:
                    for lineno, line in enumerate(fh, 1):
                        for lo_txt, hi_txt, p, n, _ in check_line(line):
                            checked += 1
                            exp_lo, exp_hi = wilson(p, n)
                            ok = True
                            detail = []
                            for txt, exp in ((lo_txt, exp_lo), (hi_txt, exp_hi)):
                                d = _decimals(txt)
                                true_v = float(exp) * 100
                                # 接受「四舍五入」或「截断」两种写法 —— 本仓两种都有
                                # (CANDY-CROSS-MODEL.md:26 用舍入 65%,同表 :27 用截断 43%),
                                # 那是排版约定差异,不是测量错误。本判据只抓**真的写错数**。
                                scale = 10 ** d
                                cands = {round(true_v, d),
                                         (int(true_v * scale) / scale) if true_v >= 0 else round(true_v, d)}
                                if float(txt) not in cands:
                                    ok = False
                                    detail.append(
                                        f"{txt}% vs 真值 {true_v:.6f}%"
                                        f"(该精度可接受值 {sorted(cands)},差 {abs(float(txt)-true_v):.4f})")
                            if not ok:
                                bad += 1
                                print(f"[错] {rel}:{lineno}  p={p:.6f} n={n}")
                                for d in detail:
                                    print(f"     {d}")
    print(f"\n可核对 {checked} 处,错值 {bad} 处")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
