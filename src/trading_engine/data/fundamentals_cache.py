"""Pre-loaded fundamentals, queryable point-in-time without network access.

A backtest asks "what was this company's gross profitability on 2014-04-01?"
thousands of times. Hitting the SEC API per query would be slow and rude, so
this fetches every company's full fact history once, then answers every later
question from memory -- while still respecting each fact's `filed` date, so
the point-in-time guarantee is unchanged.

Facts are also frozen to what was filed on or before an optional `built_for`
date, which makes it impossible for a later filing to leak backwards into an
earlier query even by accident.
"""

from __future__ import annotations

import datetime as dt

from .fundamentals import (
    CONCEPTS,
    Fact,
    SecClient,
    book_to_market,
    gross_profits_over_assets,
    point_in_time,
)


class FundamentalsCache:
    def __init__(self, client: SecClient | None = None):
        self._client = client
        self._facts: dict[str, dict[str, list[Fact]]] = {}
        self.unavailable: list[str] = []

    @property
    def client(self) -> SecClient:
        if self._client is None:
            self._client = SecClient()
        return self._client

    def load(self, symbols: list[str], verbose: bool = False) -> None:
        """One network pass. Symbols with no usable data are recorded, not
        raised -- coverage is ~70% for real universes and that is a fact to
        measure, not an error to crash on."""
        for symbol in symbols:
            if symbol in self._facts or symbol in self.unavailable:
                continue
            try:
                cik = self.client.cik_for_ticker(symbol)
                if cik is None:
                    self.unavailable.append(symbol)
                    continue
                by_field = {
                    field: self.client.concept_facts(cik, field) for field in CONCEPTS
                }
            except Exception:
                self.unavailable.append(symbol)
                continue
            if any(by_field.values()):
                self._facts[symbol] = by_field
            else:
                self.unavailable.append(symbol)
            if verbose:
                state = "ok" if symbol in self._facts else "no data"
                print(f"  {symbol:6} {state}")

    def value(self, symbol: str, field: str, as_of: dt.date) -> float | None:
        facts = self._facts.get(symbol, {}).get(field, [])
        fact = point_in_time(facts, as_of)
        return fact.value if fact else None

    def quality(self, symbol: str, as_of: dt.date) -> float | None:
        """Gross profits over assets, as known on `as_of`."""
        return gross_profits_over_assets(
            self.value(symbol, "revenue", as_of),
            self.value(symbol, "cogs", as_of),
            self.value(symbol, "assets", as_of),
        )

    def value_signal(
        self, symbol: str, as_of: dt.date, market_cap: float | None
    ) -> float | None:
        """Book-to-market. High means cheap."""
        return book_to_market(self.value(symbol, "equity", as_of), market_cap)

    def coverage(self, symbols: list[str], as_of: dt.date) -> dict[str, float]:
        """What fraction of `symbols` yields each signal on `as_of`.

        Call this before trusting a factor ranking: a signal that only exists
        for two-thirds of the universe is not ranking the universe, it is
        ranking a subset selected by accounting convention.
        """
        n = len(symbols) or 1
        got_quality = sum(1 for s in symbols if self.quality(s, as_of) is not None)
        got_equity = sum(
            1 for s in symbols if self.value(s, "equity", as_of) is not None
        )
        return {
            "loaded": len(self._facts) / n,
            "quality": got_quality / n,
            "book_equity": got_equity / n,
        }
