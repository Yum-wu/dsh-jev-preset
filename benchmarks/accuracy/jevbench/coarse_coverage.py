"""粗档派生(coarse_route)对真实历史语料的覆盖率核查。

目的:单元测试只证明 `coarse_route` 与 persona 表一致,不证明它覆盖**真实跑出来的**标识串。
本脚本把 51 个 `_runs-*.jsonl` / `runs-*.jsonl` 里的模型原文过一遍
`extract_route` → `coarse_route`,统计三档分布与「未登记」占比。
"""
import glob
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
from extract import coarse_route, extract_route  # noqa: E402

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "benchmarks", "accuracy")
files = sorted(glob.glob(os.path.join(BASE, "_runs-*.jsonl")) + glob.glob(os.path.join(BASE, "runs-*.jsonl")))

coarse = Counter()
raw_routes = Counter()
untagged = 0
total = 0
unmapped_raw = Counter()

for path in files:
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            text = row.get("text")
            if not isinstance(text, str):
                continue
            total += 1
            route = extract_route(text)
            raw_routes[route] += 1
            if route is None:
                untagged += 1
            bucket = coarse_route(route)
            coarse[bucket] += 1
            if bucket == "未登记" and route is not None:
                unmapped_raw[route] += 1

tagged = total - untagged
print(f"语料文件 {len(files)} 个,记录 {total} 条")
print(f"  其中**无任何首行标识** {untagged} 条({untagged / total * 100:.1f}%)—— 这些是协议前的旧记录,")
print(f"  任何映射表都救不了;有标识的 {tagged} 条才是本表的实际考察面。")
print("\n粗档分布(分母 = 全部 901):")
for key in ("直出", "单路", "多路", "未登记"):
    n = coarse.get(key, 0)
    pct = (n / total * 100) if total else 0.0
    print(f"  {key:<6} {n:>5}  ({pct:5.1f}%)")
mapped = coarse.get("直出", 0) + coarse.get("单路", 0) + coarse.get("多路", 0)
print(f"\n有标识记录的映射率: {mapped}/{tagged} = {mapped / tagged * 100:.1f}%"
      if tagged else "\n有标识记录 0 条")
print(f"原始标识串去重后 {len(raw_routes)} 种")
print("\n未登记的**有标识**原始串(全表见下;`None` 已单列,不在此列):")
for route, n in unmapped_raw.most_common(20):
    print(f"  {n:>5}  {route!r}")
