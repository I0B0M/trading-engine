"""Connors-style RSI(2) mean reversion: in an uptrend (close above the 200-day
average), buy sharp short-term dips (RSI(2) below the entry threshold) and
exit when price recovers above its 5-day average."""

from __future__ import annotations

import math

from ..engine.events import Bar
from ..engine.history import History
from ..engine.strategy import Strategy
from .indicators import rsi, sma


class RsiReversion(Strategy):
    params = {"rsi_period": 2, "entry_below": 10.0, "exit_sma": 5, "trend_sma": 200}

    def __init__(self, **overrides):
        super().__init__(**overrides)
        self._in_position: set[str] = set()

    def on_bar(self, bar: Bar, history: History) -> None:
        closes = history.closes(bar.symbol, self.p.trend_sma)
        trend = sma(closes, self.p.trend_sma)
        if math.isnan(trend):
            return
        if bar.symbol not in self._in_position:
            dip = rsi(closes, self.p.rsi_period)
            if bar.close > trend and dip < self.p.entry_below:
                self._in_position.add(bar.symbol)
                self.target_position(bar.symbol, 1.0)
        else:
            if bar.close > sma(closes, self.p.exit_sma) or bar.close < trend:
                self._in_position.discard(bar.symbol)
                self.target_position(bar.symbol, 0.0)
