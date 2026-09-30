# -*- coding: utf-8 -*-
"""深究 C3 两次运行失败的根因。

已知:
  - vwap-20260928-02: sub=3, tok=867770, text 空, turn/end error
  - tiered_mm-20260928-00: sub=0, tok=0, text 空, turn/end error

从磁盘会话日志(.jsonl.zstd)读原始事件,找真正的失败点。
只读。
"""
import io
import json
import os
import sys
from collections import Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, '.')

from jevbench.grading import load_jsonl  # noqa: E402

SESS = os.path.join(os.path.expanduser('~'), '.dsh', 'sessions', '--C-Users-Yum--')


def main():
    runs = load_jsonl('_runs-assert-c3.jsonl')
    fails = [r for r in runs if r.get('error')]
    print(f'失败 {len(fails)} 条:')
    for r in fails:
        print(f"  {r['case_id']}  err={r.get('error')}  end={r.get('end_reason')}  "
              f"sub={r.get('subagents')} peak={r.get('peak_subagents')} tok={r.get('tokens')} "
              f"{r.get('elapsed_ms', 0) // 1000}s  sid={r.get('session_id')}")

    print()
    print('=== 会话目录是否还在 ===')
    for r in fails:
        sid = r.get('session_id') or ''
        name = sid if sid.startswith('session-') else f'session-{sid}'
        p = os.path.join(SESS, name)
        print(f'  {name}: 存在={os.path.isdir(p)}')
        if os.path.isdir(p):
            for f in os.listdir(p):
                print(f'      {f}  {os.path.getsize(os.path.join(p, f)):,} B')

    print()
    print('=== 全部 C3 运行的错误分布(含成功的)===')
    c = Counter()
    for r in runs:
        c['error' if r.get('error') else 'ok'] += 1
    print(' ', dict(c))
    print()
    print('=== 子代理峰值分布 ===')
    print(' ', dict(Counter(r.get('peak_subagents') for r in runs)))


if __name__ == '__main__':
    main()
