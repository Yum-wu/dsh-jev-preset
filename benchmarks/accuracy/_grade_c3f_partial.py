# -*- coding: utf-8 -*-
"""C3F(强制三路)中间分析:已完成的题先看方向。

可在跑批进行中安全运行(只读已完成的行)。
"""
import io
import sys
from collections import Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, '.')

from jevbench.grading import compare, grade_runs, load_jsonl, summarize  # noqa: E402


def main():
    suite = load_jsonl('_suite-assert30.jsonl')
    try:
        c3f = load_jsonl('_runs-assert-c3f-30.jsonl')
    except FileNotFoundError:
        print('尚无数据')
        return

    done_ids = {r['case_id'] for r in c3f}
    a2 = [r for r in load_jsonl('_runs-assert-30.jsonl') if r['config'] == 'A2' and r['case_id'] in done_ids]

    print(f'=== C3F(强制三路)已完成 {len(c3f)} 题 ===')
    print(f'子代理分布: {dict(Counter(r.get("subagents") for r in c3f))}')
    print(f'运行失败: {sum(1 for r in c3f if r.get("error"))}/{len(c3f)}')
    print(f'平均 token: {sum(r.get("tokens") or 0 for r in c3f) // max(1, len(c3f)):,}')
    print()

    g = grade_runs(suite, c3f + a2)
    s = summarize(g)
    print('| 臂 | 正确 | 正确率 | 平均 token |')
    print('|---|---|---|---|')
    for c in ('A2', 'C3F'):
        if c in s:
            a = s[c]['answer_accuracy']
            print(f"| {c} | {a['k']}/{a['n']} | {a['rate']:.1%} | {s[c]['mean_tokens']:,} |")
    print()
    print(f"配对 A2 vs C3F: {compare(g, 'A2', 'C3F')}")
    print()

    print('=== 逐题 ===')
    for cid in sorted(done_ids):
        r2 = next((r for r in g if r['case_id'] == cid and r['config'] == 'A2'), None)
        rf = next((r for r in g if r['case_id'] == cid and r['config'] == 'C3F'), None)
        if r2 and rf:
            print(f"  {cid:26s} A2={'✅' if r2['correct'] else '❌'} C3F={'✅' if rf['correct'] else '❌'}"
                  f"{'  ← C3F 独错' if r2['correct'] and not rf['correct'] else ''}"
                  f"{'  ← C3F 独对' if rf['correct'] and not r2['correct'] else ''}")

    print()
    print('=== C3F 错题理由 ===')
    for r in g:
        if r['config'] == 'C3F' and not r['correct']:
            print(f"  {r['case_id']:26s} {r['reason'][:60]}")


if __name__ == '__main__':
    main()
