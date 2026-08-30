"""Read-only market history exposed to strategies.

The engine advances an internal cursor one trading day at a time. Strategies
can only ever read bars at or before the cursor — future data is not reachable
through this interface, which is what makes lookahead bias structurally
impossible rather than something we test for.
"""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd


class History:
    def __init__(self, frames: dict[str, pd.DataFrame]):
        """frames: per-symbol OHLCV DataFrames indexed by datetime.date."""
        self._dates: dict[str, np.ndarray] = {}
        self._fields: dict[str, dict[str, np.ndarray]] = {}
        for symbol, df in frames.items():
            self._dates[symbol] = np.array(df.index, dtype="datetime64[D]")
            self._fields[symbol] = {
                col: df[col].to_numpy(dtype=np.float64)
                for col in ("open", "high", "low", "close", "volume")
            }
        self._cursor: np.datetime64 | None = None

    def _set_cursor(self, date: dt.date) -> None:
        """Engine-only: advance the visible window up to and including `date`."""
        self._cursor = np.datetime64(date, "D")

    def _end(self, symbol: str) -> int:
        if self._cursor is None:
            return 0
        # number of bars with date <= cursor
        return int(np.searchsorted(self._dates[symbol], self._cursor, side="right"))

    def closes(self, symbol: str, n: int | None = None) -> np.ndarray:
        """Last `n` closing prices up to the current day (all if n is None)."""
        return self._series(symbol, "close", n)

    def opens(self, symbol: str, n: int | None = None) -> np.ndarray:
        return self._series(symbol, "open", n)

    def volumes(self, symbol: str, n: int | None = None) -> np.ndarray:
        return self._series(symbol, "volume", n)

    def bars_seen(self, symbol: str) -> int:
        """How many closed bars exist for `symbol` so far."""
        return self._end(symbol)

    def _series(self, symbol: str, field: str, n: int | None) -> np.ndarray:
        end = self._end(symbol)
        start = 0 if n is None else max(0, end - n)
        return self._fields[symbol][field][start:end]
