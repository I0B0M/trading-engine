"""Thin adapter over the Alpaca paper-trading API.

PAPER ONLY, permanently: `paper=True` is hard-coded and there is no code path
in this project that can reach a live-money endpoint. Orders are notional
market orders with DAY time-in-force; submitted after hours they queue for
the next market open — the same fill timing the backtester assumes.

Credentials come from a gitignored `.env` at the repo root, or the environment:
    ALPACA_API_KEY / ALPACA_SECRET_KEY  (or the APCA_API_KEY_ID /
    APCA_API_SECRET_KEY names Alpaca's own tooling uses)
"""

from __future__ import annotations

import os

from .env import load_env_file
from .runner import PlannedOrder


class MissingCredentials(RuntimeError):
    pass


def _env(*names: str) -> str | None:
    load_env_file()
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return None


class AlpacaPaperBroker:
    def __init__(self):
        key = _env("ALPACA_API_KEY", "APCA_API_KEY_ID")
        secret = _env("ALPACA_SECRET_KEY", "APCA_API_SECRET_KEY")
        if not key or not secret:
            raise MissingCredentials(
                "Alpaca paper keys not found. Create a free account at "
                "https://alpaca.markets, generate PAPER API keys from the "
                "dashboard, then copy .env.example to .env and fill in:\n"
                "  ALPACA_API_KEY=...\n  ALPACA_SECRET_KEY=...\n"
                ".env is gitignored, so the keys stay off the command line "
                "and out of shell history."
            )
        from alpaca.trading.client import TradingClient

        self._client = TradingClient(key, secret, paper=True)  # never live

    def equity(self) -> float:
        return float(self._client.get_account().equity)

    def position_values(self) -> dict[str, float]:
        return {
            p.symbol: float(p.market_value)
            for p in self._client.get_all_positions()
        }

    def submit(self, order: PlannedOrder) -> str:
        from alpaca.trading.enums import OrderSide, TimeInForce
        from alpaca.trading.requests import MarketOrderRequest

        if order.action == "close":
            self._client.close_position(order.symbol)
            return f"closed {order.symbol}"
        side = OrderSide.BUY if order.action == "buy" else OrderSide.SELL
        request = MarketOrderRequest(
            symbol=order.symbol,
            notional=order.notional,
            side=side,
            time_in_force=TimeInForce.DAY,
        )
        placed = self._client.submit_order(request)
        return f"order {placed.id}: {order.describe()}"
