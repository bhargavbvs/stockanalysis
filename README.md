# Stock Signal Bot

Scans US stocks for Fibonacci-EMA pullback setups (The Tao of Trading style), checks them against the market regime, the economic calendar, earnings and the stock's sector, and sends alerts to **WhatsApp** (and/or Telegram, Discord, email, webhook). Every morning it sends a **brief as two messages**:

1. **Market news** – market mood, futures/VIX/yields/oil, the next two weeks of events, and (optional, AI with web search) what moved markets, what Washington and the Fed are doing including rate-hike odds, what the pros say, scenarios and a lesson of the day.
2. **Your stocks** – portfolio totals; your largest holdings in depth (rules status, revenue growth, margin, P/E, analyst ratings and targets, levels, earnings); leveraged ETFs explained through the company behind them with the decay math ("SNXX needs +101% – SanDisk +42% in a straight line, ~+60% over 3 months of normal swings"); your option positions (value, days left, time decay per day, the price that beats selling today and the price that gets your cost back); and per-stock news with bull and bear cases (AI).

> Educational tool, not financial advice. Results are on the underlying stock; options add strike, expiry and volatility risk.

---

## How a signal is decided

Gates decide the direction. They must **all** pass:

| Gate | CALL | PUT |
|---|---|---|
| EMA stack | 8 > 21 > 34 > 55 > 89 | 8 < 21 < 34 < 55 < 89 |
| Trend | ADX(13) ≥ 20 **and** +DI > −DI | ADX(13) ≥ 20 **and** −DI > +DI |
| Earnings | none within 14 days, and the date must be verifiable (`EARNINGS_UNKNOWN=block`) | same |
| Macro events | no CPI / jobs / FOMC / bellwether earnings today or next session | same |
| Market regime | not DEFENSIVE (see below) | – |
| Sector | sector ETF not extended (RSI > 75 or > 20% above 50-day) and not breaking down (3 closes under a falling 21 EMA) | – |

**Entry triggers.** Both are needed for a SIGNAL; with only one, the stock is reported as a SETUP:
- price within 2% of the 21 EMA (a pullback in an uptrend, or a rally into it in a downtrend)
- slow stochastic (8,3,3) %K ≤ 40 for a CALL, ≥ 60 for a PUT

**Confidence** comes from five quality checks: price vs the 200 EMA, the 20/40/200 EMA order, the 200 EMA slope, RSI in range, and distance from the 52-week high (low for puts). If the earnings date can't be verified, confidence drops one level.

**Trade plan.** The stop sits past the 10-day swing low/high, clamped to 1–3 ATR so it is always on the correct side of the entry. Targets are 1R, 2R and 3R, with a time stop after 20 trading days. If earnings land inside that hold, the plan says **exit by the close the session before** (no holding options through an earnings print). Position size comes from `ACCOUNT_SIZE × RISK_PER_TRADE_PCT`.

**When signals are checked.** By default (`CONFIRM_ON_CLOSE=true`) the bot scans once per trading day, 10 minutes after the close (NYSE holidays and early closes included), on the completed daily candle. You act at the next open. This matches the backtest exactly. Setting `CONFIRM_ON_CLOSE=false` adds intraday scans on the unfinished candle; they come earlier but are noisier, and the backtest doesn't model them. An alert fires when a stock *becomes* a signal, not every day it stays one.

### Market regime score (0–5)
One point each:
1. SPY closes below its 50-day EMA
2. VIX is above 25, or up more than 30% in 5 days
3. VIX is above VIX3M (term structure inverted)
4. The high-yield credit spread (FRED `BAMLH0A0HYM2`) is up more than 0.40 pts in 20 days
5. The 10-yr yield is up more than 0.30 pts in 20 days, or Brent is up more than 20%

What the score does:
- **0–1, NORMAL:** full size.
- **2, CAUTION:** half size; CALLs need HIGH confidence.
- **3–5, DEFENSIVE:** no new CALLs.

Credit spreads and the yield/oil check tend to move *before* sell-offs. VIX mostly confirms them.

### Event calendar
`events.yaml` lists CPI, jobs and FOMC dates plus deadlines you add yourself, such as tariff or truce dates. Earnings dates for the sector bellwethers in that file (NVDA, TSM, AVGO, …) are looked up automatically, and their veto applies only to stocks in that sector. **Keep the file current.**

---

## Setup

