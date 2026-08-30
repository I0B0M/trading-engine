"""Live (paper) trading runner.

The core trick: a strategy's desired portfolio today is reconstructed by
replaying recent history through the exact same class and engine used for
backtesting — so live behavior is the backtest's behavior by construction,
not by reimplementation. We then diff those desired weights against the real
positions in the paper account and emit only the difference as orders.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import pandas as pd

from ..engine.backtest import run_backtest
from ..engine.broker import SimulatedBroker
from ..engine.strategy import Strategy


class CumulativeTargets(Strategy):
    """Wraps a strategy and remembers the last target weight it staged for
    each symbol across the whole replay. Strategies only stage weights on
    change days (a monthly rebalance, an entry/exit), so the accumulated
    dict — not just the final day's stages — is the desired portfolio."""

    def __init__(self, inner: Strategy):
        super().__init__()
        self._inner = inner
        self.current: dict[str, float] = {}

    def on_bars(self, date, bars, history) -> None:
        self._inner.on_bars(date, bars, history)

    def _collect_targets(self) -> dict[str, float]:
        staged = self._inner._collect_targets()
        self.current.update(staged)
        return staged


def compute_desired_weights(
    strategy: Strategy, frames: dict[str, pd.DataFrame]
) -> dict[str, float]:
    """Replay `frames` through the engine; return the strategy's desired
    portfolio weights as of the last bar."""
    recorder = CumulativeTargets(strategy)
    run_backtest(recorder, frames, broker=SimulatedBroker(0.0, 0.0))
    return dict(recorder.current)


@dataclass(frozen=True)
class PlannedOrder:
    symbol: str
    action: str  # "buy" | "sell" | "close"
    notional: float  # dollars; 0.0 for "close"

    def describe(self) -> str:
        if self.action == "close":
            return f"CLOSE {self.symbol} (exit entire position)"
        return f"{self.action.upper():5} {self.symbol:6} ${self.notional:,.2f}"


def reconcile(
    desired_weights: dict[str, float],
    equity: float,
    position_values: dict[str, float],  # symbol -> current market value ($)
    min_order_fraction: float = 0.005,
) -> list[PlannedOrder]:
    """Diff desired weights against actual positions. Only symbols the
    strategy has an opinion about are touched. Rebalances smaller than
    `min_order_fraction` of equity are skipped to avoid daily dust orders."""
    orders: list[PlannedOrder] = []
    for symbol, weight in sorted(desired_weights.items()):
        held = position_values.get(symbol, 0.0)
        if weight <= 0.0:
            if held > 0.0:
                orders.append(PlannedOrder(symbol, "close", 0.0))
            continue
        delta = weight * equity - held
        if abs(delta) < min_order_fraction * equity:
            continue
        action = "buy" if delta > 0 else "sell"
        orders.append(PlannedOrder(symbol, action, round(abs(delta), 2)))
    return orders


def live_data_window(
    symbols: list[str], lookback_days: int = 400, end: dt.date | None = None
) -> dict[str, pd.DataFrame]:
    """Recent daily bars for replay: enough history for the slowest indicator
    (200-day SMA) plus buffer."""
    from ..data.loader import load_bars

    end = end or dt.date.today()
    start = end - dt.timedelta(days=int(lookback_days * 1.6))
    return load_bars(symbols, start, end)
