"""Command-line entry point.

Examples:
    trade backtest sma_cross --symbols SPY --from 2010-01-01 --split 2021-01-01
    trade backtest momentum --symbols XLK,XLF,XLE,XLV,XLI,XLP,XLY,XLU,XLB
"""

from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path

from .data.loader import load_bars
from .engine.backtest import run_backtest
from .metrics.report import format_report, save_equity_chart, split_metrics
from .strategies.buy_and_hold import BuyAndHold
from .strategies.momentum import SectorMomentum
from .strategies.rsi_reversion import RsiReversion
from .strategies.sma_cross import SmaCross

STRATEGIES = {
    "buy_and_hold": BuyAndHold,
    "sma_cross": SmaCross,
    "momentum": SectorMomentum,
    "rsi_reversion": RsiReversion,
}

SECTOR_ETFS = "XLK,XLF,XLE,XLV,XLI,XLP,XLY,XLU,XLB"


def _date(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="trade")
    sub = parser.add_subparsers(dest="command", required=True)

    bt = sub.add_parser("backtest", help="replay a strategy over history")
    bt.add_argument("strategy", choices=sorted(STRATEGIES))
    bt.add_argument("--symbols", default="SPY", help="comma-separated tickers")
    bt.add_argument("--from", dest="start", type=_date, default=dt.date(2010, 1, 1))
    bt.add_argument("--to", dest="end", type=_date, default=dt.date.today())
    bt.add_argument("--split", type=_date, default=None,
                    help="in-sample/out-of-sample boundary date")
    bt.add_argument("--cash", type=float, default=100_000.0)
    bt.add_argument("--benchmark", default="SPY")
    bt.add_argument("--param", action="append", default=[], metavar="KEY=VALUE",
                    help="strategy parameter override, repeatable")
    bt.add_argument("--report-dir", default="reports")

    args = parser.parse_args(argv)
    return _backtest(args)


def _backtest(args: argparse.Namespace) -> int:
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    overrides = {}
    for item in args.param:
        key, _, value = item.partition("=")
        overrides[key] = float(value) if "." in value else int(value)

    strategy = STRATEGIES[args.strategy](**overrides)
    frames = load_bars(symbols, args.start, args.end)
    result = run_backtest(strategy, frames, start=args.start, end=args.end,
                          initial_cash=args.cash)

    benchmark = args.benchmark.upper()
    bench_frames = load_bars([benchmark], args.start, args.end)
    bench_equity = bench_frames[benchmark]["close"]
    # scale benchmark to the same starting equity for a fair curve
    bench_equity = bench_equity / bench_equity.iloc[0] * result.initial_equity

    strat_metrics = split_metrics(result.equity_curve, args.split, args.strategy)
    bench_metrics = split_metrics(bench_equity, args.split, f"hold {benchmark}")

    print(format_report(strat_metrics, bench_metrics, n_fills=len(result.fills)))

    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    chart = report_dir / f"{args.strategy}_{args.start}_{args.end}.png"
    save_equity_chart(
        result.equity_curve, bench_equity, str(chart),
        title=f"{args.strategy} on {','.join(symbols)} vs {benchmark}",
        split=args.split,
    )
    print(f"equity chart: {chart}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
