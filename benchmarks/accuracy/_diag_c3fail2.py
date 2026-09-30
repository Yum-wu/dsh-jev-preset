# -*- coding: utf-8 -*-
"""C3 失败根因验证:重跑旧版失败的 2 题 ×3 次。

假设:旧版这两题被强制走三路 → 三路不稳定 → 挂;
      新版走单路+断言 → 稳定通过。
只读。
"""
import io
import sys
from collections import Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, '.')

from jevbench.grading import grade_case, load_jsonl  # noqa: E402


def main():
    suite = {c['id']: c for c in load_jsonl('_suite-assert.jsonl')}
    runs = load_jsonl('_runs-c3fail-retry.jsonl')

    print('=== 重跑结果(新版门控,2 题 ×3 次)===')
    print('| 题 | rep | 子代理 | token | 耗时 | 正确 | 答案 |')
    print('|---|---|---|---|---|---|---|')
    ok = 0
    for r in sorted(runs, key=lambda x: (x['case_id'], x['rep'])):
        c = suite[r['case_id']]
        g = grade_case(c, r.get('text') or '')
        from jevbench.extract import extract_answer
        ans = extract_answer(r.get('text') or '')
        ok += g['correct']
        print(f"| {r['case_id']} | {r['rep']} | {r.get('subagents')} | {r.get('tokens'):,} | "
              f"{r.get('elapsed_ms', 0) // 1000}s | {'✅' if g['correct'] else '❌'} | {ans} |")

    n = len(runs)
    print()
    print(f'成功 {ok}/{n};错误 {sum(1 for r in runs if r.get("error"))}/{n}')
    print(f'子代理分布: {dict(Counter(r.get("subagents") for r in runs))}')

    print()
    print('=== 与旧版对照 ===')
    old = load_jsonl('_runs-assert-c3.jsonl')
    for cid in ('vwap-20260928-02', 'tiered_mm-20260928-00'):
        o = next(r for r in old if r['case_id'] == cid)
        news = [r for r in runs if r['case_id'] == cid]
        print(f'\n{cid}')
        print(f"  旧版: sub={o.get('subagents')} tok={o.get('tokens'):,} "
              f"{o.get('elapsed_ms', 0) // 1000}s → {o.get('error') or 'ok'}")
        for r in news:
            print(f"  新版 rep{r['rep']}: sub={r.get('subagents')} tok={r.get('tokens'):,} "
                  f"{r.get('elapsed_ms', 0) // 1000}s → {r.get('error') or 'ok'}")


if __name__ == '__main__':
    main()
