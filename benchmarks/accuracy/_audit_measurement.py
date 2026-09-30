# -*- coding: utf-8 -*-
"""审计:哪些历史结论受测量 bug 影响、哪些不受。

判据:某 runs 文件里的 C3 行若存在「无答案」(无可解析 json)或运行失败,
      则其正确率/盲目率/成本均不可信。

只读。
"""
import io
import glob
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, '.')

from jevbench.grading import grade_case, load_jsonl  # noqa: E402


def find_suite(case_id):
    for f in glob.glob('suite*.jsonl'):
        try:
            for c in load_jsonl(f):
                if c['id'] == case_id:
                    return c
        except Exception:
            continue
    return None


def audit(path):
    runs = load_jsonl(path)
    cfgs = {}
    for r in runs:
        cfgs.setdefault(r.get('config'), []).append(r)
    print(f'\n--- {os.path.basename(path)} ({len(runs)} 行) ---')
    for cfg, rows in sorted(cfgs.items()):
        no_ans = 0
        errs = 0
        for r in rows:
            if r.get('error'):
                errs += 1
                continue
            c = find_suite(r['case_id'])
            if c is None:
                continue
            g = grade_case(c, r.get('text') or '')
            if g.get('no_answer'):
                no_ans += 1
        subs = sorted({r.get('subagents') for r in rows if r.get('subagents') is not None})
        flag = '❌ 受影响' if (no_ans or errs) else '✅ 可信'
        print(f'  {cfg}: n={len(rows)} 无答案={no_ans} 运行失败={errs} 子代理={subs}  {flag}')


def main():
    print('=== 历史 runs 文件的测量可信度审计 ===')
    for f in sorted(glob.glob('runs-*.jsonl')):
        if f.startswith('_'):
            continue
        try:
            audit(f)
        except Exception as e:
            print(f'  {f}: 跳过({e})')


if __name__ == '__main__':
    main()
