from __future__ import annotations

import datetime as dt

import pandas as pd


def make_frame(start: dt.date, opens: list[float], closes: list[float]) -> pd.DataFrame:
    """Synthetic OHLCV frame on consecutive calendar days."""
    assert len(opens) == len(closes)
    dates = [start + dt.timedelta(days=i) for i in range(len(opens))]
    return pd.DataFrame(
        {
            "open": opens,
            "high": [max(o, c) for o, c in zip(opens, closes)],
            "low": [min(o, c) for o, c in zip(opens, closes)],
            "close": closes,
            "volume": [1_000_000.0] * len(opens),
        },
        index=pd.Index(dates, name="date"),
    )
