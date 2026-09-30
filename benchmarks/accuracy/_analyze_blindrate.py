# -*- coding: utf-8 -*-
"""验证关键怀疑:旧的「C3 盲目率 33%」是否为 bug 产物。

旧代码里 extract_answer 返回 None(无 json 块)时,`got != blind` 恒成立
→ 那 18 条「没出答案」的被算成「非盲目」→ 盲目率被人为压低。

若成立,则旧结论「三路把盲目率从 100% 打到 33%」是纯伪影。
只读。
"""
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, '.')

from jevbench.extract import extract_answer  # noqa: E402
from jevbench.grading import load_jsonl  # noqa: E402
import re


def parse_params(question):
    m = re.search(r'圆形[:：]\s*([\d\s]+)', question)
    s = re.search(r'五角星形[:：]\s*([\d\s]+)', question)
    if not m or not s:
        return None, None
    return [int(x) for x in m.group(1).split()], [int(x) for x in s.group(1).split()]


def blind_min(rc, sc, ia=0, ip=1):
    tc, ts = sum(rc), sum(sc)
    Ac, Pc = rc[ia], rc[ip]
    As, Ps = sc[ia], sc[ip]
    return max((tc - Ac) + (ts - As),
               (tc - Ac - Pc) + ts,
               tc + (ts - As - Ps),
               (tc - Pc) + (ts - Ps)) + 1


def blind_rate(runs, suite, label):
    n_ans = n_no = n_blind = n_correct = 0
    for r in runs:
        c = suite[r['case_id']]
        rc, sc = parse_params(c['question'])
        bm = blind_min(rc, sc)
        ans = extract_answer(r.get('text') or '')
        got = ans.get('min_candies') if ans else None
        want = c['expected']['min_candies']
        if got is None:
            n_no += 1
            continue
        n_ans += 1
        if str(got) == str(want):
            n_correct += 1
        elif str(got) == str(bm):
            n_blind += 1
    n = len(runs)
    print(f'{label}: 共{n}题 | 出答案 {n_ans} | 无答案 {n_no} | 正确 {n_correct} | '
          f'盲目 {n_blind}')
    print(f'    盲目率(只看出答案的)  = {n_blind}/{n_ans} = {n_blind / n_ans:.1%}' if n_ans else '    —')
    print(f'    盲目率(旧口径,无答案计非盲目) = {n_blind}/{n} = {n_blind / n:.1%}')
    return n_blind, n_ans, n


def main():
    suite = {c['id']: c for c in load_jsonl('suite-candy30.jsonl')}
    c1 = load_jsonl('runs-candy30-opencode-zen-space-bunny-free.jsonl')
    c3_old = load_jsonl('runs-c30-c3-sb.jsonl')

    print('=== C1 单路(历史数据,可信)===')
    blind_rate(c1, suite, 'C1')
    print()
    print('=== C3 三路(修复前,含测量 bug)===')
    blind_rate(c3_old, suite, 'C3-old')
    print()
    print('⚠ 若 C3-old 的「旧口径盲目率」≈33%,则证实旧结论是 bug 产物。')


if __name__ == '__main__':
    main()
