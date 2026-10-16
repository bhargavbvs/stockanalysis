"""Backtest the exact live rules on daily history.

    python -m stockbot.backtest --symbols AAPL MSFT NVDA AMZN --period 10y
    python -m stockbot.backtest --compare          # effect of each filter layer
    python -m stockbot.backtest --csv trades.csv   # every trade

Mechanics (no look-ahead):
  * A SIGNAL on day i (known at its close) is entered at day i+1's open.
  * Stop distance comes from day i's ATR / 10-day swing (same as the live plan);
    target = target_r × that distance.
  * Each following day: stop checked before target (conservative when both are
    touched), gaps through a level fill at the open, time stop after
    `max_hold` days at the close. One position per symbol at a time.
  * Results are in R on the underlying (1R = the stop distance). Options P&L
    depends on strike/expiry/IV and is not modelled.
  * Earnings veto uses historical earnings dates when Yahoo has them. The macro
    event calendar only covers dates listed in events.yaml, so it is not
    applied to the past.
"""

from __future__ import annotations

import argparse
import logging
import math
from dataclasses import asdict, dataclass, replace
from typing import Optional

import numpy as np
import pandas as pd

from . import config, data, indicators, regime as rg, sector as sec
from .risk import RiskParams, stop_distance
from .signals import CONFIDENCE, SIGNAL, StrategyParams, classify, criteria

log = logging.getLogger(__name__)


@dataclass
class Trade:
    symbol: str
    direction: str
    signal_date: pd.Timestamp
    entry_date: pd.Timestamp
    entry: float
    stop: float
    target: float
    exit_date: pd.Timestamp
    exit: float
    reason: str  # stop | target | time | open
    r: float
    bars: int
    confidence: str
    regime_score: Optional[int] = None


def earnings_block_series(index: pd.DatetimeIndex, dates: Optional[list], days: int) -> pd.Series:
    if not dates:
        return pd.Series(False, index=index)
    arr = np.array(sorted(pd.Timestamp(d).normalize() for d in dates), dtype="datetime64[ns]")
    bars = index.normalize().values.astype("datetime64[ns]")
    pos = np.searchsorted(arr, bars, side="left")
    nxt = np.where(pos < len(arr), arr[np.minimum(pos, len(arr) - 1)], np.datetime64("NaT", "ns"))
    gap = (nxt - bars).astype("timedelta64[D]").astype(float)
    return pd.Series((gap >= 0) & (gap <= days), index=index)


