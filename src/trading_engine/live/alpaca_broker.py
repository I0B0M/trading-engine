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


class AuthFailed(RuntimeError):
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

    def snapshot(self) -> tuple[float, dict[str, float]]:
        """Equity and position values in one call, with auth errors
        translated into something a human can act on."""
        from alpaca.common.exceptions import APIError

        try:
            equity = float(self._client.get_account().equity)
            positions = {
                p.symbol: float(p.market_value)
                for p in self._client.get_all_positions()
            }
        except APIError as e:
            if "unauthorized" in str(e).lower():
                raise AuthFailed(
                    "Alpaca rejected the credentials (unauthorized).\n\n"
                    "Most common causes, in order:\n"
                    "  1. The key ID and secret are from different generations. "
                    "A new pair invalidates the old one, and both halves must "
                    "come from the same 'Generate' click.\n"
                    "  2. The secret was copied incompletely, or with extra "
                    "text around it.\n"
                    "  3. They are LIVE keys, not paper keys. Paper keys are "
                    "generated on the Paper Trading page and the ID starts "
                    "with 'PK'.\n\n"
                    "Fix: generate a fresh PAPER pair at alpaca.markets, then "
                    "run 'trade keys' and enter both values from that same "
                    "screen."
                ) from e
            raise

        return equity, positions

    def equity(self) -> float:
        return self.snapshot()[0]

    def position_values(self) -> dict[str, float]:
        return self.snapshot()[1]

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
