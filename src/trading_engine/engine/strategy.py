"""Strategy base class.

A strategy receives one day's closed bars at a time and stages target
portfolio weights. It never places orders directly and never sees the future:
targets staged after day T's close are filled at day T+1's open.
"""

from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

from .events import Bar
from .history import History


class Strategy:
    params: dict = {}

    def __init__(self, **overrides):
        unknown = set(overrides) - set(self.params)
        if unknown:
            raise TypeError(f"{type(self).__name__} has no params {sorted(unknown)}")
        self.p = SimpleNamespace(**{**self.params, **overrides})
        self._staged: dict[str, float] = {}

    # --- API for subclasses -------------------------------------------------

    def target_position(self, symbol: str, weight: float) -> None:
        """Request to hold `weight` fraction of equity in `symbol` (0 = exit)."""
        self._staged[symbol] = weight

    def on_bars(self, date: dt.date, bars: dict[str, Bar], history: History) -> None:
        """Called once per trading day after the close, with that day's bars.

        Default: dispatch to on_bar per symbol. Multi-symbol strategies
        override this instead.
        """
        for bar in bars.values():
            self.on_bar(bar, history)

    def on_bar(self, bar: Bar, history: History) -> None:  # pragma: no cover
        pass

    # --- engine-side --------------------------------------------------------

    def _collect_targets(self) -> dict[str, float]:
        staged, self._staged = self._staged, {}
        return staged
