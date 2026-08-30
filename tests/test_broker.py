"""Broker fill math checked against hand-computed numbers."""

import datetime as dt

import pytest

from trading_engine.engine.broker import SimulatedBroker
from trading_engine.engine.events import TargetOrder
from trading_engine.engine.portfolio import Portfolio

D = dt.date(2020, 1, 2)


def test_buy_applies_slippage_and_commission():
    # $10,000 cash, buy 50% at open 100, slippage 5bps, commission 1bp:
    # shares = 5000/100 = 50, fill price = 100.05,
    # commission = 50 * 100.05 * 0.0001 = 0.500250,
    # cash = 10000 - 50*100.05 - 0.50025 = 4996.99975
    broker = SimulatedBroker(commission_bps=1.0, slippage_bps=5.0)
    pf = Portfolio(10_000.0)
    broker.execute([TargetOrder("AAA", 0.5, D)], {"AAA": 100.0}, D, pf)

    assert len(pf.fills) == 1
    fill = pf.fills[0]
    assert fill.shares == pytest.approx(50.0)
    assert fill.price == pytest.approx(100.05)
    assert fill.commission == pytest.approx(0.500250)
    assert pf.cash == pytest.approx(4996.99975)
    assert pf.positions == {"AAA": pytest.approx(50.0)}


def test_sell_slips_against_the_trader():
    # Holding 50 shares, exit at open 110: fill price = 110 * (1 - 0.0005)
    # = 109.945, commission = 50 * 109.945 * 0.0001 = 0.549725
    broker = SimulatedBroker(commission_bps=1.0, slippage_bps=5.0)
    pf = Portfolio(10_000.0)
    broker.execute([TargetOrder("AAA", 0.5, D)], {"AAA": 100.0}, D, pf)

    d2 = D + dt.timedelta(days=1)
    broker.execute([TargetOrder("AAA", 0.0, d2)], {"AAA": 110.0}, d2, pf)

    fill = pf.fills[-1]
    assert fill.shares == pytest.approx(-50.0)
    assert fill.price == pytest.approx(109.945)
    assert fill.commission == pytest.approx(0.549725)
    assert pf.positions == {}
    assert pf.cash == pytest.approx(4996.99975 + 50 * 109.945 - 0.549725)


def test_order_for_symbol_without_price_is_dropped():
    broker = SimulatedBroker()
    pf = Portfolio(10_000.0)
    broker.execute([TargetOrder("MISSING", 1.0, D)], {}, D, pf)
    assert pf.fills == []
    assert pf.cash == 10_000.0
