# -*- coding: utf-8 -*-
"""执行断言专项判分:A1(禁代码) vs A2(强制复算)。

核心问题:强制跑一次复算,能否降低数值计算题的出错率?
只读。
"""
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, '.')

from jevbench.grading import compare, grade_runs, load_jsonl, summarize  # noqa: E402


def main():
    suite = load_jsonl('_suite-assert.jsonl')
    runs = load_jsonl('_runs-assert-12.jsonl')
    g = grade_runs(suite, runs)
    s = summarize(g)

    print('=== 执行断言专项:A1(禁代码) vs A2(强制复算)===')
    print('| 臂 | 约束 | 正确 | 正确率 | Wilson 95% | 平均 token |')
    print('|---|---|---|---|---|---|')
    for cfg, desc in (('A1', '禁代码纯推理'), ('A2', '强制跑代码复算')):
        a = s[cfg]['answer_accuracy']
        print(f"| {cfg} | {desc} | {a['k']}/{a['n']} | {a['rate']:.1%} | {a['wilson95']} | {s[cfg]['mean_tokens']} |")
    print()
    print('配对比较:', compare(g, 'A1', 'A2'))
    print()

    print('=== 逐题 ===')
    print('| 题 | 类别 | A1 | A2 | 结果 |')
    print('|---|---|---|---|---|')
    for cid in sorted({r['case_id'] for r in g}):
        a1 = next(r for r in g if r['case_id'] == cid and r['config'] == 'A1')
        a2 = next(r for r in g if r['case_id'] == cid and r['config'] == 'A2')
        if a1['correct'] and a2['correct']:
            m = '同对'
        elif a2['correct']:
            m = '**A2 独对**'
        elif a1['correct']:
            m = '**A1 独对**'
        else:
            m = '同错'
        print(f"| {cid} | {a1['category']} | {'✅' if a1['correct'] else '❌'} | "
              f"{'✅' if a2['correct'] else '❌'} | {m} |")

    print()
    print('=== 错误理由 ===')
    for cfg in ('A1', 'A2'):
        errs = [r for r in g if r['config'] == cfg and not r['correct']]
        print(f'  {cfg} 错 {len(errs)} 条:')
        for r in errs:
            print(f"     {r['case_id']:26s} {r['reason'][:64]}")


if __name__ == '__main__':
    main()
