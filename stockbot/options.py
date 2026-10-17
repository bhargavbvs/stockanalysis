"""Option positions you hold: what they're worth, what they need, what time costs.

Set OPTIONS=APLD:2027-01-15:25C:20@6.897,INTC:2027-06-17:100C:1@25
(underlying : expiry : strike + C/P : contracts @ price paid per share, the
number Robinhood shows, i.e. $6.90 not $690). Quotes come from Yahoo's option
chain; delta, daily time decay and odds use Black-Scholes with the quoted
implied volatility (solved from the price when Yahoo has none).

Two break-even prices matter and they are different:
  * "beats selling today": strike + today's price. Above this at expiry,
    holding paid off versus selling now. This is the bet you are making by
    holding (sunk cost excluded).
  * "your cost back": strike + what you paid. Above this, the trade as a whole
    made money.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import date
from typing import Optional

RATE = 0.04  # risk-free rate for the Black-Scholes estimates
_STRIKE = re.compile(r"^(\d+(?:\.\d+)?)([CP])$")


@dataclass(frozen=True)
class OptionHolding:
    underlying: str
    expiry: date
    strike: float
    right: str  # "C" or "P"
    contracts: float
    cost: Optional[float] = None  # per share, as shown in Robinhood
    multiplier: int = 100

    @property
    def label(self) -> str:
        kind = "call" if self.right == "C" else "put"
        return f"{self.underlying} ${self.strike:g} {kind} {self.expiry:%b %d '%y}"


def parse_options(text: str) -> list[OptionHolding]:
    out = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            sym, exp, sk, rest = (x.strip() for x in part.split(":"))
            m = _STRIKE.match(sk.upper())
            if not m:
                raise ValueError
            qty, _, px = rest.partition("@")
            out.append(OptionHolding(sym.upper(), date.fromisoformat(exp), float(m.group(1)), m.group(2),
                                     float(qty), float(px) if px.strip() else None))
        except ValueError:
            raise ValueError(f"OPTIONS entry {part!r} must look like APLD:2027-01-15:25C:20@6.90") from None
    return out


# --------------------------------------------------------------------------- #
# Black-Scholes
# --------------------------------------------------------------------------- #


def _n(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _npdf(x: float) -> float:
    return math.exp(-x * x / 2) / math.sqrt(2 * math.pi)


@dataclass
class Greeks:
    price: float
    delta: float
    theta_day: float  # $ per share per calendar day (negative for long options)


def bs(spot: float, strike: float, years: float, vol: float, right: str, rate: float = RATE) -> Greeks:
    if years <= 0 or vol <= 0:
        intrinsic = max(0.0, spot - strike) if right == "C" else max(0.0, strike - spot)
        delta = (1.0 if spot > strike else 0.0) if right == "C" else (-1.0 if spot < strike else 0.0)
        return Greeks(intrinsic, delta, 0.0)
    st = vol * math.sqrt(years)
    d1 = (math.log(spot / strike) + (rate + vol * vol / 2) * years) / st
    d2 = d1 - st
    disc = math.exp(-rate * years)
    if right == "C":
        price = spot * _n(d1) - strike * disc * _n(d2)
        delta = _n(d1)
        theta = -spot * _npdf(d1) * vol / (2 * math.sqrt(years)) - rate * strike * disc * _n(d2)
    else:
        price = strike * disc * _n(-d2) - spot * _n(-d1)
        delta = _n(d1) - 1
        theta = -spot * _npdf(d1) * vol / (2 * math.sqrt(years)) + rate * strike * disc * _n(-d2)
    return Greeks(price, delta, theta / 365)


def implied_vol(price: float, spot: float, strike: float, years: float, right: str) -> Optional[float]:
    """Bisection; None when the price is below intrinsic value or the inputs are degenerate."""
    if price <= 0 or spot <= 0 or years <= 0:
        return None
    lo, hi = 0.01, 6.0
    if bs(spot, strike, years, lo, right).price > price or bs(spot, strike, years, hi, right).price < price:
        return None
    for _ in range(80):
        mid = (lo + hi) / 2
        if bs(spot, strike, years, mid, right).price > price:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def prob_beyond(spot: float, level: float, years: float, vol: float, right: str, rate: float = RATE) -> Optional[float]:
    """Options-market (risk-neutral) odds the stock finishes above `level` (below, for puts)."""
    if years <= 0 or vol <= 0 or level <= 0:
        return None
    d2 = (math.log(spot / level) + (rate - vol * vol / 2) * years) / (vol * math.sqrt(years))
    return _n(d2) if right == "C" else _n(-d2)


# --------------------------------------------------------------------------- #
# Position view
# --------------------------------------------------------------------------- #


@dataclass
class OptionQuote:
    bid: Optional[float]
    ask: Optional[float]
    last: Optional[float]
    iv: Optional[float]

    @property
    def live(self) -> bool:
        """False when Yahoo shows no bid and no ask (closed market / weekend pulls)."""
        return bool(self.bid) or bool(self.ask)

    @property
    def mark(self) -> Optional[float]:
        b, a = self.bid or 0.0, self.ask or 0.0
        if b > 0 and a > 0:
            return (min(b, a) + max(b, a)) / 2  # tolerate a crossed/stale quote
        if b > 0:
            return b
        if a > 0:  # no bid: half the ask, like Robinhood's mark (the last trade may be days old)
            return a / 2
        return self.last or None

    @property
    def no_bid(self) -> bool:
        return bool(self.ask) and not self.bid


@dataclass
class OptionView:
    holding: OptionHolding
    today: date
    spot: Optional[float]
    quote: Optional[OptionQuote]
    earnings_before_expiry: Optional[date] = None
    mark: Optional[float] = None
    iv: Optional[float] = None
    greeks: Optional[Greeks] = None

    @property
    def days_left(self) -> int:
        return (self.holding.expiry - self.today).days

    @property
    def shares(self) -> float:
        return self.holding.contracts * self.holding.multiplier

    @property
    def value(self) -> Optional[float]:
        return None if self.mark is None else self.mark * self.shares

    @property
    def paid(self) -> Optional[float]:
        return None if self.holding.cost is None else self.holding.cost * self.shares

    @property
    def pnl(self) -> Optional[float]:
        return None if self.value is None or self.paid is None else self.value - self.paid

    def _level(self, premium: Optional[float]) -> Optional[float]:
        if premium is None:
            return None
        h = self.holding
        return h.strike + premium if h.right == "C" else h.strike - premium

    @property
    def beat_selling(self) -> Optional[float]:
        return self._level(self.mark)

    @property
    def cost_back(self) -> Optional[float]:
        return self._level(self.holding.cost)

    def move(self, level: Optional[float]) -> Optional[float]:
        return None if level is None or not self.spot else (level / self.spot - 1) * 100

    @property
    def decay_day(self) -> Optional[float]:
        return None if self.greeks is None else self.greeks.theta_day * self.shares

    @property
    def delta_shares(self) -> Optional[float]:
        return None if self.greeks is None else self.greeks.delta * self.shares

    @property
    def odds(self) -> Optional[float]:
        if self.iv is None or self.spot is None or self.beat_selling is None:
            return None
        return prob_beyond(self.spot, self.beat_selling, self.days_left / 365, self.iv, self.holding.right)

    def lines(self) -> list[str]:
        h, L = self.holding, []
        head = f"*{h.label}* ×{h.contracts:g}"
        if self.days_left < 0:
            return [head + " – expired; remove it from OPTIONS"]
        if self.value is not None:
            head += f" – ${self.value:,.0f}"
            if self.paid:
                head += f" ({self.pnl / self.paid * 100:+.0f}%, paid ${self.paid:,.0f})"
        elif self.quote is None:
            head += " – no quote"
        L.append(head)
        bits = []
        if self.spot:
            bits.append(f"{h.underlying} ${self.spot:,.2f}")
        bits.append(f"{self.days_left} days left")
        if self.decay_day is not None and abs(self.decay_day) >= 1:
            word = "time decay -" if self.decay_day < 0 else "time value +"
            bits.append(f"{word}${abs(self.decay_day):,.0f}/day")
        L.append("   " + " · ".join(bits))
        word = "above" if h.right == "C" else "below"
        lv = []
        if self.beat_selling is not None and self.spot:
            odds = ""
            if self.odds is not None:
                odds = ", market odds <1%" if self.odds < 0.005 else f", market odds ~{self.odds * 100:.0f}%"
            lv.append(f"beats selling today {word} ${self.beat_selling:,.2f} ({self.move(self.beat_selling):+.0f}%{odds})")
        if self.cost_back is not None and self.spot:
            lv.append(f"your cost back {word} ${self.cost_back:,.2f} ({self.move(self.cost_back):+.0f}%)")
        if lv:
            L.append("   At expiry: " + " · ".join(lv))
        if self.quote and not self.quote.live and self.mark:
            L.append(f"   ➖ no live quote – priced at the last trade ${self.mark:,.2f}")
        elif self.quote and self.quote.no_bid:
            L.append("   ⚠️ no bid right now – it can't be sold at the moment")
        elif self.quote and self.quote.bid and self.quote.ask and self.mark and (self.quote.ask - self.quote.bid) / self.mark > 0.15:
            L.append(f"   ⚠️ wide spread ${self.quote.bid:,.2f} / ${self.quote.ask:,.2f} – use a limit order near the middle")
        e = self.earnings_before_expiry
        if e and (e - self.today).days <= 21:
            L.append(f"   📅 {h.underlying} earnings {e:%b %d} ({(e - self.today).days} days) – option prices usually "
                     "drop after earnings (IV crush), even if the stock doesn't move")
        elif e and (h.expiry - e).days <= 14:
            L.append(f"   📅 {h.underlying} earnings {e:%b %d} lands {(h.expiry - e).days} days before expiry – "
                     "little time left to recover from a bad report")
        return L


def build_view(h: OptionHolding, today: date, spot: Optional[float], quote: Optional[OptionQuote],
               earnings: Optional[date] = None) -> OptionView:
    v = OptionView(h, today, spot, quote)
    if earnings and today <= earnings <= h.expiry:
        v.earnings_before_expiry = earnings
    if quote is None:
        return v
    v.mark = quote.mark
    years = max(v.days_left, 0) / 365
    iv = quote.iv if quote.iv and 0.01 < quote.iv < 6 else None
    if iv is None and v.mark and spot:
        iv = implied_vol(v.mark, spot, h.strike, years, h.right)
    v.iv = iv
    if iv and spot and years > 0:
        v.greeks = bs(spot, h.strike, years, iv, h.right)
    return v
