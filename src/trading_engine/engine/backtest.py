"""The replay loop.

For each trading day, in order:
  1. Fill orders staged after yesterday's close, at today's OPEN.
  2. Mark the portfolio at today's CLOSE and record the equity curve.
  3. Show the strategy today's closed bars; it may stage orders for tomorrow.

This ordering is the engine's honesty guarantee: a signal computed on day T
can never transact at day T's prices.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

import pandas as pd

from .broker import SimulatedBroker
from .events import Bar, Fill, TargetOrder
from .history import History
from .portfolio import Portfolio
from .strategy import Strategy


@dataclass
class BacktestResult:
    equity_curve: pd.Series  # equity marked at each day's close
    fills: list[Fill] = field(default_factory=list)
    final_positions: dict[str, float] = field(default_factory=dict)

    @property
    def initial_equity(self) -> float:
        return float(self.equity_curve.iloc[0])

    @property
    def final_equity(self) -> float:
        return float(self.equity_curve.iloc[-1])


def run_backtest(
    strategy: Strategy,
    frames: dict[str, pd.DataFrame],
    start: dt.date | None = None,
    end: dt.date | None = None,
    initial_cash: float = 100_000.0,
    broker: SimulatedBroker | None = None,
) -> BacktestResult:
    """frames: per-symbol OHLCV DataFrames indexed by datetime.date."""
    broker = broker or SimulatedBroker()
    history = History(frames)
    portfolio = Portfolio(initial_cash)

    calendar = sorted({d for df in frames.values() for d in df.index})
    if start is not None:
        calendar = [d for d in calendar if d >= start]
    if end is not None:
        calendar = [d for d in calendar if d <= end]
    if not calendar:
        raise ValueError("no trading days in the requested range")

    lookup = {
        symbol: {d: i for i, d in enumerate(df.index)} for symbol, df in frames.items()
    }

    pending: list[TargetOrder] = []
    equity_dates: list[dt.date] = []
    equity_values: list[float] = []
    last_close: dict[str, float] = {}

    for date in calendar:
        todays_bars: dict[str, Bar] = {}
        open_prices: dict[str, float] = {}
        for symbol, df in frames.items():
            i = lookup[symbol].get(date)
            if i is None:
                continue
            row = df.iloc[i]
            todays_bars[symbol] = Bar(
                symbol=symbol,
                date=date,
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"]),
            )
            open_prices[symbol] = float(row["open"])

        # 1. fill yesterday's staged orders at today's open
        broker.execute(pending, open_prices, date, portfolio)
        pending = []

        # 2. mark at today's close (last known close for symbols halted today)
        for symbol, bar in todays_bars.items():
            last_close[symbol] = bar.close
        equity_dates.append(date)
        equity_values.append(portfolio.equity(last_close))

        # 3. strategy sees today's closed bars, stages targets for tomorrow
        history._set_cursor(date)
        strategy.on_bars(date, todays_bars, history)
        pending = [
            TargetOrder(symbol=s, weight=w, signal_date=date)
            for s, w in strategy._collect_targets().items()
        ]

    return BacktestResult(
        equity_curve=pd.Series(equity_values, index=pd.Index(equity_dates, name="date")),
        fills=portfolio.fills,
        final_positions=dict(portfolio.positions),
    )
