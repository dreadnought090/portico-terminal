"""Portfolio risk metrics — pure numpy/pandas, no extra dep.

Computes industry-standard metrics from PortfolioSnapshot history:
- Returns: daily, annualized, total
- Volatility: annualized stdev
- Sharpe ratio (assuming Rf = IDR 10y bond ~6.5%)
- Max drawdown + duration
- Historical VaR / CVaR (5% one-tailed)

Output: dict ready to inject as ground-truth numbers into Portfolio Analyzer
LLM context (Opus). Lets the LLM cite real numbers instead of estimating.
"""
from __future__ import annotations

import math
from typing import Any

# Indonesian risk-free rate proxy: 10-year IDR government bond yield (~6.5% in 2026).
# Conservative — could be tuned to actual SBN-10y if we ever fetch it.
RISK_FREE_RATE_ANNUAL = 0.065
TRADING_DAYS_PER_YEAR = 252


def compute_risk_metrics(history: list[dict]) -> dict[str, Any]:
    """Compute risk metrics from chronological snapshot history.

    Each item: {date, total_market_value, total_pnl, total_pnl_pct}.
    Needs ≥ 2 points to compute returns.
    """
    if not history or len(history) < 2:
        return {
            "n_snapshots": len(history) if history else 0,
            "available": False,
            "reason": "Butuh minimum 2 snapshot untuk hitung returns",
        }

    mv = [h["total_market_value"] for h in history if h.get("total_market_value")]
    if len(mv) < 2:
        return {"n_snapshots": len(mv), "available": False, "reason": "Data market value kosong"}

    # Daily simple returns from MV series
    returns = []
    for i in range(1, len(mv)):
        if mv[i - 1] > 0:
            returns.append((mv[i] - mv[i - 1]) / mv[i - 1])

    if not returns:
        return {"n_snapshots": len(mv), "available": False, "reason": "Returns kosong (zero MV?)"}

    n = len(returns)
    mean_r = sum(returns) / n
    var_r = sum((r - mean_r) ** 2 for r in returns) / (n - 1) if n > 1 else 0
    stdev_r = math.sqrt(var_r) if var_r > 0 else 0

    # Annualize
    ann_return = (1 + mean_r) ** TRADING_DAYS_PER_YEAR - 1
    ann_vol = stdev_r * math.sqrt(TRADING_DAYS_PER_YEAR)
    sharpe = (ann_return - RISK_FREE_RATE_ANNUAL) / ann_vol if ann_vol > 0 else 0

    # Max drawdown — peak-to-trough on cumulative MV
    peak = mv[0]
    max_dd = 0.0
    dd_start_idx = 0
    dd_trough_idx = 0
    current_peak_idx = 0
    for i, v in enumerate(mv):
        if v > peak:
            peak = v
            current_peak_idx = i
        dd = (peak - v) / peak if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd
            dd_start_idx = current_peak_idx
            dd_trough_idx = i

    dd_duration_days = dd_trough_idx - dd_start_idx if dd_trough_idx > dd_start_idx else 0

    # Historical VaR / CVaR — 5% one-tailed (worst 5% of daily returns)
    sorted_r = sorted(returns)
    var_idx = max(int(n * 0.05) - 1, 0)
    var_5 = sorted_r[var_idx] if sorted_r else 0
    cvar_5 = sum(sorted_r[:var_idx + 1]) / (var_idx + 1) if var_idx >= 0 else 0

    # Win rate
    wins = sum(1 for r in returns if r > 0)
    win_rate = wins / n if n > 0 else 0

    # Best / worst day
    best_day = max(returns) if returns else 0
    worst_day = min(returns) if returns else 0

    return {
        "available": True,
        "n_snapshots": len(mv),
        "n_returns": n,
        "period_days": dd_duration_days,
        # Returns
        "daily_return_mean_pct": round(mean_r * 100, 3),
        "annualized_return_pct": round(ann_return * 100, 2),
        "total_return_pct": round((mv[-1] / mv[0] - 1) * 100, 2) if mv[0] > 0 else 0,
        # Risk
        "daily_volatility_pct": round(stdev_r * 100, 3),
        "annualized_volatility_pct": round(ann_vol * 100, 2),
        "sharpe_ratio": round(sharpe, 2),
        "risk_free_rate_assumed_pct": RISK_FREE_RATE_ANNUAL * 100,
        # Drawdown
        "max_drawdown_pct": round(max_dd * 100, 2),
        "max_drawdown_duration_days": dd_duration_days,
        # Tail risk
        "var_5pct_daily": round(var_5 * 100, 3),
        "cvar_5pct_daily": round(cvar_5 * 100, 3),
        # Behavior
        "win_rate_pct": round(win_rate * 100, 1),
        "best_day_pct": round(best_day * 100, 2),
        "worst_day_pct": round(worst_day * 100, 2),
    }


def fmt_metrics_for_llm(metrics: dict) -> str:
    """Format metrics dict as compact markdown for LLM injection."""
    if not metrics.get("available"):
        return f"\nMETRIK RISK PORTOFOLIO: tidak tersedia ({metrics.get('reason', 'unknown')})\n"

    return f"""
## METRIK RISK PORTOFOLIO (computed from {metrics['n_snapshots']} snapshots, {metrics['n_returns']} daily returns)

**Returns**:
- Daily mean: {metrics['daily_return_mean_pct']:+.3f}%
- Annualized: {metrics['annualized_return_pct']:+.2f}%
- Total period: {metrics['total_return_pct']:+.2f}%

**Volatility & Sharpe**:
- Daily vol: {metrics['daily_volatility_pct']:.3f}%
- Annualized vol: {metrics['annualized_volatility_pct']:.2f}%
- Sharpe ratio: {metrics['sharpe_ratio']} (Rf assumed {metrics['risk_free_rate_assumed_pct']}% — IDR 10y bond)

**Drawdown**:
- Max drawdown: -{metrics['max_drawdown_pct']:.2f}% (peak-to-trough)
- DD duration: {metrics['max_drawdown_duration_days']} days

**Tail risk (one-tailed 5%)**:
- Historical VaR(5%): {metrics['var_5pct_daily']:+.3f}% daily
- Historical CVaR(5%): {metrics['cvar_5pct_daily']:+.3f}% daily (expected shortfall)

**Behavior**:
- Win rate: {metrics['win_rate_pct']}%
- Best day: {metrics['best_day_pct']:+.2f}% / Worst day: {metrics['worst_day_pct']:+.2f}%
"""
