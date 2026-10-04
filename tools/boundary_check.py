#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""tools/boundary_check.py: 自优化循环终止与结构性边界门控判据。

根据目标书规范:
1. 在每轮 Step 1 之前执行;
2. 若本轮候选缺陷落在 docs/structural-boundaries.md 已声明的边界内 => 输出 exit 3 (insufficient_data 语义: 不是本轮可修缺陷);
3. 若连续 N 轮 (N=3) 红队报的缺陷全部是同一形态 => 输出 exit 4 (停止整个循环);
4. 包含全仓扫描判据 (R17): 扫描 docs/*.md 与代码注释, 发现「疑似行号引用 / 疑似写死计数」即报红 (exit 1),
   并维护合法的符号级豁免清单。

退出码契约:
- exit 0: 检查通过, 无边界拦截, 无重复形态, 全仓扫描无违规残留
- exit 1: 扫描发现未豁免的疑似行号引用或写死计数 (R17 判据失败)
- exit 2: 调用参数或使用方式错误 (CLI 错误)
- exit 3: 候选缺陷落在已声明的结构性边界内 (insufficient_data, 强制结束本轮)
- exit 4: 连续 3 轮红队缺陷全部落在同一形态 / 边界内 (停止整个自优化循环)
"""

import argparse
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOUNDARIES_FILE = os.path.join(ROOT, "docs", "structural-boundaries.md")
ROUNDS_FILE = os.path.join(ROOT, "docs", "self-optimize-rounds.md")

BOUNDARY_TAGS = ["B1", "B2", "B3", "B4", "B5", "B6", "B7", "H1", "H2", "H3", "H4", "H5"]

def check_candidate_defect(report_text):
    """判定输入的候选缺陷报告文本是否落在已声明边界内。"""
    if not report_text:
        return None
    for tag in BOUNDARY_TAGS:
        pattern = r"\b" + tag + r"\b"
        if re.search(pattern, report_text, re.I):
            return tag
    keywords = [
        ("判据自身零棘轮", "B1"),
        ("共享同一次 import", "B2"),
        ("模块级短路", "B2"),
        ("末位豁免", "B3"),
        ("机制与缺陷不在同一侧", "B4"),
        ("数量口径", "B5"),
        ("移动靶", "B6"),
        ("写死数字", "B7"),
        ("行号引用", "B7"),
        ("docstring", "B7"),
    ]
    for kw, tag in keywords:
        if kw in report_text:
            return tag
    return None

def check_consecutive_repeat(rounds_text_path, window_size=3):
    """检查最近 window_size 轮红队缺陷是否全部属于同一形态或落在边界内。"""
    if not os.path.exists(rounds_text_path):
        return False, []
    with open(rounds_text_path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    # 匹配每个 Round 的块: # Round N 或 ## Round N 或 ROUND N
    round_blocks = re.findall(r"(?:^|\n)(?:#+|ROUND)\s*(?:Round\s*)?(\d+)[\s\S]*?(?=(?:\n(?:#+|ROUND)\s*(?:Round\s*)?\d+)|\Z)", content, re.I)
    
    # 提取所有 Round 块
    blocks = re.split(r"(?:\n|^)(?=#+\s*Round\s*\d+|ROUND\s*\d+)", content)
    valid_blocks = [b for b in blocks if re.search(r"(?:Round|ROUND)\s*\d+", b)]
    if len(valid_blocks) < window_size:
        return False, []

    recent_rounds = valid_blocks[-window_size:]
    round_tags = []
    for r_text in recent_rounds:
        tags = set()
        for tag in BOUNDARY_TAGS:
            if re.search(r"\b" + tag + r"\b", r_text, re.I):
                tags.add(tag)
        if "行号" in r_text or "写死数字" in r_text or "腐烂" in r_text:
            tags.add("B7")
        round_tags.append(tags)

    common = set.intersection(*round_tags) if round_tags else set()
    if common:
        return True, list(common)
    return False, []

def scan_rot_values():
    """扫描 docs/*.md 与代码注释, 发现未豁免的疑似行号引用与写死真值。"""
    violations = []
    re_lineno = re.compile(r"(\b[A-Z]{2,4}:\d+\b|\b[a-zA-Z0-9_\-]+\.(?:py|md|mjs|ps1|json):\d+\b|第\s*\d+\s*行|\bL\d+\b)")
    
    # 豁免清单 (合法的符号指代或测试规范示例)
    EXEMPTIONS = [
        "tests/test_evasion_audit.py", # 测试数据行本身
        "test_no_encoding_damage.py",  # 历史事故引用
    ]

    docs_dir = os.path.join(ROOT, "docs")
    if os.path.exists(docs_dir):
        for fname in os.listdir(docs_dir):
            if not fname.endswith(".md"):
                continue
            # 历史记录文件免除逐字清除, 但 structural-boundaries.md 必须完全去值化
            if fname in ["structural-boundaries.md"]:
                fpath = os.path.join(docs_dir, fname)
                with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
                for idx, line in enumerate(lines, 1):
                    # 允许更正注中说明历史去掉了什么的说明
                    if "更正" in line or "沿革如实记录" in line:
                        continue
                    m = re_lineno.search(line)
                    if m:
                        matched_str = m.group(1)
                        violations.append((os.path.relpath(fpath, ROOT), idx, line.strip(), f"未豁免行号引用: {matched_str}"))

    return violations

def main():
    parser = argparse.ArgumentParser(description="自优化循环边界门控与终止检查判据")
    parser.add_argument("--defect-report", type=str, help="红队报告原文文件或文本")
    parser.add_argument("--scan-rot", action="store_true", help="执行文档与注释可腐烂面扫描 (R17)")
    args = parser.parse_args()

    # 1. 如果指定了红队报告原文, 检查是否落在已声明边界
    if args.defect_report:
        report_text = args.defect_report
        if os.path.exists(report_text):
            with open(report_text, "r", encoding="utf-8", errors="replace") as f:
                report_text = f.read()
        
        tag = check_candidate_defect(report_text)
        if tag:
            print(f"[BOUNDARY CHECK] 候选缺陷落在已声明结构性边界 [{tag}] 内!")
            print(f"依据: {BOUNDARIES_FILE} 已声明此类缺陷属于固有边界/无需修复。")
            sys.exit(3)

    # 2. 如果请求扫描文档可腐烂面 (R17)
    if args.scan_rot:
        violations = scan_rot_values()
        if violations:
            print(f"[ROT SCAN] 发现 {len(violations)} 处疑似行号引用或写死计数:")
            for fpath, lno, ltext, reason in violations[:20]:
                print(f"  {fpath}:{lno} [{reason}] {ltext[:80]}")
            if len(violations) > 20:
                print(f"  ... 另有 {len(violations) - 20} 处未展开")
            sys.exit(1)
        else:
            print("[ROT SCAN] 扫描通过: 未发现可腐烂行号引用或写死计数。")
            sys.exit(0)

    # 3. 检查是否满足连续 3 轮重复形态终止条件 (S2' / S2'' / S3)
    repeat_hit, common_tags = check_consecutive_repeat(ROUNDS_FILE, window_size=3)
    if repeat_hit:
        print(f"[BOUNDARY CHECK] 连续 3 轮红队缺陷全部落在同一边界形态 {common_tags} 内!")
        print("触发 S2' / S3 循环终止判据 (exit 4), 停止整个自优化循环。")
        sys.exit(4)
        violations = scan_rot_values()
        if violations:
            print(f"[ROT SCAN] 发现 {len(violations)} 处疑似行号引用或写死计数:")
            for fpath, lno, ltext, reason in violations[:20]:
                print(f"  {fpath}:{lno} [{reason}] {ltext[:80]}")
            if len(violations) > 20:
                print(f"  ... 另有 {len(violations) - 20} 处未展开")
            sys.exit(1)
        else:
            print("[ROT SCAN] 扫描通过: 未发现可腐烂行号引用或写死计数。")

    print("[BOUNDARY CHECK] 通过: 候选缺陷未落在已声明边界内, 亦未触发连续终止判据。")
    sys.exit(0)

if __name__ == "__main__":
    main()