def simulate(symbol: str, ind: pd.DataFrame, cls: pd.DataFrame, rp: RiskParams,
             regime_score: Optional[pd.Series] = None, earnings: Optional[list] = None) -> list[Trade]:
    """Replay the live plan: levels anchored to the signal close, entry next open.

    A trade is skipped when the next open has already gapped through the stop
    or the target (the alert's levels are no longer valid). Positions are
    closed at the end of the session before an earnings date, mirroring the
    plan's "exit by" rule.
    """
    o, h, l, c = (ind[k].to_numpy() for k in ("Open", "High", "Low", "Close"))
    atr = ind["atr"].to_numpy()
    status, direction, conf = cls["status"].to_numpy(), cls["direction"].to_numpy(), cls["confidence"].to_numpy()
    idx = ind.index
    days = idx.normalize()
    e_dates = np.array(sorted(pd.Timestamp(d).normalize() for d in (earnings or [])), dtype="datetime64[ns]")
    n = len(ind)
    trades: list[Trade] = []
    i = 0
    while i < n - 1:
        if status[i] != SIGNAL or not isinstance(direction[i], str) or not np.isfinite(atr[i]) or atr[i] <= 0:
            i += 1
            continue
        d = direction[i]
        sign = 1 if d == "CALL" else -1
        lo = max(0, i - rp.swing_lookback + 1)
        swing = float(l[lo:i + 1].min() if d == "CALL" else h[lo:i + 1].max())
        dist, _ = stop_distance(float(c[i]), swing, float(atr[i]), d, rp)
        stop = float(c[i]) - sign * dist
        target = float(c[i]) + sign * rp.target_r * dist
        e = i + 1
        entry = float(o[e])
        risk = sign * (entry - stop)
        if risk <= 0 or sign * (target - entry) <= 0:
            i += 1  # gapped through the stop or the target before we could enter
            continue

        last = min(n - 1, e + rp.max_hold_bars - 1)
        exit_reason_at_last = "time"
        if len(e_dates):
            k = np.searchsorted(e_dates, days[e].to_datetime64(), side="left")
            if k < len(e_dates):
                before = int(np.searchsorted(days.values, e_dates[k], side="left")) - 1  # session before earnings
                if before < e:
                    i += 1  # earnings tomorrow – the live veto would have blocked this
                    continue
                if before < last:
                    last, exit_reason_at_last = before, "earnings"

        exit_px, reason, j = None, "open", e
        for j in range(e, last + 1):
            op = float(o[j]) if j > e else entry
            if d == "CALL":
                if l[j] <= stop:
                    exit_px, reason = min(op, stop), "stop"
                elif h[j] >= target:
                    exit_px, reason = max(op, target), "target"
            else:
                if h[j] >= stop:
                    exit_px, reason = max(op, stop), "stop"
                elif l[j] <= target:
                    exit_px, reason = min(op, target), "target"
            if exit_px is not None:
                break
        if exit_px is None:
            j = last
            exit_px = float(c[j])
            ended_early = j == n - 1 and exit_reason_at_last == "time" and j < e + rp.max_hold_bars - 1
            reason = "open" if ended_early else exit_reason_at_last

        r = sign * (exit_px - entry) / risk
        trades.append(Trade(symbol, d, idx[i], idx[e], entry, stop, target, idx[j], exit_px, reason,
                            r, j - e + 1, str(conf[i]),
                            None if regime_score is None or pd.isna(regime_score.iloc[i]) else int(regime_score.iloc[i])))
        i = j + 1
    return trades


def summarize(trades: list[Trade]) -> dict:
    """Stats over closed trades, in exit order (open trades are only counted)."""
    closed = sorted((t for t in trades if t.reason != "open"), key=lambda t: t.exit_date)
    open_n = len(trades) - len(closed)
    if not closed:
        return {"trades": 0, "open": open_n}
    r = np.array([t.r for t in closed])
    cum = np.cumsum(r)
    dd = float((np.maximum.accumulate(np.r_[0.0, cum]) - np.r_[0.0, cum]).max())
    wins, losses = r[r > 0], r[r <= 0]
    return {
        "trades": len(r),
        "open": open_n,
        "win_rate": float((r > 0).mean()),
        "avg_r": float(r.mean()),
        "median_r": float(np.median(r)),
        "total_r": float(r.sum()),
        "profit_factor": float(wins.sum() / -losses.sum()) if losses.sum() < 0 else math.inf,
        "max_dd_r": dd,
        "avg_bars": float(np.mean([t.bars for t in closed])),
    }


@dataclass(frozen=True)
class Variant:
    name: str
    earnings: bool = True
    regime: bool = True
    sector: bool = True


VARIANTS = [
    Variant("core rules only", earnings=False, regime=False, sector=False),
    Variant("+ earnings veto", earnings=True, regime=False, sector=False),
    Variant("+ market regime", earnings=True, regime=True, sector=False),
    Variant("+ sector guard (live config)", earnings=True, regime=True, sector=True),
]


