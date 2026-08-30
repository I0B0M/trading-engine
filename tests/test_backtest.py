"""Replay-loop semantics: no lookahead, next-open fills, correct equity."""

import datetime as dt

import pytest

from tests.conftest import make_frame
from trading_engine.engine.backtest import run_backtest
from trading_engine.engine.broker import SimulatedBroker
from trading_engine.engine.events import Bar
from trading_engine.engine.history import History
from trading_engine.engine.strategy import Strategy
from trading_engine.strategies.buy_and_hold import BuyAndHold

START = dt.date(2020, 1, 1)
FREE = SimulatedBroker(commission_bps=0.0, slippage_bps=0.0)


def test_history_never_shows_the_future():
    seen = []

    class Recorder(Strategy):
        def on_bar(self, bar: Bar, history: History) -> None:
            closes = history.closes(bar.symbol)
            seen.append((len(closes), closes[-1], bar.close))

    frame = make_frame(START, opens=[100, 101, 102, 103], closes=[100.5, 101.5, 102.5, 103.5])
    run_backtest(Recorder(), {"AAA": frame}, broker=FREE)

    # Each day the window grows by exactly one bar and ends at today's close.
    assert [(n, last) for n, last, _ in seen] == [
        (1, 100.5), (2, 101.5), (3, 102.5), (4, 103.5)
    ]
    for _, last_visible, todays_close in seen:
        assert last_visible == todays_close


def test_signal_on_day_t_fills_at_day_t_plus_1_open():
    frame = make_frame(START, opens=[100, 105, 106], closes=[101, 105.5, 106.5])
    result = run_backtest(BuyAndHold(), {"AAA": frame}, initial_cash=10_000.0, broker=FREE)

    assert len(result.fills) == 1
    fill = result.fills[0]
    assert fill.date == START + dt.timedelta(days=1)  # not the signal day
    assert fill.price == pytest.approx(105.0)  # day-2 OPEN, not day-1 close


def test_buy_and_hold_equity_matches_hand_math():
    # Buys at day-2 open (100) with $10,000 -> 100 shares; final close 120.
    frame = make_frame(START, opens=[100, 100, 110, 120], closes=[100, 110, 120, 120])
    result = run_backtest(BuyAndHold(), {"AAA": frame}, initial_cash=10_000.0, broker=FREE)

    assert result.final_equity == pytest.approx(12_000.0)
    assert result.equity_curve.iloc[0] == pytest.approx(10_000.0)  # day 1: still cash
    assert result.final_positions == {"AAA": pytest.approx(100.0)}


def test_unknown_strategy_param_rejected():
    with pytest.raises(TypeError):
        BuyAndHold(nonsense=1)
