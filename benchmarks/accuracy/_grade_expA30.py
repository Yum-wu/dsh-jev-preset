# -*- coding: utf-8 -*-
"""A 扩样判分:30 题 A1(禁代码) vs A2(强制复算)。

目的:12 题时 p=0.0312 接近阈值,扩到 30 题复核。
只读。
"""
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, '.')

from jevbench.grading import compare, grade_runs, load_jsonl, summarize  # noqa: E402


def main():
    suite = load_jsonl('_suite-assert30.jsonl')
    runs = load_jsonl('_runs-assert-30.jsonl')
    g = grade_runs(suite, runs)
    s = summarize(g)

    print('=== A 扩样:30 题,A1(禁代码) vs A2(强制复算)===')
    print('| 臂 | 约束 | 正确 | 正确率 | Wilson 95% | 平均 token |')
    print('|---|---|---|---|---|---|')
    for c, d in (('A1', '禁代码纯推理'), ('A2', '强制跑代码复算')):
        a = s[c]['answer_accuracy']
        print(f"| {c} | {d} | {a['k']}/{a['n']} | {a['rate']:.1%} | {a['wilson95']} | {s[c]['mean_tokens']} |")
    print()
    print('配对比较:', compare(g, 'A1', 'A2'))
    print(f"no_answer: A1={s['A1']['no_answer']}  A2={s['A2']['no_answer']}")
    print()

    print('=== 与 12 题子集对照 ===')
    ids12 = {c['id'] for c in load_jsonl('_suite-assert.jsonl')}
    g12 = [r for r in g if r['case_id'] in ids12]
    import collections
    cf = collections.defaultdict(lambda: [0, 0])
    for r in g12:
        cf[r['config']][0] += r['correct']
        cf[r['config']][1] += 1
    for c in ('A1', 'A2'):
        k, n = cf[c]
        print(f'  {c} (12 题子集): {k}/{n} = {k / n:.1%}')
    print(f"  配对(12 题): {compare(g12, 'A1', 'A2')}")
    print()

    print('=== A1 错题明细 ===')
    errs = [r for r in g if r['config'] == 'A1' and not r['correct']]
    print(f'A1 错 {len(errs)}/{s["A1"]["answer_accuracy"]["n"]}:')
    for r in errs:
        print(f"   {r['case_id']:26s} {r['reason'][:58]}")

    print()
    print('=== A2 错题明细 ===')
    errs2 = [r for r in g if r['config'] == 'A2' and not r['correct']]
    print(f'A2 错 {len(errs2)}:')
    for r in errs2:
        print(f"   {r['case_id']:26s} {r['reason'][:58]}")

    print()
    print('=== 分题型 ===')
    bycat = collections.defaultdict(lambda: {'A1': [0, 0], 'A2': [0, 0]})
    for r in g:
        bycat[r['category']][r['config']][0] += r['correct']
        bycat[r['category']][r['config']][1] += 1
    print('| 类别 | A1 | A2 |')
    print('|---|---|---|')
    for c in sorted(bycat):
        a1, a2 = bycat[c]['A1'], bycat[c]['A2']
        print(f'| {c} | {a1[0]}/{a1[1]} | {a2[0]}/{a2[1]} |')


if __name__ == '__main__':
    main()
