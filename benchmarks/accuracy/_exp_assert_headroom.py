# -*- coding: utf-8 -*-
"""执行断言专项 · 第一步:headroom 检查。

用已有 C0(纯推理、禁工具,最弱基线)数据找出**答错的题** ——
只有这些题才可能显出「执行断言」的增益;全对的题无区分力。

只读,不发起网络调用。
"""
import io
import sys
from collections import Counter, defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, '.')

from jevbench.grading import grade_runs, load_jsonl  # noqa: E402

NUMERIC = ('tick', 'lot', 'vwap', 'tiered_mm', 'ny_open', 'ex_rights', 'cagr', 'mdd')


def main():
    suite = load_jsonl('suite150.jsonl')
    c0 = load_jsonl('runs-c0-40q-dsflash.jsonl')

    g = grade_runs(suite, c0)
    num = [r for r in g if r['category'] in NUMERIC]
    print(f'C0 基线(40 题,ds-flash,纯推理禁工具)')
    print(f'  其中 numeric {len(num)} 题')
    k = sum(r['correct'] for r in num)
    print(f'  正确 {k}/{len(num)} = {k / len(num):.1%}')
    print()

    by_cat = defaultdict(lambda: [0, 0])
    for r in num:
        by_cat[r['category']][0] += r['correct']
        by_cat[r['category']][1] += 1
    print('| 类别 | C0 正确 | 有 headroom? |')
    print('|---|---|---|')
    for c, (a, b) in sorted(by_cat.items()):
        print(f'| {c} | {a}/{b} | {"✅" if a < b else "❌ 饱和"} |')

    print()
    wrong = [r for r in num if not r['correct']]
    print(f'=== C0 答错的题({len(wrong)} 道,即候选实验题)===')
    for r in wrong:
        print(f"  {r['case_id']:34s} {r['reason'][:46]}")

    print()
    print('=== 全 90 题 numeric 是否都跑过? ===')
    all_num_ids = {c['id'] for c in suite if c['category'] in NUMERIC}
    ran = {r['case_id'] for r in c0}
    print(f'  suite150 numeric 共 {len(all_num_ids)} 题;C0 只跑过 {len(all_num_ids & ran)} 题')
    print(f'  未跑过的 {len(all_num_ids - ran)} 题:seed 不同,需新跑')


if __name__ == '__main__':
    main()