def run(histories: dict[str, pd.DataFrame], sp: StrategyParams, rp: RiskParams, variant: Variant,
        regime_frame: Optional[pd.DataFrame] = None, earnings: Optional[dict[str, list]] = None,
        sectors: Optional[dict[str, pd.DataFrame]] = None, sector_of: Optional[dict[str, str]] = None,
        defensive_at: int = 3, caution_at: int = 2, min_conf_rank: int = 0) -> list[Trade]:
    """Run one variant. Signals are filtered the way the live tracker filters
    alerts: MIN_CONFIDENCE, and HIGH+ for CALLs while the regime is CAUTION."""
    trades: list[Trade] = []
    for sym, df in histories.items():
        if len(df) < 200:
            continue
        ind = indicators.compute(df)
        c = criteria(ind, sp)
        e_block = earnings_block_series(ind.index, (earnings or {}).get(sym), sp.earnings_days) if variant.earnings else None
        score = risk_off = None
        if regime_frame is not None and not regime_frame.empty:
            score = regime_frame["score"].reindex(ind.index).ffill()
            if variant.regime:
                risk_off = score >= defensive_at
        s_block = None
        etf = (sector_of or {}).get(sym)
        if variant.sector and etf and sectors and etf in sectors:
            sf = sec.sector_frame(sectors[etf])
            blocked = (sf["extended"] | sf["breaking"]).astype(float)
            s_block = blocked.reindex(ind.index).ffill().fillna(0.0).astype(bool)
        cls = classify(c, replace(sp, use_regime=variant.regime), earnings_block=e_block,
                       risk_off=risk_off, sector_block=s_block).copy()
        rank = cls["confidence"].map({k: i for i, k in enumerate(CONFIDENCE)}).fillna(-1)
        need = pd.Series(min_conf_rank, index=cls.index)
        if variant.regime and score is not None:
            caution = (score >= caution_at) & (score < defensive_at) & (cls["direction"] == "CALL")
            need = need.where(~caution, max(min_conf_rank, CONFIDENCE.index("HIGH")))
        cls.loc[(cls["status"] == SIGNAL) & (rank < need), "status"] = "FILTERED"
        trades += simulate(sym, ind, cls, rp, score, (earnings or {}).get(sym) if variant.earnings else None)
    return trades


def forward_edge(histories: dict[str, pd.DataFrame], trades: list[Trade], horizon: int = 10) -> dict:
    """Mean `horizon`-day return after signal entries vs after every day (same direction)."""
    sig, base = [], {"CALL": [], "PUT": []}
    for sym, df in histories.items():
        fwd = (df["Close"].shift(-horizon) / df["Open"].shift(-1) - 1).dropna()
        base["CALL"].append(fwd)
        base["PUT"].append(-fwd)
    for t in trades:
        df = histories[t.symbol]
        pos = df.index.get_loc(t.signal_date)
        if pos + horizon < len(df):
            ret = df["Close"].iloc[pos + horizon] / df["Open"].iloc[pos + 1] - 1
            sig.append(ret if t.direction == "CALL" else -ret)
    out = {"horizon": horizon, "signals": float(np.mean(sig)) * 100 if sig else None}
    for d in ("CALL", "PUT"):
        allr = pd.concat(base[d]) if base[d] else pd.Series(dtype=float)
        out[f"all_days_{d.lower()}"] = float(allr.mean()) * 100 if len(allr) else None
    return out


