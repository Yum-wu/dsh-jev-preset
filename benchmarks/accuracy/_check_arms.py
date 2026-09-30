# -*- coding: utf-8 -*-
"""实验有效性检查:A1 是否真禁了代码、A2 是否真跑了代码。

若 A1 偷跑代码 或 A2 没跑代码,则该实验的变量隔离失败,结论无效。
只读。
"""
import io
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, '.')

from jevbench.extract import extract_answer  # noqa: E402
from jevbench.grading import load_jsonl  # noqa: E402

CODE_HINT = re.compile(r'(pwsh|powershell|python|node\s|```(?:python|powershell|ps1|js))', re.I)


def main():
    runs = load_jsonl(sys.argv[1] if len(sys.argv) > 1 else '_runs-assert-smoke.jsonl')
    suite = {c['id']: c for c in load_jsonl('_suite-assert.jsonl')}
    for r in runs:
        t = r.get('text') or ''
        ans = extract_answer(t)
        c = suite[r['case_id']]
        want = c['expected']
        ok = ans is not None and all(str(ans.get(k)) == str(v) for k, v in want.items())
        print(f"[{r['config']}] {r['case_id']}  tok={r.get('tokens')} sub={r.get('subagents')} "
              f"{r.get('elapsed_ms', 0) // 1000}s 正确={ok}")
        print(f"    提到代码/解释器: {bool(CODE_HINT.search(t))}  含代码块: {'```' in t}  "
              f"文本 {len(t)} 字符")
        print(f"    答案: {ans}")
        print(f"    期望: {want}")
        print()


if __name__ == '__main__':
    main()
