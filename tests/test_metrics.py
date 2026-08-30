"""Metrics checked against hand-computed values."""

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from trading_engine.metrics.report import compute_metrics, split_metrics


def _series(values: list[float]) -> pd.Series:
    dates = [dt.date(2020, 1, 1) + dt.timedelta(days=i) for i in range(len(values))]
    return pd.Series(values, index=pd.Index(dates, name="date"))


def test_max_drawdown_hand_computed():
    # peak 120 -> trough 90 is a 25% drawdown
    m = compute_metrics(_series([100, 120, 90, 100]), "t")
    assert m.max_drawdown == pytest.approx(-0.25)
    assert m.total_return == pytest.approx(0.0)


def test_cagr_doubling_in_one_trading_year():
    # 252 daily points, 100 -> 200: exactly one trading year, CAGR = 100%
    values = list(np.linspace(100, 200, 252))
    m = compute_metrics(_series(values), "t")
    assert m.cagr == pytest.approx(1.0)
    assert m.total_return == pytest.approx(1.0)
    assert m.sharpe > 0


def test_split_produces_in_and_out_of_sample():
    values = list(np.linspace(100, 200, 100))
    split_date = dt.date(2020, 1, 1) + dt.timedelta(days=50)
    parts = split_metrics(_series(values), split_date, "t")
    labels = [m.label for m in parts]
    assert labels == ["t (full)", "t (in-sample)", "t (out-of-sample)"]
    assert parts[1].end < split_date <= parts[2].start
