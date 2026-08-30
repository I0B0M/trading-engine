"""Historical daily bars via yfinance, cached locally as parquet.

Prices are split- and dividend-adjusted (auto_adjust=True), which is the
right basis for strategy returns. Phase 2 swaps in Alpaca's data API behind
this same function signature.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd

CACHE_DIR = Path(__file__).resolve().parents[3] / "data_cache"
EARLIEST = dt.date(2000, 1, 3)
COLUMNS = ["open", "high", "low", "close", "volume"]


def load_bars(
    symbols: list[str],
    start: dt.date,
    end: dt.date,
    cache_dir: Path | None = None,
) -> dict[str, pd.DataFrame]:
    """Return per-symbol OHLCV frames indexed by datetime.date, covering
    [start, end] (or the symbol's full listed life within it)."""
    cache_dir = cache_dir or CACHE_DIR
    cache_dir.mkdir(parents=True, exist_ok=True)
    frames: dict[str, pd.DataFrame] = {}
    for symbol in symbols:
        df = _load_symbol(symbol, end, cache_dir)
        df = df[(df.index >= start) & (df.index <= end)]
        if df.empty:
            raise ValueError(f"no data for {symbol} in {start}..{end}")
        frames[symbol] = df
    return frames


def _load_symbol(symbol: str, end: dt.date, cache_dir: Path) -> pd.DataFrame:
    path = cache_dir / f"{symbol.upper()}.parquet"
    if path.exists():
        cached = pd.read_parquet(path)
        # refresh if the cache is more than 3 days behind what's requested
        if cached.index.max() >= min(end, dt.date.today()) - dt.timedelta(days=3):
            return cached
    df = _download(symbol)
    df.to_parquet(path)
    return df


def _download(symbol: str) -> pd.DataFrame:
    import yfinance as yf

    raw = yf.download(
        symbol,
        start=EARLIEST.isoformat(),
        auto_adjust=True,
        progress=False,
        multi_level_index=False,
    )
    if raw is None or raw.empty:
        raise ValueError(f"yfinance returned no data for {symbol}")
    df = raw.rename(columns=str.lower)[COLUMNS].dropna()
    df.index = pd.Index([ts.date() for ts in df.index], name="date")
    return df
