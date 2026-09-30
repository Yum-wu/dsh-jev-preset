# -*- coding: utf-8 -*-
"""从 suite150 抽一个「执行断言专项」子集:跨类别、参数规模最大(最易错)。

选取原则:
- 每类取题面最长(参数最多)的题 → 最大化手算出错概率
- 覆盖有断言库的类别:tick / vwap / tiered_mm / ny_open / ex_rights / mdd
- 审题零陷阱(这些题的条件都显式,陷阱在计算不在阅读)

用法: python -X utf8 _mk_assert_suite.py [每类题数] [输出文件]
"""
import io
import json
import sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 只取有对应断言库实现的类别
CATS = ['tick', 'vwap', 'tiered_mm', 'ny_open', 'ex_rights', 'mdd']


def main():
    per = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    out = sys.argv[2] if len(sys.argv) > 2 else '_suite-assert.jsonl'

    rows = [json.loads(l) for l in open('suite150.jsonl', encoding='utf-8') if l.strip()]
    by = defaultdict(list)
    for r in rows:
        if r['category'] in CATS:
            by[r['category']].append(r)

    picked = []
    for cat in CATS:
        items = by[cat]
        # 按题面长度降序 = 参数最多 = 最易错
        items.sort(key=lambda r: -len(r['question']))
        picked.extend(items[:per])

    with open(out, 'w', encoding='utf-8', newline='\n') as f:
        for r in picked:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')

    print(f'已写 {len(picked)} 题 → {out}')
    for r in picked:
        print(f"  {r['id']:26s} {r['category']:10s} 题面 {len(r['question']):4d} 字符  期望 {r['expected']}")


if __name__ == '__main__':
    main()
