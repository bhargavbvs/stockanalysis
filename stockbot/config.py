"""Settings, read from environment variables (and a local .env file if present).

No secrets live in the code. See .env.example for every option.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .leverage import DEFAULT_LEVERAGED, LeveragedETF, parse_leveraged
from .options import OptionHolding, parse_options
from .regime import RegimeParams
from .risk import RiskParams
from .signals import CONFIDENCE, StrategyParams

DEFAULT_WATCHLIST = "AAPL,MSFT,GOOGL,AMZN,TSLA,NVDA,META,NFLX,AMD,AVGO"
DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _bool(name: str, default: bool) -> bool:
    v = _env(name)
    return default if not v else v.lower() in ("1", "true", "yes", "on")


def _float(name: str, default: Optional[float]) -> Optional[float]:
    v = _env(name)
    return default if not v else float(v)


def _int(name: str, default: int) -> int:
    v = _env(name)
    return default if not v else int(v)


@dataclass(frozen=True)
class Holding:
    symbol: str
    shares: Optional[float] = None
    cost: Optional[float] = None


def parse_portfolio(text: str) -> list[Holding]:
    """"AAPL:10@182.50, NVDA:5, MSFT" -> holdings (shares and cost are optional)."""
    out = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        sym, _, rest = part.partition(":")
        shares, cost = None, None
        if rest:
            qty, _, px = rest.partition("@")
            shares = float(qty) if qty.strip() else None
            cost = float(px) if px.strip() else None
        out.append(Holding(sym.strip().upper(), shares, cost))
    return out


def _pairs(text: str) -> dict[str, str]:
    out = {}
    for part in text.split(","):
        k, _, v = part.partition(":")
        if k.strip() and v.strip():
            out[k.strip().upper()] = v.strip().upper()
    return out


@dataclass
class Settings:
    # WhatsApp
    whatsapp_provider: str = "callmebot"  # callmebot | twilio
    whatsapp_phone: str = ""  # international format, e.g. +15105551234
    callmebot_api_key: str = ""
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_whatsapp_from: str = "whatsapp:+14155238886"
    # Telegram
    telegram_token: str = ""
    telegram_chat_id: str = ""
    allowed_chat_ids: set[str] = field(default_factory=set)
    # Other channels (optional)
    discord_webhook_url: str = ""
    webhook_url: str = ""
    email_smtp_server: str = "smtp.gmail.com"
    email_smtp_port: int = 587
    email_sender: str = ""
    email_password: str = ""
    email_recipient: str = ""
    # Scanning
    watchlist: list[str] = field(default_factory=list)
    portfolio: list[Holding] = field(default_factory=list)
    options: list[OptionHolding] = field(default_factory=list)
    leveraged: dict[str, LeveragedETF] = field(default_factory=lambda: dict(DEFAULT_LEVERAGED))
    scan_interval_minutes: int = 30
    min_confidence: str = "MODERATE"
    alert_cooldown_hours: float = 24.0
    alert_setups: bool = False
    confirm_on_close: bool = True
    events_file: Path = Path("events.yaml")
    sector_guard: bool = True
    sector_overrides: dict[str, str] = field(default_factory=dict)
    data_dir: Path = Path("data")
    # Morning brief
    brief_enabled: bool = True
    brief_time: str = "06:00"
    brief_tz: str = "America/Los_Angeles"
    brief_days: tuple[str, ...] = DAYS
    anthropic_api_key: str = ""
    brief_model: str = "claude-sonnet-5-5"
    brief_language: str = "English"
    brief_max_searches: int = 8
    brief_split: bool = True  # news and stocks as two separate messages
    brief_deep_stocks: int = 6  # holdings that get the full fundamentals/analyst block
    # Sizing (optional)
    account_size: Optional[float] = None
    risk_pct: float = 1.0
    # Rules
    strategy: StrategyParams = field(default_factory=StrategyParams)
    risk: RiskParams = field(default_factory=RiskParams)
    regime: RegimeParams = field(default_factory=RegimeParams)

    @property
    def email_enabled(self) -> bool:
        return bool(self.email_sender and self.email_password and self.email_recipient)

    @property
    def min_confidence_rank(self) -> int:
        return CONFIDENCE.index(self.min_confidence) if self.min_confidence in CONFIDENCE else 1

    @property
    def portfolio_symbols(self) -> list[str]:
        return [h.symbol for h in self.portfolio]

    def underlying(self, symbol: str) -> str:
        """The company behind a leveraged ETF (SNXX -> SNDK); the symbol itself otherwise."""
        lev = self.leveraged.get(symbol.upper())
        return lev.underlying if lev else symbol.upper()

    @property
    def scan_symbols(self) -> list[str]:
        """Watchlist plus portfolio, de-duplicated, order kept."""
        return list(dict.fromkeys(self.watchlist + self.portfolio_symbols))


def load(env_file: Optional[str] = ".env") -> Settings:
    if env_file:
        try:
            from dotenv import load_dotenv

            load_dotenv(env_file, override=False)
        except ImportError:
            pass

    min_conf = _env("MIN_CONFIDENCE", "MODERATE").upper()
    if min_conf not in CONFIDENCE:
        raise ValueError(f"MIN_CONFIDENCE must be one of {', '.join(CONFIDENCE)}")
    provider = _env("WHATSAPP_PROVIDER", "callmebot").lower()
    if provider not in ("callmebot", "twilio"):
        raise ValueError("WHATSAPP_PROVIDER must be callmebot or twilio")
    days = tuple(d.strip().lower()[:3] for d in _env("BRIEF_DAYS", ",".join(DAYS)).split(",") if d.strip())
    bad_days = [d for d in days if d not in DAYS]
    if bad_days:
        raise ValueError(f"BRIEF_DAYS has unknown days {bad_days}; use mon,tue,wed,thu,fri,sat,sun")
    brief_time = _env("BRIEF_TIME", "06:00")
    try:
        hh, mm = (int(x) for x in brief_time.split(":"))
        assert 0 <= hh < 24 and 0 <= mm < 60
    except Exception:
        raise ValueError(f"BRIEF_TIME must be HH:MM (24h), got {brief_time!r}") from None
    brief_tz = _env("BRIEF_TZ", "America/Los_Angeles")
    try:
        from zoneinfo import ZoneInfo

        ZoneInfo(brief_tz)
    except Exception:
        raise ValueError(f"BRIEF_TZ must be an IANA time zone like America/Los_Angeles, got {brief_tz!r}") from None
    unknown_earnings = _env("EARNINGS_UNKNOWN", "block").lower()
    if unknown_earnings not in ("block", "warn"):
        raise ValueError("EARNINGS_UNKNOWN must be block or warn")

    return Settings(
        whatsapp_provider=provider,
        whatsapp_phone=_env("WHATSAPP_PHONE"),
        callmebot_api_key=_env("CALLMEBOT_API_KEY"),
        twilio_account_sid=_env("TWILIO_ACCOUNT_SID"),
        twilio_auth_token=_env("TWILIO_AUTH_TOKEN"),
        twilio_whatsapp_from=_env("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886"),
        telegram_token=_env("TELEGRAM_BOT_TOKEN"),
        telegram_chat_id=_env("TELEGRAM_CHAT_ID"),
        allowed_chat_ids={c.strip() for c in _env("ALLOWED_CHAT_IDS").split(",") if c.strip()},
        discord_webhook_url=_env("DISCORD_WEBHOOK_URL"),
        webhook_url=_env("WEBHOOK_URL"),
        email_smtp_server=_env("EMAIL_SMTP_SERVER", "smtp.gmail.com"),
        email_smtp_port=_int("EMAIL_SMTP_PORT", 587),
        email_sender=_env("EMAIL_SENDER"),
        email_password=_env("EMAIL_PASSWORD"),
        email_recipient=_env("EMAIL_RECIPIENT"),
        watchlist=[s.strip().upper() for s in _env("WATCHLIST", DEFAULT_WATCHLIST).split(",") if s.strip()],
        portfolio=parse_portfolio(_env("PORTFOLIO")),
        options=parse_options(_env("OPTIONS")),
        leveraged=parse_leveraged(_env("LEVERAGED_ETFS")),
        scan_interval_minutes=_int("SCAN_INTERVAL_MINUTES", 30),
        min_confidence=min_conf,
        alert_cooldown_hours=_float("ALERT_COOLDOWN_HOURS", 24.0),
        alert_setups=_bool("ALERT_SETUPS", False),
        confirm_on_close=_bool("CONFIRM_ON_CLOSE", True),
        events_file=Path(_env("EVENTS_FILE", "events.yaml")),
        sector_guard=_bool("SECTOR_GUARD", True),
        sector_overrides=_pairs(_env("SECTOR_OVERRIDES")),
        data_dir=Path(_env("DATA_DIR", "data")),
        brief_enabled=_bool("BRIEF_ENABLED", True),
        brief_time=brief_time,
        brief_tz=brief_tz,
        brief_days=days or DAYS,
        anthropic_api_key=_env("ANTHROPIC_API_KEY"),
        brief_model=_env("BRIEF_MODEL", "claude-sonnet-5-5"),
        brief_language=_env("BRIEF_LANGUAGE", "English"),
        brief_max_searches=_int("BRIEF_MAX_SEARCHES", 8),
        brief_split=_bool("BRIEF_SPLIT", True),
        brief_deep_stocks=_int("BRIEF_DEEP_STOCKS", 6),
        account_size=_float("ACCOUNT_SIZE", None),
        risk_pct=_float("RISK_PER_TRADE_PCT", 1.0),
        strategy=StrategyParams(
            pullback_pct=_float("PULLBACK_PCT", 2.0),
            adx_min=_float("ADX_MIN", 20.0),
            earnings_days=_int("EARNINGS_BLACKOUT_DAYS", 14),
            use_regime=_bool("REGIME_FILTER", True),
            block_unknown_earnings=unknown_earnings == "block",
        ),
        risk=RiskParams(target_r=_float("TARGET_R", 2.0), max_hold_bars=_int("MAX_HOLD_DAYS", 20)),
        regime=RegimeParams(vix_max=_float("VIX_MAX", 25.0), vix_spike_pct=_float("VIX_SPIKE_PCT", 30.0)),
    )
