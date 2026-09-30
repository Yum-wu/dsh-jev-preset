# -*- coding: utf-8 -*-
"""实验 D 的敏感性分析:C3 的 2 个失败是「运行错误」而非「答错」。

两种口径都要报告:
  1. 严格口径(运行失败计为错)—— 保守下界
  2. 有效样本口径(只比较成功完成的题)—— 剔除缺失数据

若两口径结论不同,说明结果对基础设施稳定性敏感,必须说明。
只读。
"""
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, '.')

from jevbench.grading import compare, grade_runs, load_jsonl, summarize  # noqa: E402


def main():
    suite = load_jsonl('_suite-assert.jsonl')
    a12 = load_jsonl('_runs-assert-12.jsonl')
    c3 = load_jsonl('_runs-assert-c3.jsonl')

    failed = {r['case_id'] for r in c3 if r.get('error')}
    print(f'C3 运行失败的题: {sorted(failed)}  (共 {len(failed)} 道)')
    for cid in sorted(failed):
        r = next(x for x in c3 if x['case_id'] == cid)
        print(f"   {cid}: {r.get('error')} | sub={r.get('subagents')} peak={r.get('peak_subagents')} "
              f"tok={r.get('tokens')} | {r.get('elapsed_ms', 0) // 1000}s | text 长度 {len(r.get('text') or '')}")

    print()
    print('=' * 70)
    print('【口径 1】严格:运行失败计为错(即 _grade_expD.py 的口径)')
    print('=' * 70)
    g = grade_runs(suite, a12 + c3)
    s = summarize(g)
    for cfg in ('A1', 'A2', 'C3'):
        a = s[cfg]['answer_accuracy']
        print(f"  {cfg}: {a['k']}/{a['n']} = {a['rate']:.1%}  Wilson={a['wilson95']}")
    print(f"  A2 vs C3: {compare(g, 'A2', 'C3')}")

    print()
    print('=' * 70)
    print('【口径 2】剔除 C3 运行失败的题,只在三方都成功完成的题上比较')
    print('=' * 70)
    keep = [c['id'] for c in suite if c['id'] not in failed]
    sub_a = [r for r in a12 if r['case_id'] in keep]
    sub_c = [r for r in c3 if r['case_id'] in keep]
    g2 = grade_runs(suite, sub_a + sub_c)
    s2 = summarize(g2)
    print(f'  (剔除 {len(failed)} 题,剩 {len(keep)} 题)')
    for cfg in ('A1', 'A2', 'C3'):
        a = s2[cfg]['answer_accuracy']
        print(f"  {cfg}: {a['k']}/{a['n']} = {a['rate']:.1%}  Wilson={a['wilson95']}")
    print(f"  A2 vs C3: {compare(g2, 'A2', 'C3')}")

    print()
    print('=== 结论差异 ===')
    p1 = compare(g, 'A2', 'C3')['mcnemar_p']
    p2 = compare(g2, 'A2', 'C3')['mcnemar_p']
    print(f'  口径1 p={p1} / 口径2 p={p2}')
    if (p1 < 0.05) != (p2 < 0.05):
        print('  ⚠ 两口径显著性不同 → 结果对基础设施稳定性敏感')
    else:
        print('  两口径显著性一致 → 结论对这 2 个失败不敏感')

    print()
    print('=== 成本(仅口径2的题)===')
    mt = {c: s2[c]['mean_tokens'] for c in s2 if s2[c]['mean_tokens']}
    for c, v in sorted(mt.items()):
        print(f'  {c}: {v:,} token')


if __name__ == '__main__':
    main()
