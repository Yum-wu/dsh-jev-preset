# dsh-jev-preset

[![CI](https://github.com/Yum-wu/dsh-jev-preset/actions/workflows/ci.yml/badge.svg)](https://github.com/Yum-wu/dsh-jev-preset/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)

[中文](./README.md)

An agent preset bundle for [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) (DSH).

It does one thing: before the model commits to a numeric or risk-control answer, it runs real code once and checks the number.

---

## What it fixes

Single-session models fail on quantitative work in three ways:

1. **Wrong but fluent.** Bad numbers get wrapped in smooth reasoning that survives human review.
2. **Autoregressive self-contamination.** Asking one session to "analyze from three perspectives" anchors later tokens on earlier ones — not real multi-path.
3. **No physical ground truth.** A formula that never ran in an interpreter should not ship.

## Install

A standard DSH bundle: an npm package carrying one `cordis.patch.yml` layer, mounted into the profile's loader tree.

```
dsh plugin --profile <your-profile> add dsh-jev-preset
```

Verify the layer landed without booting:

```
dsh --profile <your-profile> --dump-config
```

You should see a `# == dsh-jev-preset` layer. Then boot — **JEV Cross-Verification** appears in the preset list.

Remove the same way: `dsh plugin --profile <your-profile> remove dsh-jev-preset`.

> This bundle declares no `dependencies` / `peerDependencies` and hardcodes no DSH version.
> The declaration row ships `inject = ["agentPresets"]`, so the loader activates it once the registry is ready,
> and sub-plugin paths resolve from the host `@deepseek-ai/dsh-agent-preset` baseUrl.
> Tested working on 0.2.0-rc.2.

## Gating: what happens when

The model routes on its own; no user action needed.

| Task | Handling |
|---|---|
| Everyday / low risk (lookup, Q&A, small single-file edits) | Fast-Pass, single shot |
| Numeric, risk, position sizing, liquidation price, indicator math | **Single pass + real code re-check**; ship only if assertions pass |
| High risk but no single numeric answer (security boundaries, concurrency, design tradeoffs) | 3-way isolated sampling |
| Any of the above, but assertion/test fails | Do not ship. Fix the assertion first; escalate to 3-way only if it can't be fixed |

3-way is the fallback, not the default. See the numbers below.

## Measured results

All figures come from reproducible experiments under `benchmarks/accuracy/`.

| Method | Effect | Cost |
|---|---|---|
| Prompt structuring | +89pp (100% on 5/5 models) | ×1 |
| **Execution assertion** | **24/30 → 30/30, McNemar p=0.0312** | ×2.0 |
| Switch to a heterogeneous model | +89pp (some models) | ×5.4 |
| 3-way isolated sampling | **Gain 0 (p=1.0)** | ×10.6 |

**The assertion pass is the only statistically significant positive result in this repo.** Stacking 3-way sampling on top of an already-asserted answer adds nothing (30/30 vs 30/30, p=1.0) at 15.3× the cost, with a higher run-failure rate (2/12 vs 0/12).

Why 3-way can't fix reading errors: on candy trap problems, all 5 wrong answers equal the "blind" value exactly — failures sit in the **information-extraction layer** (missed constraints). Voting reduces variance, not bias. Calculation problems are the opposite: errors are scattered arithmetic slips, which assertions do catch.

> Retracted: the 30-problem batch `runs-c30-c3-sb.jsonl` (3.3% / p=1.0 / blind rate 33%) had 18/30 rows affected by a measurement bug — the runner scored before subagent settlement. The 9-problem batch is unaffected and still valid. Audit: `benchmarks/accuracy/MEASUREMENT-BUG-2026-09-30.md`.

## Relation to published work

| Dimension | Source | Here |
|---|---|---|
| Sampling converts to performance only with a verifier | [Large Language Monkeys](https://arxiv.org/abs/2407.21787) (UC Berkeley/CMU) | assertions ×2.0 significant; 3-way ×10.6 gain 0 |
| Mindset effect causes missed constraints | [MisguidedAttention](https://github.com/cpldcpu/MisguidedAttention); Anthropic changed its system prompt for the same failure in 2024-10 | §3.0 constraint diagnosis, +89pp |
| 85.5% sycophantic conformity in unisolated agents | [arXiv:2605.00914](https://arxiv.org/html/2605.00914), [arXiv:2503.13657](https://arxiv.org/html/2503.13657v1) | no answer-forward anchoring; `maxDepth:1` |
| Heterogeneous models share latent entanglement; agreement ≠ independence | [arXiv:2604.07650](https://arxiv.org/abs/2604.07650) | execution result outranks 3-way consensus |

## Assertion library

When the gate decides "this can be an assertion", reuse these instead of writing throwaway scripts — reuse removes the bugs and float drift of hand-written code.

Python: `packages/assertions/python/jev_assertions/`

- `tick.py` — tick truncation, rounding direction, grid alignment, inverse contract lots
- `margin.py` — tiered maintenance margin, quick deduction, linear/inverse liquidation price
- `slippage.py` — orderbook VWAP, Almgren-Chriss impact, AMM slippage
- `calendar.py` — DST transitions, monotonic clock regression
- `split.py` — ex-rights price, forward-adjusted returns, reverse split factor

PowerShell: `packages/assertions/pwsh/JevAssertions.psm1` (PS 5.1 / 7, UTF-8 BOM)

⚠ **The PS surface and the Python surface are NOT equivalent** (fixed 2026-10-01):
the Python side has **18** assertions; the PS side has **only 3**
(`Assert-JevTickFloor` / `Assert-JevTieredMargin` / `Assert-JevSlippageBudget`) —
**the other 15 assertion kinds do not exist on the PS side**.
**Prefer the Python CLI below** whenever an assertion can express the check;
use the PS module only when the environment is PowerShell-only and the
check is one of those 3 kinds.

Call all 18 assertions from the CLI.

⚠ The path below is **relative to the plugin root** and only resolves when the
current directory is `plugins/dsh-jev-preset/`. Copy-pasting it from the repository
root (the default session cwd) yields `[Errno 2]`. Locate first:

```powershell
$JEV = @(Resolve-Path "$env:USERPROFILE\.dsh\profiles\*\node_modules\dsh-jev-preset\packages\assertions\python\jev_assertions\cli.py" -ErrorAction SilentlyContinue | Sort-Object Path)[0].Path
if (-not (Test-Path $JEV)) { $JEV = @(Get-ChildItem . -Recurse -Depth 5 -Directory -Filter jev_assertions)[0].FullName + '\cli.py' }
if (-not (Test-Path $JEV)) { throw "assertion library not found ($JEV)" }
```

```powershell
python $JEV --list

python $JEV --func tick_floor --args '{"raw_price": 67432.178, "tick_size": 0.01, "expected": "67432.17"}'
```

> When `$JEV` is empty you **must** throw first: running `python $JEV --func ...`
> degrades to `python --func ...`, which reports `unknown option --func` — easily
> misread as "the assertion actually ran".

**Exit-code contract (three values)**:

| exit | status | meaning | action |
|---|---|---|---|
| `0` | `pass` | assertion passed | release the conclusion |
| `1` | `fail` | assertion ran, **the value is wrong** | do not release; recompute or escalate to 3-way |
| `2` | `error` | **bad call, nothing ran** (missing `--func` / malformed JSON / parameter mismatch / unknown assertion / internal exception) | **fix the command first, then recompute** |
| `3` | `insufficient_data` | **input cannot decide** (e.g. not enough order-book depth) | **supply more data, then rerun** — recomputing is pointless |

> exit 2 matters most: no numeric conclusion exists at that point. Treating it as
> "the assertion rejected my value" fabricates a verification that never happened.
> exit 3 is the mirror image: the value is not wrong, the input is inadequate —
> recomputing wastes effort. The contract is locked cell-by-cell by
> `tests/test_cli_exit_codes.py`
> (including the invariant `status == "error" ⟺ exit == 2`).

> The PowerShell `Assert-Jev*` module has **only two values** (failure = 1; missing
> parameter / unknown function also = 1, the PowerShell convention) — no exit 2/3.
> As noted above, it also exposes **only 3 functions**, far fewer than the 18 on the Python side.
> On that surface, read the exception text to tell "wrong value" from "bad call";
> the exit code alone cannot.

## Defenses that exist (and ones that don't)

Present and verified:

- **Recursion block** `maxDepth: 1` — subagents cannot spawn further; measured 0 grandchild sessions, engine throws `SubagentDepthError`.
- **Isolated service realms** — compaction / delegation live in private realms; checked statically by `validate.mjs`.

Absent (do not assume otherwise):

- **Standalone circuit breaker** — does not exist. Failure recovery comes from the host `@deepseek-ai/dsh-llm-retry`. The one in `tests/test-circuit-breaker.mjs` is a reference implementation only.
- **Role mutex** — does not exist. 3-way role uniqueness rests on persona discipline, not code, so the model can still dispatch two Path 3s.

## Development

```bash
npm test                # node unit tests + Python assertions + suite self-check
npm run validate        # cordis.patch.yml and loader composition
npm run test:benchmark  # 30 boundary cases (see caveat)
```

The four statistics in `benchmarks/run_stress_matrix.py` currently return `None` — those 30 cases are a parameter inventory, and 3-way sampling has not actually been run on them. An older version printed four rows of `100.0%`; those were tautologies from a hardcoded `hit = True`, not measurements, and have been removed. Do not parse numbers from historical versions; see [`docs/benchmark-report.md`](./docs/benchmark-report.md).

## License

[MIT](./LICENSE)
