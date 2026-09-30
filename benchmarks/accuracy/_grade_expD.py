# -*- coding: utf-8 -*-
"""实验 D:C3(三路+断言) vs A2(单路+断言) —— 三路在断言已足够时是否纯浪费。

三臂对比:
  A1 = 单路 + 禁代码        (无断言基线)
  A2 = 单路 + 强制复算      (断言净效应)
  C3 = JEV 三路 + 断言      (多路净效应,叠加在断言之上)

核心问题:A2 已经 100% 时,C3 多花的 ×20 成本买到什么?
只读。
"""
import io
import sys
from collections import Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, '.')

from jevbench.grading import compare, grade_runs, load_jsonl, summarize  # noqa: E402


def main():
    suite = load_jsonl('_suite-assert.jsonl')
    runs = []
    for f in ('_runs-assert-12.jsonl', '_runs-assert-c3.jsonl'):
        try:
            runs.extend(load_jsonl(f))
        except FileNotFoundError:
            print(f'(缺 {f},跳过)')
    if not runs:
        print('无数据')
        return
    g = grade_runs(suite, runs)
    s = summarize(g)

    print('=== 实验 D:三路在断言之上是否还有增益 ===')
    print('| 臂 | 配置 | 正确 | 正确率 | Wilson 95% | 平均 token | 子代理 |')
    print('|---|---|---|---|---|---|---|')
    desc = {'A1': '单路+禁代码', 'A2': '单路+强制复算', 'C3': 'JEV三路+断言'}
    for cfg in ('A1', 'A2', 'C3'):
        if cfg not in s:
            continue
        a = s[cfg]['answer_accuracy']
        subs = sorted({r.get('subagents') for r in runs if r.get('config') == cfg})
        print(f"| {cfg} | {desc[cfg]} | {a['k']}/{a['n']} | {a['rate']:.1%} | {a['wilson95']} | "
              f"{s[cfg]['mean_tokens']} | {subs} |")

    print()
    print('=== 配对比较 ===')
    for a, b in (('A1', 'A2'), ('A2', 'C3')):
        if a in s and b in s:
            print(f'  {a} vs {b}: {compare(g, a, b)}')

    print()
    print('=== 成本比 ===')
    mt = {c: s[c]['mean_tokens'] for c in s if s[c]['mean_tokens']}
    if 'A2' in mt:
        for c, v in sorted(mt.items()):
            print(f'  {c}: {v:,} token  = A2 的 {v / mt["A2"]:.2f} 倍')

    print()
    print('=== 逐题 ===')
    ids = sorted({r['case_id'] for r in g})
    cfgs = [c for c in ('A1', 'A2', 'C3') if c in s]
    print('| 题 | ' + ' | '.join(cfgs) + ' |')
    print('|---|' + '---|' * len(cfgs))
    for cid in ids:
        cells = []
        for c in cfgs:
            row = next((r for r in g if r['case_id'] == cid and r['config'] == c), None)
            cells.append('✅' if row and row['correct'] else ('❌' if row else '—'))
        print(f'| {cid} | ' + ' | '.join(cells) + ' |')

    print()
    print('=== C3 错误理由 ===')
    for r in g:
        if r['config'] == 'C3' and not r['correct']:
            print(f"  {r['case_id']:26s} {r['reason'][:60]}")


if __name__ == '__main__':
    main()
