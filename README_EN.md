# dsh-jev-preset

[![CI Status](https://github.com/Yum-wu/dsh-jev-preset/actions/workflows/ci.yml/badge.svg)](https://github.com/Yum-wu/dsh-jev-preset/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![DSH Compatibility](https://img.shields.io/badge/DSH-0.1.7-green.svg)](https://github.com/deepseek-ai)

[中文文档 (Chinese)](./README.md)

**JEV (Judgment-Execution-Verification) Adaptive Cross-Verification Preset** for DeepSeek Harness (DSH) — An industrial-grade standard bundle for quantitative finance and mission-critical agent workflows.

---

## 🌟 Philosophy & Core Pain Points Solved

In quantitative trading, risk management calculations, and critical system refactoring, single-model reasoning exhibits three major hazards:
1. **Overconfident Hallucination**: Single-context models can produce grammatically flawless justifications even when numerical derivations are completely wrong.
2. **Autoregressive Co-contamination**: Simulating "multiple perspectives" within the same context window causes downstream tokens to be conditioned on previous errors.
3. **Absence of Real Execution Truth**: Theoretical text reasoning cannot substitute for sandbox runtime execution. Formulas and logic must pass real execution before approval.

**Key JEV Innovations** (priority re-ranked by measured data, 2026-09-30):
- **① Assertion-First**: For computational/numerical tasks, answer in a **single path and actually
  re-run the computation in code**. Measured on 30 computational cases: forced re-computation raised
  accuracy from **24/30 → 30/30** (McNemar **p=0.0312**, zero reversals) at only **×2.0** cost.
  This is the project's **only statistically significant** positive result.
- **② Objective Gated Routing**: Fast-Pass for routine low-risk queries; 3-way fission **only** for
  high-risk tasks that **cannot be expressed as an assertion** (security boundaries, concurrency/state
  machines, non-unique-value trade-offs).
- **③ True 3-Way Context-Isolated Sampling**: Uses `provider: spawn` to spin up 3 strictly isolated
  subagent contexts (Rigorous Deriver, Red-Team Adversary, Minimalist Executor).
  ⚠ **Fallback path, not the default**: measured, adding 3-way sampling on top of a passing assertion
  yields **zero gain** (10/10 vs 10/10, p=1.0) while costing **×10.6** more, with a higher run-failure
  rate (2/12 vs 0/12).

### Method priority (measured, 2026-09-30)

| Priority | Method | Effect | Cost | Applies to |
|---|---|---|---|---|
| 1 | **Prompt structuring** | +89pp (5/5 models) | **×1** | Reading/attention blind spots |
| 2 | **Execution assertion** | **24/30 → 30/30 (p=0.0312)** | **×2.0** | Computational (assertion-expressible) |
| 3 | Heterogeneous model swap | +89pp (some models) | ×5.4 | Reading blind spots when structuring is insufficient |
| 4 | 3-way isolated sampling | **zero gain** (p=1.0) | ×10.6 | Only when neither assertion nor model swap is possible |

> **Mechanism**: on candy reading-trap cases, all 5 wrong 3-way answers were of the
> "missed a key condition" type (bias — voting cannot fix it); on numeric cases, errors were
> scattered arithmetic slips (variance — an assertion does fix them). Two sides of the same
> statistical principle: `voting reduces variance, not bias`. Consistent with
> [Large Language Monkeys](https://arxiv.org/abs/2407.21787) — extra sampling only converts to
> performance where an **automatic verifier** exists.
>
> Evidence: `benchmarks/accuracy/EXP-F-ASSERTION-EFFECT.md`,
> `EXP-G-THREE-PATH-VS-ASSERTION.md`, `MEASUREMENT-BUG-2026-09-30.md`.

---

## 📊 30 High-Risk Quantitative Benchmark Performance

Tested across 5 critical risk categories (Tick Quantization, Tiered Liquidation, Slippage Penetration, Timezone/DST Alignment, and Adjustment Factor Zero-Division):

> ⚠️ Honesty notice (2026-09-28): an earlier version of this table claimed four
> rows of `100.0%`. Those were identities produced by local if-elif hard-coded
> branches (`hit = True` tautology, `assert isinstance(expected, dict)` tautology),
> **not** measured JEV three-way isolated sampling. The figures have been withdrawn;
> see [`docs/benchmark-report.md`](./docs/benchmark-report.md) for the full disclosure.

30 cases (5 risk domains) currently exist only as a **case parameter inventory**; three-way
sampling has not yet been genuinely executed. The four sampling metrics currently
return `None` (unmeasured) in `benchmarks/benchmark-results.json`. Genuinely verified
evidence consists of: static contract checks (`validate.mjs`, `tests/test-*.mjs`, all green)
and one fully archived real 4-subagent isolated run (`notes/jev-three-path-run-2026-09-28.md`).

> 📖 Field contract (`benchmarks/benchmark-results.json`, since 2026-09-28):
> `path1_avg_convergence_ms` / `path2_attack_hit_rate` / `path3_pass_at_k_rate` /
> `consensus_rate_3_of_3` are always `null`, each with a `*_note` explaining why;
> the only machine-consumable fields are `case_inventory_count` (=30) and the
> `results[]` case inventory. Historical versions emitted `100.0%` — identities,
> not measurements; downstream consumers **must not** parse old versions as numbers.

---

## 🧰 Built-in Quantitative & Risk Assertion Suite

- `packages/assertions/python/jev_assertions/`:
  - `tick.py`: Tick size truncation, floor/ceiling quantize, lot step budget, inverse contract integer rounding.
  - `margin.py`: Tiered maintenance margin (MMR), quick deduction, linear/inverse liquidation price formulas.
  - `slippage.py`: Orderbook VWAP, Almgren-Chriss square-root impact model, AMM constant product impact.
  - `calendar.py`: DST timezone shifts (EST/EDT), monotonic clock backward-jump detection.
  - `split.py`: Ex-right price, forward adjustment log-return safety, reverse split volume inverse conservation.
- `packages/assertions/pwsh/JevAssertions.psm1`: Cross-compatible PowerShell module with UTF-8 BOM.

---

## 🚀 Quick Start

### Installation

Declare the preset within your Cordis profile Loader tree:

```yaml
- insert:
    - id: preset-jev
      name: '@deepseek-ai/dsh-agent-preset'
      config:
        id: jev
        name: JEV Cross-Verification
        order: 5
        plugins: [ ... ]
```

### Running Tests

```bash
# Run all unit and assertion tests
npm test

# Run 30-case stress benchmark matrix
npm run test:benchmark

# Validate Cordis patch schema
npm run validate
```

---

## 📜 License

Distributed under the [MIT License](./LICENSE).
