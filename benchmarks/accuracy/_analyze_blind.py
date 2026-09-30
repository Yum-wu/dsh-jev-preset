# -*- coding: utf-8 -*-
"""判定 C3 的错答属于哪种失效模式:
  A) 盲目(blind) —— 答案 == blind_candy_min,即忽略了"形状靠手感可分辨"
  B) 其它错   —— 既不等于正确答案,也不等于盲目值(可能是建模/推理错)

blind_candy_min 需从题面参数重算,故通过 jevbench.cases 重建同 seed 题集反查。
只读。
"""
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, '.')

from jevbench import cases as C  # noqa: E402
from jevbench.extract import extract_answer  # noqa: E402
from jevbench.grading import load_jsonl  # noqa: E402


def rebuild_map():
    """重建成 id -> {answer, blind} 映射。cases.build_suite(seed) 的 seed 从 id 里解析。"""
    suite = load_jsonl('suite-candy30.jsonl')
    seeds = sorted({int(r['id'].split('-')[-2]) for r in suite})
    out = {}
    for sd in seeds:
        for c in C.build_suite(sd):
            if c['category'] != 'trap_candy':
                continue
            # 从题面里解析参数不可靠,改用 solve 直接对同参数重算不可行
            # → 改为:build_suite 内部已算过 blind,若未随题集落盘,则此处只能标 unknown
            out[c['id']] = c
    return out


def main():
    runs = load_jsonl(sys.argv[1] if len(sys.argv) > 1 else '_runs-c3-10.jsonl')
    suite = {c['id']: c for c in load_jsonl('suite-candy30.jsonl')}
    print('题集里 trap_candy 条目的键:', sorted(next(c for c in suite.values() if c['category'] == 'trap_candy').keys()))
    print()
    for r in runs:
        c = suite[r['case_id']]
        ans = extract_answer(r.get('text') or '')
        got = ans.get('min_candies') if ans else None
        want = c['expected']['min_candies']
        mark = 'OK' if str(got) == str(want) else 'ERR'
        print(f"{r['case_id']} want={want} got={got} {mark}")
        # 打印题面里的参数行,便于人工核对盲目值
    print()
    print('--- 首题题面前 400 字(看参数是否在题面)---')
    print(suite[runs[0]['case_id']]['question'][:400])


if __name__ == '__main__':
    main()
