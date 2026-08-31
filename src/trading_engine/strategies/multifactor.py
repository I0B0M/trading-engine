"""Cross-sectional multi-factor long-only portfolio.

The design answer to everything wrong with a 50/200 crossover: instead of one
timing bet on one index generating ~54 observations per century, this places a
ranked bet across every name in the universe at every rebalance, which is how
statistical power actually accumulates.

Construction:
  - rank the universe on a composite of price-based factor signals
  - hold the top `top_n`, with a buffer band so incumbents are not churned out
    on small rank changes (MSCI keeps incumbents to 1.5x the target count;
    Novy-Marx & Velikov call a buy/hold spread "the single most effective
    simple cost mitigation strategy")
  - rebalance quarterly, not monthly: the underlying signals are slow, and
    net-of-cost spreads survive mainly below ~50% monthly one-sided turnover
  - size positions equally, or by inverse volatility

Deliberately absent: stop losses. Tested on a century of US data, a -20%
hard stop cut annual returns by more than half AND still suffered a -29%
drawdown, because it exits after the damage and re-enters after the recovery.
Drawdown control belongs at the portfolio level and must be continuous.
"""

from __future__ import annotations

import datetime as dt

import numpy as np

from ..engine.events import Bar
from ..engine.history import History
from ..engine.strategy import Strategy
from .factors import composite_scores, weekly_volatility

REBALANCE_MONTHS = {1, 4, 7, 10}


class MultiFactor(Strategy):
    params = {
        "top_n": 5,
        "band": 1.5,  # incumbents kept while ranked within band * top_n
        "use_low_vol": 1,  # 1 = include the low-volatility sleeve
        "weighting": "equal",  # "equal" or "inverse_vol"
        "min_history": 300,  # trading days required before a symbol is eligible
    }

    def __init__(self, **overrides):
        super().__init__(**overrides)
        if self.p.weighting not in ("equal", "inverse_vol"):
            raise ValueError("weighting must be 'equal' or 'inverse_vol'")
        self._last_rebalance: tuple[int, int] | None = None
        self._held: set[str] = set()

    def on_bars(self, date: dt.date, bars: dict[str, Bar], history: History) -> None:
        if date.month not in REBALANCE_MONTHS:
            return
        period = (date.year, date.month)
        if period == self._last_rebalance:
            return

        closes = {
            symbol: history.closes(symbol)
            for symbol in bars
            if history.bars_seen(symbol) >= self.p.min_history
        }
        scores = composite_scores(closes, use_low_vol=bool(self.p.use_low_vol))
        if len(scores) < self.p.top_n:
            return  # not enough eligible names yet; leave the book alone

        self._last_rebalance = period
        ranked = sorted(scores, key=lambda s: scores[s], reverse=True)
        target_n = min(self.p.top_n, len(ranked))
        entrants = ranked[:target_n]
        band_cutoff = min(int(self.p.band * target_n), len(ranked))
        eligible_to_hold = set(ranked[:band_cutoff])

        # Keep incumbents still inside the band, then fill with fresh entrants.
        selected = [s for s in ranked if s in self._held and s in eligible_to_hold]
        for symbol in entrants:
            if len(selected) >= target_n:
                break
            if symbol not in selected:
                selected.append(symbol)
        selected = selected[:target_n]

        weights = self._weights(selected, closes)
        for symbol in self._held - set(selected):
            self.target_position(symbol, 0.0)
        for symbol, weight in weights.items():
            self.target_position(symbol, weight)
        self._held = set(selected)

    def _weights(
        self, selected: list[str], closes: dict[str, np.ndarray]
    ) -> dict[str, float]:
        if not selected:
            return {}
        if self.p.weighting == "equal":
            w = 1.0 / len(selected)
            return {s: w for s in selected}

        # Inverse volatility: equal standalone risk per position. Uses only the
        # diagonal of the covariance matrix, the one part estimable from short
        # samples -- full covariance optimization is where estimation error wins.
        inv = {}
        for symbol in selected:
            vol = weekly_volatility(closes[symbol])
            if np.isfinite(vol) and vol > 0:
                inv[symbol] = 1.0 / vol
        if not inv:
            w = 1.0 / len(selected)
            return {s: w for s in selected}
        total = sum(inv.values())
        return {s: v / total for s, v in inv.items()}