### 1. WhatsApp (CallMeBot, free for personal use)
1. Save the CallMeBot WhatsApp number from [callmebot.com](https://www.callmebot.com) in your contacts. The number changes occasionally, so take it from the site.
2. Send it: `I allow callmebot to send me messages`
3. It replies with your API key. Set `WHATSAPP_PHONE=+1…` and `CALLMEBOT_API_KEY=…`.

Twilio is also supported (`WHATSAPP_PROVIDER=twilio`). WhatsApp only allows free-form business messages within 24 h of your last message to that number, so the daily brief needs you to reply now and then, or an approved template.

### 2. Telegram (optional, needed for the interactive bot)
Create a bot with @BotFather and set `TELEGRAM_BOT_TOKEN`. Send `/start` to it to see your chat id, then set `TELEGRAM_CHAT_ID` and `ALLOWED_CHAT_IDS`. The interactive bot is deny-by-default: until your chat id is in `ALLOWED_CHAT_IDS` it only answers `/start`, so strangers can't see your portfolio or spend your Claude credits.

### 3. AI section of the brief (optional)
Set `ANTHROPIC_API_KEY` (from console.anthropic.com). Each brief makes one Claude call with up to `BRIEF_MAX_SEARCHES` (default 8) web searches, which costs roughly $0.15–0.30 with the default `claude-sonnet-5-5`. Without a key the brief still has everything except the news write-up, the per-stock news and the lesson.

### 4. Your stocks and options
`PORTFOLIO=NVDA:20@95,MSFT:5@410,TSLA` sets ticker, shares and average cost; shares and cost are optional. `WATCHLIST=…` holds the extra symbols to scan.

`OPTIONS=APLD:2027-01-15:25C:20@6.897` lists option positions as underlying, expiry, strike with C or P, contracts, and the per-share price you paid (the number Robinhood shows). Quotes come from Yahoo's option chain; delta, time decay and odds use Black-Scholes with the quoted implied volatility. Each position shows two break-even prices: **beats selling today** (strike + today's price – what holding from here has to clear) and **your cost back** (strike + what you paid).

Leveraged and inverse ETFs (`SNXX`→SanDisk, `APLX`→Applied Digital, `TQQQ`, …; add your own with `LEVERAGED_ETFS=ETF:UNDERLYING:FACTOR`) use the company's earnings date for the blackout and its sector for the sector guard. Without this, a 2x single-stock fund has no earnings date of its own and would never be blocked before the company reports.

All options are documented in [`.env.example`](.env.example).

---

## Run

```bash
pip install -r requirements.txt
cp .env.example .env              # fill in your keys

python stock_tracker.py --test    # send a test message to every channel
python stock_tracker.py --brief   # send today's brief now  (--dry-run to just print it)
python stock_tracker.py --once    # one scan now
python stock_tracker.py           # run forever: brief at BRIEF_TIME + a scan after each close

python -m stockbot.bot            # interactive Telegram bot: /analyze NVDA, /market, /brief
streamlit run app.py              # dashboard (pip install -r requirements-app.txt)
```

### Deploy on Railway
The repo is ready as is: `railway.json` runs `python stock_tracker.py`.
1. New project → Deploy from GitHub → this repo.
2. Add your variables (at least the WhatsApp ones and `PORTFOLIO`) under **Variables**.
3. Optional: add a **Volume** mounted at `/app/data` and set `DATA_DIR=/app/data`, so alert history survives redeploys.
4. To run the interactive Telegram bot as well, add a second service with start command `python -m stockbot.bot`.

On a crash the process exits with code 1, so Railway restarts it, and you also get a WhatsApp/Telegram message about it. Without a volume, alert history resets on every deploy, so a signal that is still live can be re-sent once after a redeploy. The brief only catches up within 3 hours of `BRIEF_TIME`, so a late-night restart won't send a "morning" brief.

---

## Backtest

```bash
python -m stockbot.backtest --period 10y --compare          # effect of each filter layer
python -m stockbot.backtest --symbols NVDA AMD --csv trades.csv
```
The backtest replays the live rules on completed daily bars with no look-ahead, using the same filters as the alerts (`MIN_CONFIDENCE`, and HIGH+ for CALLs in a CAUTION regime).
- The stop and target are anchored to the signal close, exactly like the alert. Entry is at the next open, and trades that gap through either level are skipped.
- The stop is checked before the target, and later gaps fill at the open.
- Positions exit the session before earnings.
- Not modelled: the CPI/jobs/FOMC veto in the past, FRED's HY spread before ~2023, intraday mode, and survivorship bias. It reports win rate, average R, profit factor, max drawdown in R, splits by direction, confidence and year, and the 10-day move after signals compared with any random day. Run it on your own symbols before trusting the filters.

---

## Tests
```bash
pip install -r requirements-dev.txt
pytest -q
```
CI runs the suite on every push. All tests use synthetic data; none touch the network.

## Layout
```
stock_tracker.py      entry point (Railway)
app.py                Streamlit dashboard
events.yaml           macro event calendar + sector bellwethers
stockbot/
  indicators.py       EMA, RSI, slow stochastic, ATR, ADX/DI (Wilder)
  signals.py          gates → triggers → confidence (vectorized; shared with the backtest)
  risk.py             stop / targets / size
  regime.py           market regime score
  events.py           event veto
  sector.py           sector ETF guard
  levels.py           support / resistance from swing pivots
  data.py             batched Yahoo download, earnings dates, FRED, news
  scanner.py          builds the shared context and evaluates symbols
  brief.py            morning brief: news message + stocks message (+ optional Claude/web search)
  leverage.py         leveraged-ETF map and decay / recovery math
  options.py          option positions: quotes, Black-Scholes delta/decay, break-evens
  report.py           message formatting (WhatsApp / Telegram HTML / Discord / plain)
  alerts.py           delivery channels
  tracker.py          scheduler, alert de-duplication, CLI
  bot.py              interactive Telegram bot
  backtest.py         backtest CLI
tests/                pytest suite
```
