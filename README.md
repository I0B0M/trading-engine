# trading-engine

An event-driven backtesting engine for stock trading strategies. Replays
15+ years of daily market data one closed bar at a time, simulates every
trade through a broker model with slippage and commissions, and reports
performance with a mandatory in-sample/out-of-sample split.

Phase 1 of three:

1. **Backtesting engine** (this) — test strategies on the past.
2. **Paper trading** — run the same strategy code on live prices with fake
   money via Alpaca's paper API.
3. **AI assistant** — describe a strategy in plain English; an LLM compiles
   it to a validated config, the engine backtests it and reports. The AI
   suggests; it never trades.

## Design rules

- **No lookahead, structurally.** Strategies read history through a cursor
  that only the engine advances; a signal computed on day T fills at day
  T+1's open, never at T's prices. There is no API through which a strategy
  can see the future.
- **Costs always on.** 5 bps slippage against the trader and 1 bp commission
  by default. Free-trading fantasies flatter every strategy.
- **Out-of-sample verdicts.** `--split` reports tuned-period and unseen-period
  results separately, because strategies that only work on the data they were
  tuned on are memorizing, not predicting.
- **Engine verified against reality.** Buy-and-hold SPY through the simulator
  must reproduce SPY's actual return (it does, within 0.5pp over 16 years),
  and broker math is pytest-checked against hand-computed fills.

## Usage

```bash
uv sync
uv run trade backtest sma_cross --symbols SPY --from 2010-01-01 --split 2021-01-01
uv run trade backtest momentum --symbols XLK,XLF,XLE,XLV,XLI,XLP,XLY,XLU,XLB
uv run trade backtest rsi_reversion --symbols SPY --param entry_below=15
```

Each run prints a report card (total return, CAGR, Sharpe, max drawdown,
against a buy-the-index benchmark) and saves an equity-curve chart to
`reports/`.

## Strategies

| Name | Idea |
|---|---|
| `buy_and_hold` | Buy on day one, never sell. The benchmark and the engine's sanity check. |
| `sma_cross` | Golden cross: invested while the 50-day average is above the 200-day. |
| `momentum` | Monthly, hold the 3 sector ETFs with the strongest 6-month return. |
| `rsi_reversion` | In an uptrend, buy sharp 2-day dips, exit on recovery. |

A strategy is a small class; the engine does everything else:

```python
class SmaCross(Strategy):
    params = {"fast": 50, "slow": 200}

    def on_bar(self, bar, history):
        closes = history.closes(bar.symbol, self.p.slow)
        if sma(closes, self.p.fast) > sma(closes, self.p.slow):
            self.target_position(bar.symbol, 1.0)
        else:
            self.target_position(bar.symbol, 0.0)
```

## Layout

```
src/trading_engine/
├── engine/      # events, history window, portfolio, broker sim, replay loop
├── data/        # yfinance loader with local parquet cache
├── strategies/  # one class per strategy + shared indicators
├── metrics/     # CAGR / Sharpe / drawdown, report, equity charts
└── cli.py       # `trade backtest ...`
tests/           # broker & metrics vs hand-computed numbers; no-lookahead proof
```

## Tests

```bash
uv run pytest
```

Disclaimer: educational project. Simulated and paper results are not
investment advice, and past performance does not predict future returns.
