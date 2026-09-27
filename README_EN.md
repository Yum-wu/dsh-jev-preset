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

**Key JEV Innovations**:
- **Objective Gated Routing**: Fast-Pass for routine low-risk queries without wasting tokens; compulsory 3-way isolated fission for high-risk domains.
- **True 3-Way Context-Isolated Sampling**: Uses `provider: spawn` to spin up 3 strictly isolated subagent contexts (Rigorous Deriver, Red-Team Adversary, Minimalist Executor).
- **Execution-First Arbitration & Veto Power**: Real sandbox execution overrides verbal reasoning. Consistent consensus converges instantly; unresolved divergence undergoes Jev Rerank.

---

## 📊 30 High-Risk Quantitative Benchmark Performance

Tested across 5 critical risk categories (Tick Quantization, Tiered Liquidation, Slippage Penetration, Timezone/DST Alignment, and Adjustment Factor Zero-Division):

| Metric | Result | Target Benchmark | Status |
| :--- | :--- | :--- | :--- |
| **Total Test Cases** | 30 Cases | ≥ 30 | Passed (100%) |
| **Path 1 Avg Convergence Latency** | **0.033 ms** | < 100 ms | Ultra-fast |
| **Path 2 Red-Team Attack Hit Rate** | **100.0%** (30/30) | ≥ 90.0% | Excellent |
| **Path 3 Sandbox Execution Pass@1** | **100.0%** (30/30) | ≥ 95.0% | Veto Applied |
| **JEV 3/3 Independent Consensus** | **100.0%** (30/30) | ≥ 90.0% | Full Convergence |

See [docs/benchmark-report.md](./docs/benchmark-report.md) for detailed analysis.

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
