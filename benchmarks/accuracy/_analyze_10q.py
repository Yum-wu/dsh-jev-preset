# -*- coding: utf-8 -*-
"""小样本重测分析:C1(历史,可信) vs C3(修复后),输出正确率/盲目率/McNemar。

C1 数据为何可复用:`CONFIG_PREFIX.C1` 明示"不要派生子代理"→ subagents 全为 0
→ 单 turn 即终结,`last.ended` 判据对它有效。实测 30/30 零错误、零"无可解析 json"。

用法: python -X utf8 _analyze_10q.py <new_c3_runs.jsonl> [limit]
"""
import io
import json
import sys
from collections import Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, '.')

from jevbench.grading import compare, grade_runs, load_jsonl, summarize  # noqa: E402
from jevbench.solve import blind_candy_min  # noqa: E402
from jevbench.extract import extract_answer  # noqa: E402


def blind_of(suite_row):
    """从题面参数反推盲目答案(题集里没存,故重算)。cases.py 未导出参数,用 expected 反查不可行,
    故改为:直接调用 cases 重建。"""
    return None


def main():
    new_runs = sys.argv[1] if len(sys.argv) > 1 else '_runs-c3-10.jsonl'
    suite = load_jsonl('suite-candy30.jsonl')
    c1 = load_jsonl('runs-candy30-opencode-zen-space-bunny-free.jsonl')
    c3_new = load_jsonl(new_runs)

    new_ids = {r['case_id'] for r in c3_new}
    c1_sub = [r for r in c1 if r['case_id'] in new_ids]
    c3_old_full = load_jsonl('runs-c30-c3-sb.jsonl')
    c3_old = [r for r in c3_old_full if r['case_id'] in new_ids]

    g_new = grade_runs(suite, c3_new)
    g_c1 = grade_runs(suite, c1_sub)
    g_old = grade_runs(suite, c3_old)

    def rate(graded):
        n = len(graded)
        k = sum(r['correct'] for r in graded)
        na = sum(1 for r in graded if r.get('no_answer'))
        return k, n, na

    print('=== 小样本重测(candy,模型=opencode-zen/space-bunny-free)===')
    print(f'题数: {len(new_ids)}')
    print()
    print('| 组 | 正确 | 总数 | 正确率 | 无答案 |')
    print('|---|---|---|---|---|')
    for tag, g in [('C1 单路(历史,可信)', g_c1), ('C3 三路(修复前)', g_old), ('C3 三路(修复后)', g_new)]:
        k, n, na = rate(g)
        pct = f'{k / n:.1%}' if n else '—'
        print(f'| {tag} | {k} | {n} | {pct} | {na} |')

    print()
    print('=== 配对比较(C1 vs 修复后 C3)===')
    cmp_new = compare(g_c1 + g_new, 'C1', 'C3')
    cmp_old = compare(g_c1 + g_old, 'C1', 'C3')
    print(f'  修复前: {cmp_old}')
    print(f'  修复后: {cmp_new}')

    print()
    print('=== 逐题明细(修复后)===')
    by_id = {c['id']: c for c in suite}
    print('| 题 | 期望 | 得到 | 判分 | 耗时 | 子代理 |')
    print('|---|---|---|---|---|---|')
    for r in c3_new:
        c = by_id[r['case_id']]
        g = next(x for x in g_new if x['case_id'] == r['case_id'])
        ans = extract_answer(r.get('text') or '')
        got = ans.get('min_candies') if ans else '(无)'
        el = (r.get('elapsed_ms') or 0) // 1000
        print(f"| {r['case_id'].replace('trap_candy-', '')} | {c['expected']['min_candies']} | {got} | "
              f"{'✅' if g['correct'] else '❌'} | {el}s | {r.get('peak_subagents')} |")

    print()
    print('=== 错误理由分布(修复后)===')
    for k, v in Counter(r['reason'][:40] for r in g_new).most_common():
        print(f'  {v:3d}  {k}')


if __name__ == '__main__':
    main()
