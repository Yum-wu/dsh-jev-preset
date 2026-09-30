# -*- coding: utf-8 -*-
"""从题面解析糖果题参数,判定每个错答是「盲目」还是「其它错」。

blind = 忽略"形状靠手感可分辨"(配比由对手定)的答案。
若 错答 == blind → 信息提取层失败(漏读条件)
若 错答 != blind → 推理/建模层失败(读到了也算不对)
只读。
"""
import io
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, '.')

from jevbench.extract import extract_answer  # noqa: E402
from jevbench.grading import load_jsonl  # noqa: E402


def parse_params(question):
    """从题面抓「圆形:6 9 5」与「五角星形:4 3 3」。"""
    m = re.search(r'圆形[:：]\s*([\d\s]+)', question)
    s = re.search(r'五角星形[:：]\s*([\d\s]+)', question)
    if not m or not s:
        return None, None
    rc = [int(x) for x in m.group(1).split()]
    sc = [int(x) for x in s.group(1).split()]
    return rc, sc


def candy_min(rc, sc, ia=0, ip=1):
    tc, ts = sum(rc), sum(sc)
    Ac, Pc = rc[ia], rc[ip]
    As, Ps = sc[ia], sc[ip]

    def avoidable(x, y):
        return ((x <= tc - Ac and y <= ts - As)
                or (x <= tc - Ac - Pc and y <= ts)
                or (x <= tc and y <= ts - As - Ps)
                or (x <= tc - Pc and y <= ts - Ps))

    for n in range(0, tc + ts + 1):
        for x in range(max(0, n - ts), min(n, tc) + 1):
            if not avoidable(x, n - x):
                return n
    return tc + ts


def blind_min(rc, sc, ia=0, ip=1):
    tc, ts = sum(rc), sum(sc)
    Ac, Pc = rc[ia], rc[ip]
    As, Ps = sc[ia], sc[ip]
    return max((tc - Ac) + (ts - As),
               (tc - Ac - Pc) + ts,
               tc + (ts - As - Ps),
               (tc - Pc) + (ts - Ps)) + 1


def main():
    runs = load_jsonl(sys.argv[1] if len(sys.argv) > 1 else '_runs-c3-10.jsonl')
    suite = {c['id']: c for c in load_jsonl('suite-candy30.jsonl')}

    print('| 题 | 期望(读到) | 盲目值(漏读) | 得到 | 判定 |')
    print('|---|---|---|---|---|')
    tally = {'correct': 0, 'blind': 0, 'other_err': 0, 'no_ans': 0, 'unparsed': 0}
    for r in runs:
        c = suite[r['case_id']]
        q = c['question']
        rc, sc = parse_params(q)
        ans = extract_answer(r.get('text') or '')
        got_s = ans.get('min_candies') if ans else None
        want = c['expected']['min_candies']
        if rc is None:
            print(f"| {r['case_id']} | {want} | ? | {got_s} | 题面解析失败 |")
            tally['unparsed'] += 1
            continue
        cm, bm = candy_min(rc, sc), blind_min(rc, sc)
        if got_s is None:
            verdict, key = '未出答案', 'no_ans'
        elif str(got_s) == str(want):
            verdict, key = '✅ 正确', 'correct'
        elif str(got_s) == str(bm):
            verdict, key = f'❌ 盲目(={bm})', 'blind'
        else:
            verdict, key = f'❌ 其它错(盲目={bm})', 'other_err'
        tally[key] += 1
        print(f"| {r['case_id'].replace('trap_candy-', '')} | {want} | {bm} | {got_s} | {verdict} |")

    n = sum(tally.values())
    print()
    print('=== 汇总 ===')
    for k in ('correct', 'blind', 'other_err', 'no_ans', 'unparsed'):
        if tally[k]:
            print(f'  {k}: {tally[k]}/{n} = {tally[k] / n:.1%}')
    if tally['blind'] + tally['other_err']:
        tot = tally['blind'] + tally['other_err']
        print()
        print(f"  错答中 盲目占比 {tally['blind']}/{tot} = {tally['blind'] / tot:.1%}"
              f"（盲目=信息提取层失败；其余=推理/建模层失败）")


if __name__ == '__main__':
    main()
