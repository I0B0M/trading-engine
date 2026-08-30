"""Simulated broker.

Fills target-weight orders at the day's open price, with slippage working
against the trader and a commission on notional value. Fractional shares are
allowed (as they are at Alpaca, the Phase 2 broker).
"""

from __future__ import annotations

import datetime as dt

from .events import Fill, TargetOrder
from .portfolio import Portfolio


class SimulatedBroker:
    def __init__(self, commission_bps: float = 1.0, slippage_bps: float = 5.0):
        self.commission_bps = commission_bps
        self.slippage_bps = slippage_bps

    def execute(
        self,
        orders: list[TargetOrder],
        open_prices: dict[str, float],
        date: dt.date,
        portfolio: Portfolio,
    ) -> None:
        """Fill `orders` at `date`'s open. Orders for symbols with no bar
        today (halted/not yet listed) are dropped silently."""
        if not orders:
            return
        # Mark equity at today's open to size positions.
        marks = dict(open_prices)
        for symbol in portfolio.positions:
            if symbol not in marks:
                raise ValueError(f"no open price for held symbol {symbol} on {date}")
        equity = portfolio.equity(marks)

        for order in orders:
            open_price = open_prices.get(order.symbol)
            if open_price is None:
                continue
            target_value = order.weight * equity
            current_shares = portfolio.positions.get(order.symbol, 0.0)
            delta_shares = target_value / open_price - current_shares
            if abs(delta_shares * open_price) < 1.0:  # ignore sub-$1 rebalances
                continue
            slip = self.slippage_bps / 10_000.0
            price = open_price * (1 + slip) if delta_shares > 0 else open_price * (1 - slip)
            commission = abs(delta_shares) * price * self.commission_bps / 10_000.0
            portfolio.apply_fill(
                Fill(
                    symbol=order.symbol,
                    date=date,
                    shares=delta_shares,
                    price=price,
                    commission=commission,
                )
            )
