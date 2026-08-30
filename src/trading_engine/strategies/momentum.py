"""Sector momentum rotation: on the first trading day of each month, hold the
`top_n` symbols with the strongest trailing `lookback`-day return, equal
weight. Symbols without enough history yet are skipped."""

from __future__ import annotations

import datetime as dt
import math

from ..engine.events import Bar
from ..engine.history import History
from ..engine.strategy import Strategy
from .indicators import total_return


class SectorMomentum(Strategy):
    params = {"lookback": 126, "top_n": 3}

    def __init__(self, **overrides):
        super().__init__(**overrides)
        self._last_rebalance_month: tuple[int, int] | None = None
        self._held: set[str] = set()

    def on_bars(self, date: dt.date, bars: dict[str, Bar], history: History) -> None:
        month = (date.year, date.month)
        if month == self._last_rebalance_month:
            return
        self._last_rebalance_month = month

        scores = {}
        for symbol in bars:
            r = total_return(history.closes(symbol, self.p.lookback + 1), self.p.lookback)
            if not math.isnan(r):
                scores[symbol] = r
        if len(scores) < self.p.top_n:
            return

        winners = set(sorted(scores, key=scores.get, reverse=True)[: self.p.top_n])
        for symbol in self._held - winners:
            self.target_position(symbol, 0.0)
        for symbol in winners:
            self.target_position(symbol, 1.0 / self.p.top_n)
        self._held = winners
