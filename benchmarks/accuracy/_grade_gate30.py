# -*- coding: utf-8 -*-
"""判分:新门控下裸 C3 在 30 道计算题上的行为。

预期(2026-09-30 门控改版后):C3 应走「单路+断言」,即
  - subagents 全为 0
  - token 约 13 万/题(A2 量级,而非三路的 ~140 万)
  - 正确率接近 A2(100%)
若 C3 表现与 A2 一致 → 门控改版生效的直接证据。
只读。
"""
import io
import sys
from collections import Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, '.')

from jevbench.grading import compare, grade_runs, load_jsonl, summarize  # noqa: E402


def main():
    suite = load_jsonl('_suite-assert30.jsonl')
    c3 = load_jsonl('_runs-assert-c3-30.jsonl')
    a2 = load_jsonl('_runs-assert-30.jsonl')
    a2 = [r for r in a2 if r['config'] == 'A2']

    g = grade_runs(suite, c3 + a2)
    s = summarize(g)

    print('=== 新门控下 C3(30 题)vs A2(单路+断言)===')
    print('| 臂 | 正确 | 正确率 | 平均 token | 子代理分布 |')
    print('|---|---|---|---|---|')
    for c in ('A2', 'C3'):
        if c not in s:
            continue
        a = s[c]['answer_accuracy']
        subs = dict(Counter(r.get('subagents') for r in (a2 if c == 'A2' else c3)))
        print(f"| {c} | {a['k']}/{a['n']} | {a['rate']:.1%} | {s[c]['mean_tokens']:,} | {subs} |")

    print()
    print(f"配对 A2 vs C3: {compare(g, 'A2', 'C3')}")
    print()

    # 首行标识分布:验证是否走了「断言通过」
    print('=== C3 首行 [JEV: ...] 标识分布 ===')
    import re
    routes = Counter()
    for r in c3:
        t = r.get('text') or ''
        m = re.search(r'\[JEV:\s*([^\]]+)\]', t)
        routes[m.group(1).strip() if m else '(无标识)'] += 1
    for k, v in routes.most_common():
        print(f'  {v:3d}  {k}')

    print()
    print('=== C3 错题 ===')
    for r in g:
        if r['config'] == 'C3' and not r['correct']:
            print(f"  {r['case_id']:26s} {r['reason'][:60]}")


if __name__ == '__main__':
    main()
