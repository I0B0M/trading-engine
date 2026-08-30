"""Cash + positions bookkeeping."""

from __future__ import annotations

from .events import Fill


class Portfolio:
    def __init__(self, initial_cash: float):
        self.initial_cash = initial_cash
        self.cash = initial_cash
        self.positions: dict[str, float] = {}  # symbol -> shares
        self.fills: list[Fill] = []

    def apply_fill(self, fill: Fill) -> None:
        self.cash -= fill.shares * fill.price + fill.commission
        new_shares = self.positions.get(fill.symbol, 0.0) + fill.shares
        if abs(new_shares) < 1e-9:
            self.positions.pop(fill.symbol, None)
        else:
            self.positions[fill.symbol] = new_shares
        self.fills.append(fill)

    def equity(self, prices: dict[str, float]) -> float:
        """Cash plus positions marked at `prices` (missing symbols mark at 0 —
        callers must pass prices for every held symbol)."""
        value = self.cash
        for symbol, shares in self.positions.items():
            value += shares * prices[symbol]
        return value
