"""Buy on the first bar, never sell. The benchmark every strategy must beat,
and the engine's sanity check: its result must track the index itself."""

from __future__ import annotations

from ..engine.events import Bar
from ..engine.history import History
from ..engine.strategy import Strategy


class BuyAndHold(Strategy):
    def __init__(self, **overrides):
        super().__init__(**overrides)
        self._entered: set[str] = set()

    def on_bar(self, bar: Bar, history: History) -> None:
        if bar.symbol not in self._entered:
            self._entered.add(bar.symbol)
            self.target_position(bar.symbol, 1.0 / self._n_symbols)

    def on_bars(self, date, bars, history) -> None:
        self._n_symbols = max(len(bars), getattr(self, "_n_symbols", 1))
        super().on_bars(date, bars, history)
