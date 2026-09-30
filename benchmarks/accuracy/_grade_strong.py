# -*- coding: utf-8 -*-
"""强模型(ds-flash)复跑:headroom 边界验证。

假设:强模型 A1 基线更高 → headroom 变小 → A2 增益应显著缩小或归零。
若成立,则「执行断言有效」这一结论**依赖模型能力**(弱模型受益更大)。

同时对比弱模型(space-bunny)同 30 题的结果。
只读。
"""
import io
import sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, '.')

from jevbench.grading import compare, grade_runs, load_jsonl, summarize  # noqa: E402


def table(tag, runs):
    suite = load_jsonl('_suite-assert30.jsonl')
    g = grade_runs(suite, runs)
    s = summarize(g)
    print(f'--- {tag} ---')
    print('| 臂 | 正确 | 正确率 | Wilson 95% | 平均 token | 运行失败 |')
    print('|---|---|---|---|---|---|')
    for c in ('A1', 'A2'):
        if c not in s:
            continue
        a = s[c]['answer_accuracy']
        errs = sum(1 for r in g if r['config'] == c and r.get('run_error'))
        print(f"| {c} | {a['k']}/{a['n']} | {a['rate']:.1%} | {a['wilson95']} | {s[c]['mean_tokens']} | {errs} |")
    if 'A1' in s and 'A2' in s:
        print(f"配对: {compare(g, 'A1', 'A2')}")
    print()
    return g, s


def main():
    print('=' * 72)
    print('强模型 vs 弱模型:执行断言的增益是否随模型能力衰减?')
    print('=' * 72)
    print()

    weak = load_jsonl('_runs-assert-30.jsonl')
    strong = load_jsonl('_runs-assert-strong.jsonl')

    gw, sw = table('弱模型 opencode-zen/space-bunny-free', weak)
    gs, ss = table('强模型 combo/ds-flash', strong)

    print('=' * 72)
    print('=== 对照汇总 ===')
    print('=' * 72)
    print('| 模型 | A1 基线 | A2 | 增益 | p | 成本倍数 |')
    print('|---|---|---|---|---|---|')
    for tag, s in (('弱 space-bunny', sw), ('强 ds-flash', ss)):
        if 'A1' not in s or 'A2' not in s:
            continue
        a1, a2 = s['A1']['answer_accuracy'], s['A2']['answer_accuracy']
        gain = a2['rate'] - a1['rate']
        p = compare(grade_runs(load_jsonl('_suite-assert30.jsonl'),
                               weak if tag.startswith('弱') else strong), 'A1', 'A2')['mcnemar_p']
        ratio = s['A2']['mean_tokens'] / s['A1']['mean_tokens']
        print(f"| {tag} | {a1['rate']:.1%} | {a2['rate']:.1%} | {gain:+.1%} | {p} | ×{ratio:.2f} |")

    print()
    print('=== 强模型 A1 错题(看是否仍有 headroom)===')
    for r in gs:
        if r['config'] == 'A1' and not r['correct']:
            print(f"  {r['case_id']:26s} {r['reason'][:60]}")
    n_err = sum(1 for r in gs if r['config'] == 'A1' and not r['correct'])
    if n_err == 0:
        print('  (无 —— A1 已 100%,零 headroom)')

    print()
    print('=== 强模型 A2 错题 ===')
    for r in gs:
        if r['config'] == 'A2' and not r['correct']:
            print(f"  {r['case_id']:26s} {r['reason'][:60]}")


if __name__ == '__main__':
    main()
