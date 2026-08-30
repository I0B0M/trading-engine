"""Core value types passed around the engine."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass


@dataclass(frozen=True)
class Bar:
    """One closed daily bar. By the time a strategy sees this, the day is over."""

    symbol: str
    date: dt.date
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class TargetOrder:
    """A request to hold `weight` fraction of portfolio equity in `symbol`.

    Created after the close of `signal_date`; the broker fills it at the
    next trading day's open. Weight 0.0 means exit the position.
    """

    symbol: str
    weight: float
    signal_date: dt.date


@dataclass(frozen=True)
class Fill:
    """An executed trade."""

    symbol: str
    date: dt.date
    shares: float  # positive = bought, negative = sold
    price: float  # actual fill price including slippage
    commission: float
