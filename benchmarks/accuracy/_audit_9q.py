# -*- coding: utf-8 -*-
"""核实:9 题 candy C1/C3 实验(runs-candy.jsonl)是否真的不受测量 bug 影响。

若 C3 的 9 条全部出了答案块(无 no_answer),则 11.1%→44.4% / ×18.7
这些数字**依然有效**,不应被标注为作废。
只读。
"""
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, '.')

from jevbench.extract import extract_answer, extract_route  # noqa: E402
from jevbench.grading import grade_case, load_jsonl  # noqa: E402


def main():
    runs = load_jsonl('runs-candy.jsonl')
    # 找 9 题 suite
    for f in ('suite150.jsonl', 'suite-candy-control.jsonl'):
        try:
            suite = {c['id']: c for c in load_jsonl(f)}
            if all(r['case_id'] in suite for r in runs):
                print(f'题集来源: {f}')
                break
        except FileNotFoundError:
            continue
    else:
        print('未找到匹配题集')
        return

    print()
    print('| 配置 | 题 | 子代理 | 有答案块 | 正确 | 判分理由 |')
    print('|---|---|---|---|---|---|')
    tally = {}
    for r in runs:
        c = suite[r['case_id']]
        g = grade_case(c, r.get('text') or '')
        ans = extract_answer(r.get('text') or '')
        has = ans is not None
        k = r['config']
        tally.setdefault(k, [0, 0, 0])
        tally[k][0] += 1
        tally[k][1] += has
        tally[k][2] += g['correct']
        print(f"| {k} | {r['case_id']} | {r.get('subagents')} | {'✅' if has else '❌'} | "
              f"{'✅' if g['correct'] else '❌'} | {g['reason'][:40]} |")

    print()
    print('=== 汇总 ===')
    for k, (n, has, ok) in sorted(tally.items()):
        print(f'  {k}: n={n} 有答案块={has} 正确={ok} → 正确率 {ok / n:.1%}')
        tok = [r.get('tokens') for r in runs if r['config'] == k and r.get('tokens')]
        if tok:
            print(f'      平均 token {sum(tok) / len(tok):,.0f}')

    print()
    print('=== 关键判定 ===')
    c3 = [r for r in runs if r['config'] == 'C3']
    no_ans = sum(1 for r in c3 if extract_answer(r.get('text') or '') is None)
    print(f'  C3 的 {len(c3)} 条中,无答案块 {no_ans} 条')
    if no_ans == 0:
        print('  ✅ 9 题实验未受测量 bug 影响 → 11.1%→44.4% / ×18.7 数字**依然有效**')
    else:
        print(f'  ❌ 受影响({no_ans}/{len(c3)})')


if __name__ == '__main__':
    main()
