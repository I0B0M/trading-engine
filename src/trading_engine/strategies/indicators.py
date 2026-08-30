"""Small indicator helpers over numpy arrays of closes (oldest first)."""

from __future__ import annotations

import numpy as np


def sma(closes: np.ndarray, period: int) -> float:
    """Simple moving average of the last `period` values. NaN if too short."""
    if len(closes) < period:
        return float("nan")
    return float(closes[-period:].mean())


def rsi(closes: np.ndarray, period: int) -> float:
    """Wilder's RSI over the last `period` changes. NaN if too short."""
    if len(closes) < period + 1:
        return float("nan")
    deltas = np.diff(closes[-(period + 1):])
    gains = deltas.clip(min=0).mean()
    losses = (-deltas).clip(min=0).mean()
    if losses == 0:
        return 100.0
    rs = gains / losses
    return float(100.0 - 100.0 / (1.0 + rs))


def total_return(closes: np.ndarray, period: int) -> float:
    """Return over the last `period` bars. NaN if too short."""
    if len(closes) < period + 1:
        return float("nan")
    return float(closes[-1] / closes[-(period + 1)] - 1.0)
