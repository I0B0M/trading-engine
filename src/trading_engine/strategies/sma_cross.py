"""Golden-cross trend following: fully invested while the fast moving average
is above the slow one, in cash otherwise."""

from __future__ import annotations

import math

from ..engine.events import Bar
from ..engine.history import History
from ..engine.strategy import Strategy
from .indicators import sma


class SmaCross(Strategy):
    params = {"fast": 50, "slow": 200}

    def on_bar(self, bar: Bar, history: History) -> None:
        closes = history.closes(bar.symbol, self.p.slow)
        fast = sma(closes, self.p.fast)
        slow = sma(closes, self.p.slow)
        if math.isnan(fast) or math.isnan(slow):
            return
        self.target_position(bar.symbol, 1.0 if fast > slow else 0.0)
