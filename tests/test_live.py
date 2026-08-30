"""Live-layer logic: desired-weight reconstruction and order reconciliation.
No network, no Alpaca — pure logic tests."""

import datetime as dt

import pytest

from tests.conftest import make_frame
from trading_engine.engine.strategy import Strategy
from trading_engine.live.runner import compute_desired_weights, reconcile

START = dt.date(2020, 1, 1)


class StagesOnceEarly(Strategy):
    """Stages weights on day 2 only, like a monthly rebalancer mid-month."""

    def on_bars(self, date, bars, history):
        if date == START + dt.timedelta(days=1):
            self.target_position("AAA", 0.6)
            self.target_position("BBB", 0.0)


def test_desired_weights_persist_after_stage_day():
    # The last stage happened long before the final bar; the accumulated
    # targets must still reflect it.
    frames = {
        "AAA": make_frame(START, opens=[100] * 10, closes=[100] * 10),
        "BBB": make_frame(START, opens=[50] * 10, closes=[50] * 10),
    }
    desired = compute_desired_weights(StagesOnceEarly(), frames)
    assert desired == {"AAA": 0.6, "BBB": 0.0}


def test_reconcile_hand_computed():
    # equity $100k: want 60% AAA ($60k, hold $10k -> buy $50k),
    # exit BBB entirely, and CCC is not the strategy's business.
    orders = reconcile(
        desired_weights={"AAA": 0.6, "BBB": 0.0},
        equity=100_000.0,
        position_values={"AAA": 10_000.0, "BBB": 5_000.0, "CCC": 7_000.0},
    )
    by_symbol = {o.symbol: o for o in orders}
    assert by_symbol["AAA"].action == "buy"
    assert by_symbol["AAA"].notional == pytest.approx(50_000.0)
    assert by_symbol["BBB"].action == "close"
    assert "CCC" not in by_symbol


def test_reconcile_skips_dust_rebalances():
    # Off by only 0.3% of equity -> below the 0.5% threshold, no order.
    orders = reconcile(
        desired_weights={"AAA": 0.5},
        equity=100_000.0,
        position_values={"AAA": 49_700.0},
    )
    assert orders == []


def test_reconcile_sells_down_overweight_position():
    orders = reconcile(
        desired_weights={"AAA": 0.2},
        equity=100_000.0,
        position_values={"AAA": 35_000.0},
    )
    assert len(orders) == 1
    assert orders[0].action == "sell"
    assert orders[0].notional == pytest.approx(15_000.0)
