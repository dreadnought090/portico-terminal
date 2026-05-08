"""Distilled compact checklists from skill library.

Each constant is ~120-180 tokens — suitable for inline injection into LLM
prompts without bloating context. Source skill markdowns in same folder.

Usage:
    from backend.skills._checklists import VALUATION_CHECKLIST
    prompt = base_prompt + "\\n\\n" + VALUATION_CHECKLIST
"""
from __future__ import annotations


VALUATION_CHECKLIST = """## Valuation Reference Frame

**Absolute (DCF/DDM)**: forecast 5y FCFF; WACC = E/(D+E)·Ke + D/(D+E)·Kd·(1-T);
terminal = FCF·(1+g)/(WACC-g), g ≤ GDP. Sensitivity ±1% WACC, ±2% g.

**Relative**: PE-Band ±1σ vs 3y historical median + industry; PB-ROE for banks;
EV/EBITDA + reserves for commodity; PEG for tech.

**IDX-specific**: Banking → P/B-ROE preferred; Resources → EV/EBITDA + 1P/2P
reserves; Tech/Internet → PEG + DCF reverse.

**Trap detection**: cyclical low-PE ≠ cheap; deteriorating ROIC; unrealistic
terminal g; thinly-covered names (low analyst N).
"""


ASSET_ALLOCATION_CHECKLIST = """## Asset Allocation Reference Frame

**MPT (Markowitz)**: minimize w'Σw given target return; ALWAYS add bounds
(5-25% per asset, sector cap) — raw MPT produces extreme weights from input
sensitivity.

**Black-Litterman**: market equilibrium + investor views; τ=0.025-0.05; Ω per
view confidence (smaller = more confident).

**Risk parity / 1/N risk contribution**: when no clear edge across assets;
equity-tilted (60/30/10 stocks/bonds/commodities) for growth bias.

**All-Weather**: balance growth-up (equity+commodity), growth-down
(govt bond+TIPS), inflation-up (commodity+EM debt), inflation-down
(equity+govt).

**Rebalance rules**: (a) calendar quarterly OR drift-threshold ±5%;
(b) tax-aware (avoid forced sell distressed); (c) liquidity floor (min
Rp 1B daily volume IDX).

**IDX-specific limits**: max single-name 20%, sector cap 30% (esp banking
risk), reksadana NAV check daily.
"""
