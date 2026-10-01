# -*- coding: utf-8 -*-
"""
grade_audit — 对照臂「禁代码」口径缺口的**登记牌**(附录 B6)。

⚠⚠ 本模块**不是**审计能力,只是一张登记牌(红队 31ebcbb2 判定,2026-10-01):

  1. **B6 本来是可修的,而且修法比本模块彻底得多。**
     红队给出三条代码证据,本轮已逐条核实成立:
       a. `dsh-web-app/presets/standard.patch.yml` 显式挂载 `tool-bash`/`tool-pwsh`/
          `tool-fs` ⇒ A1 臂(同为 `standard` 预设)**物理上能执行代码**;
       b. 宿主 `dsh-web-app/cordis.patch.yml` 命中执行工具 **0 处**
          ⇒ 执行工具**只由 preset 提供**;
       c. `dsh-agent-preset-registry/.../invariant.js` 明写工具
          "resolve against the **empty global layer**" ⇒ **preset 的插件清单就是工具面**。
     推论:声明一个**不含** `tool-bash`/`tool-pwsh`/`tool-fs`/`tool-jobs` 的 `no-code` 预设,
     把 A1 指过去,就能**物理消除**偷跑 —— 工具面本身就是证明,无需任何事后文本审计。
     **本模块是那种做法的替代品,而替代品在能力上弱得多。**

  2. **文本扫描在开放世界下只能给上界,永远不能证明「未执行」。**
     `_runs-*.jsonl` 的 13 个字段中**零个工具轨迹字段**(实测)。
     反例(合法):A1 调 pwsh 跑完断言拿到 30/30,再用自然语言输出最终 JSON、
     不复述任何命令/栈/路径 → text 洁净 → 本模块报 0 → **而它确实执行了**。
     只有**白名单式强制拦截**(工具面里根本没有 pwsh)才能给出「未执行」。

  3. 因此 `flagged` **只能读作「检出痕迹」**,绝不等于「偷跑数」;
     `detection_power` 字段把这句话常驻在返回值里。
     **把它写成「佐证 A1 没偷跑」是 R13 违规**(红队已点名 round log 里那句)。

保留它的唯一理由:顺手把「runs 无工具轨迹」这条**结构性事实**记录下来并可机读。
原先 EXP-F 那句「实测 A1 文本里有『代码』字样」实为 0/30(假),本模块的字段清单是对的。
"""
import re

__all__ = ["flag_code_execution", "audit_baseline_arm"]

# ⚠ 以下模式**只能用于「上界提示」**,不得当作判定依据(见模块 docstring 第 2 点)。
# 误报率实测偏高:纯讨论里提到一个 .py 文件名就会被判「执行」。
# 故此处**刻意不含**文件路径 / shell 提示符这类高误报模式 ——
# 红队 31ebcbb2 实测 7/9 纯讨论样本被它们误判,删掉后仅保留真·强信号。
_EXEC_PATTERNS = (
    re.compile(r"Traceback \(most recent call last\)"),
    re.compile(r"^\s*File \"[^\"]+\", line \d+", re.M),
    re.compile(r"\bexit code\b|\bexit status\b", re.I),
)

# 「仅仅在讨论」的词表 —— 出现它们**不**算执行证据。
# 红队 31ebcbb2 实测:初版漏了「脚本/文件/路径/运行」,
# 导致「你的脚本 write_report.py 第 40 行有 off-by-one」这类**纯讨论**被判为执行。
_DISCUSSION_ONLY = re.compile(
    r"代码|函数|实现|算法|复杂度|重构|编程|脚本|文件|路径|运行|执行|建议|参考|示例|写法")

def flag_code_execution(text):
    """从一次作答文本里判断是否存在**执行痕迹**。

    返回 `(flagged: bool, evidence: list[str], discussed: bool)`:
      flagged    是否检出执行痕迹(强信号)
      evidence   命中的片段(供人工复核,避免黑盒判罚)
      discussed  是否**仅仅**在讨论代码(讨论不算违规,但会让人误以为跑了)

    刻意**不**把「提到代码」判成违规 —— 那是 EXP-F 原检查的错误,
    会把纯文字讨论误报成偷跑,进而**高估**真实差距(方向与 B6 关心的问题相反)。
    """
    text = text or ""
    hits = []
    for pat in _EXEC_PATTERNS:
        for m in pat.finditer(text):
            frag = m.group(0).strip()
            if frag and frag not in hits:
                hits.append(frag)
    discussed = bool(_DISCUSSION_ONLY.search(text))
    return bool(hits), hits, discussed


def audit_baseline_arm(runs, config="A1"):
    """审计某个对照臂的 runs,报出「检出执行痕迹」的样本。

    `runs` 是 `_runs-*.jsonl` 解析出的记录列表(或已 grade 的列表)。
    返回:
      config, total, flagged, flagged_case_ids
      discuss_only     只讨论代码、未检出执行痕迹的样本数
      detection_power  **本次审计的检出能力** —— 因无工具轨迹,
                       只能证明「检出痕迹」,不能证明「没跑」;该字段显式说明这一点。
    """
    flagged, flagged_ids, discuss_only = 0, [], 0
    total = 0
    for r in runs:
        if r.get("config") != config:
            continue
        total += 1
        hit, _ev, discussed = flag_code_execution(r.get("text", ""))
        if hit:
            flagged += 1
            flagged_ids.append(r.get("case_id"))
        elif discussed:
            discuss_only += 1
    return {
        "config": config,
        "total": total,
        "flagged": flagged,
        "flagged_case_ids": flagged_ids,
        "discuss_only": discuss_only,
        "detection_power":
            "无工具轨迹:本次审计只能证明「检出执行痕迹」,不能证明「未执行」。"
            "阴性结果(=没检出)不等于没跑代码。",
    }