def _fmt(s: dict) -> str:
    if not s.get("trades"):
        return "no closed trades"
    return (f"{s['trades']:>4} trades | win {s['win_rate']:5.1%} | avg {s['avg_r']:+.2f}R | "
            f"total {s['total_r']:+7.1f}R | PF {s['profit_factor']:.2f} | maxDD {s['max_dd_r']:.1f}R | "
            f"hold {s['avg_bars']:.1f}d" + (f" | {s['open']} still open" if s.get("open") else ""))


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Backtest the stock bot's rules")
    ap.add_argument("--symbols", nargs="*", help="default: WATCHLIST + PORTFOLIO from .env")
    ap.add_argument("--period", default="10y")
    ap.add_argument("--compare", action="store_true", help="show the effect of each filter layer")
    ap.add_argument("--csv", help="write every trade to this CSV")
    ap.add_argument("--target-r", type=float)
    ap.add_argument("--max-hold", type=int)
    ap.add_argument("--env", default=".env")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.WARNING)

    s = config.load(args.env)
    sp = s.strategy
    rp = replace(s.risk, **{k: v for k, v in (("target_r", args.target_r), ("max_hold_bars", args.max_hold)) if v})
    symbols = [x.upper() for x in (args.symbols or s.scan_symbols)]

    print(f"Downloading {len(symbols)} symbols ({args.period}) + market data…")
    hist = data.fetch_history(symbols, period=args.period)
    market = data.fetch_history(rg.MARKET_SYMBOLS, period=args.period)
    hy = data.fetch_fred(rg.HY_SERIES)
    rframe = rg.regime_frame(market, hy, s.regime)
    earnings = {sym: data.get_earnings_history(sym) for sym in hist}
    missing_e = [k for k, v in earnings.items() if not v]
    smap = sec.SectorMap(s.data_dir / "sectors.json", s.sector_overrides)
    sector_of = {sym: smap.get(sym) for sym in hist}
    sectors = data.fetch_history(sorted({e for e in sector_of.values() if e}), period=args.period)

    variants = VARIANTS if args.compare else [VARIANTS[-1]]
    print(f"\nRules: EMA stack + ADX≥{sp.adx_min:g} with DI direction, pullback ≤{sp.pullback_pct:g}% of 21 EMA, "
          f"stochastic; stop 1–3 ATR at swing, target {rp.target_r:g}R, time stop {rp.max_hold_bars}d\n")
    final = []
    for v in variants:
        trades = run(hist, sp, rp, v, rframe, earnings, sectors, sector_of, s.regime.defensive_at,
                     s.regime.caution_at, s.min_confidence_rank)
        print(f"{v.name:<30} {_fmt(summarize(trades))}")
        final = trades

    for d in ("CALL", "PUT"):
        sub = [t for t in final if t.direction == d]
        print(f"  {d:<28} {_fmt(summarize(sub))}")
    for conf in ("VERY HIGH", "HIGH", "MODERATE", "LOW"):
        sub = [t for t in final if t.confidence == conf]
        if sub:
            print(f"  conf {conf:<23} {_fmt(summarize(sub))}")
    by_year = pd.Series([t.r for t in final], index=[t.entry_date.year for t in final]).groupby(level=0).agg(["count", "sum", "mean"])
    if not by_year.empty:
        print("\nBy year (count, total R, avg R):")
        for y, row in by_year.iterrows():
            print(f"  {y}: {int(row['count']):>3}  {row['sum']:+6.1f}R  {row['mean']:+.2f}R")

    edge = forward_edge(hist, final)
    if edge["signals"] is not None:
        print(f"\n{edge['horizon']}-day move after signals: {edge['signals']:+.2f}% "
              f"(vs any day: calls {edge['all_days_call']:+.2f}%, puts {edge['all_days_put']:+.2f}%)")
    if missing_e:
        print(f"\nNote: no earnings history for {', '.join(missing_e)} – earnings veto not applied to them.")
    if hy is None:
        print("Note: credit-spread data unavailable – that regime component was off.")
    else:
        first = min(df.index[0] for df in hist.values()) if hist else None
        if first is not None and hy.index[0] > first + pd.Timedelta(days=30):
            print(f"Note: FRED only serves the HY spread from {hy.index[0]:%Y-%m-%d}; before that the credit "
                  "component was off, so early-period regime results are less strict.")
    print("Note: the macro event veto (CPI/jobs/FOMC) is not applied to the past; today's symbols "
          "carry survivorship bias (yesterday's losers aren't in the list).")
    print("Results are on the underlying in R multiples; options P&L is not modelled.")

    if args.csv:
        pd.DataFrame([asdict(t) for t in final]).to_csv(args.csv, index=False)
        print(f"Wrote {len(final)} trades to {args.csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
