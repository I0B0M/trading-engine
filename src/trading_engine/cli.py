"""Command-line entry point.

Examples:
    trade backtest sma_cross --symbols SPY --from 2010-01-01 --split 2021-01-01
    trade backtest momentum --symbols XLK,XLF,XLE,XLV,XLI,XLP,XLY,XLU,XLB
    trade live sma_cross --symbols SPY            # dry-run: prints the plan
    trade live sma_cross --symbols SPY --execute  # submits to the PAPER account
    trade account                                 # paper account status
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

    live = sub.add_parser("live", help="run a strategy against the Alpaca PAPER account")
    live.add_argument("strategy", choices=sorted(STRATEGIES))
    live.add_argument("--symbols", default="SPY", help="comma-separated tickers")
    live.add_argument("--lookback-days", type=int, default=400,
                      help="history replayed to reconstruct the strategy's state")
    live.add_argument("--param", action="append", default=[], metavar="KEY=VALUE")
    live.add_argument("--execute", action="store_true",
                      help="actually submit orders (default is a dry-run print)")

    sub.add_parser("account", help="show paper account equity and positions")
    sub.add_parser("keys", help="save Alpaca paper keys to .env interactively")

    args = parser.parse_args(argv)
    if args.command == "backtest":
        return _backtest(args)
    if args.command == "live":
        return _live(args)
    if args.command == "keys":
        return _keys()
    return _account()


def _parse_overrides(items: list[str]) -> dict:
    overrides = {}
    for item in items:
        key, _, value = item.partition("=")
        overrides[key] = float(value) if "." in value else int(value)
    return overrides


def _backtest(args: argparse.Namespace) -> int:
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    overrides = _parse_overrides(args.param)

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


def _live(args: argparse.Namespace) -> int:
    from .live.alpaca_broker import AlpacaPaperBroker, AuthFailed, MissingCredentials
    from .live.runner import compute_desired_weights, live_data_window, reconcile

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    strategy = STRATEGIES[args.strategy](**_parse_overrides(args.param))

    frames = live_data_window(symbols, lookback_days=args.lookback_days)
    desired = compute_desired_weights(strategy, frames)
    print(f"desired portfolio ({args.strategy}):")
    for symbol, weight in sorted(desired.items()):
        print(f"  {symbol:6} {weight:6.1%}")

    try:
        broker = AlpacaPaperBroker()
        equity, positions = broker.snapshot()
    except (MissingCredentials, AuthFailed) as e:
        print(f"\n{e}")
        return 1

    orders = reconcile(desired, equity, positions)

    print(f"\npaper account equity: ${equity:,.2f}")
    print(f"current positions: {positions or 'none'}")
    if not orders:
        print("already aligned with the strategy — nothing to do.")
        return 0

    print("\nplanned orders:")
    for order in orders:
        print(f"  {order.describe()}")

    if not args.execute:
        print("\ndry-run only. Re-run with --execute to submit to the PAPER account.")
        return 0

    print("\nsubmitting to PAPER account:")
    for order in orders:
        print(f"  {broker.submit(order)}")
    return 0


def _keys() -> int:
    """Prompt for Alpaca paper keys and write them to .env (mode 0600).

    Typed here rather than passed as arguments so the secret never lands in
    shell history; the secret prompt does not echo.
    """
    import getpass

    from .live.env import env_file_path

    target = env_file_path()
    print("Alpaca PAPER keys (https://alpaca.markets -> Paper Trading -> API Keys)")
    print(f"Saving to: {target}\n")

    try:
        key = input("API key ID       : ").strip()
        secret = getpass.getpass("Secret key (hidden): ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled; nothing was written.")
        return 1
    if not key or not secret:
        print("\nBoth values are required; nothing was written.")
        return 1

    other = {}
    if target.is_file():
        for raw in target.read_text().splitlines():
            line = raw.strip()
            if line and not line.startswith("#") and "=" in line:
                name, _, value = line.partition("=")
                name = name.strip()
                if name not in ("ALPACA_API_KEY", "ALPACA_SECRET_KEY"):
                    other[name] = value.strip()

    lines = [f"ALPACA_API_KEY={key}", f"ALPACA_SECRET_KEY={secret}"]
    lines += [f"{n}={v}" for n, v in other.items()]
    target.write_text("\n".join(lines) + "\n")
    target.chmod(0o600)

    print(f"\nSaved {len(lines)} entries to {target.name} (readable only by you).")
    print("Verify with:  trade account")
    return 0


def _account() -> int:
    from .live.alpaca_broker import AlpacaPaperBroker, AuthFailed, MissingCredentials

    try:
        equity, positions = AlpacaPaperBroker().snapshot()
    except (MissingCredentials, AuthFailed) as e:
        print(str(e))
        return 1
    print(f"paper equity: ${equity:,.2f}")
    for symbol, value in sorted(positions.items()):
        print(f"  {symbol:6} ${value:,.2f}")
    if not positions:
        print("  (no open positions)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
