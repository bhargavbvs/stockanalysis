"""Interactive Telegram bot.

    /analyze NVDA   (or just send "NVDA")   full check of one stock
    /market                                 market regime score right now
    /brief                                  today's morning brief on demand
    /help

The token comes from TELEGRAM_BOT_TOKEN. Access is deny-by-default: until
ALLOWED_CHAT_IDS lists your chat id, the bot only answers /start (which tells
you that id), so strangers can't read your portfolio or spend your Claude
credits. (CallMeBot WhatsApp is send-only, so questions go through Telegram.)
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Optional

from . import brief as brief_mod, config, scanner
from .report import signal_message, split_message, to_telegram_html

log = logging.getLogger("stockbot.bot")
TICKER = re.compile(r"^\^?[A-Z][A-Z0-9.\-=]{0,9}$")
CTX_TTL = 600  # seconds
BRIEF_COOLDOWN = 600  # seconds between on-demand briefs

HELP = (
    "*Stock bot*\n"
    "Send a ticker (e.g. NVDA) or /analyze NVDA – trend, entry checks, plan, levels\n"
    "/market – market mood (regime score) right now\n"
    "/brief – today's morning brief\n\n"
    "Rules: EMA stack 8>21>34>55>89 + ADX trend, pullback to the 21 EMA with stochastic ≤ 40 "
    "(puts mirrored). Vetoes: earnings, CPI/jobs/FOMC, risky market regime, overheated sector.\n\n"
    "_Educational only – not financial advice._"
)


class BotState:
    def __init__(self, settings: config.Settings):
        self.s = settings
        self.ctx: Optional[scanner.Context] = None
        self.ctx_time = 0.0
        self.lock = asyncio.Lock()
        self.brief_lock = asyncio.Lock()
        self.last_brief = 0.0

    def context(self, symbols: list[str]) -> scanner.Context:
        if self.ctx is None or time.time() - self.ctx_time > CTX_TTL:
            self.ctx = scanner.build_context(self.s, symbols)
            self.ctx_time = time.time()
        else:
            scanner.ensure_symbols(self.ctx, self.s, symbols)
        return self.ctx


def is_allowed(settings: config.Settings, chat_id) -> bool:
    """Deny by default: only chats listed in ALLOWED_CHAT_IDS get answers."""
    return str(chat_id) in settings.allowed_chat_ids


def build_app(settings: config.Settings):
    from telegram import Update
    from telegram.constants import ParseMode
    from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

    state = BotState(settings)

    def allowed(update: Update) -> bool:
        return is_allowed(settings, update.effective_chat.id)

    async def reply(update: Update, text: str) -> None:
        for chunk in split_message(text, 3500):
            await update.effective_message.reply_text(
                to_telegram_html(chunk), parse_mode=ParseMode.HTML, disable_web_page_preview=True)

    async def analyze_symbol(update: Update, symbol: str) -> None:
        msg = await update.effective_message.reply_text(f"🔍 Checking {symbol}…")
        try:
            async with state.lock:
                sig = await asyncio.to_thread(
                    lambda: scanner.analyze(symbol, state.context([symbol]), settings, force_earnings=True))
            await msg.delete()
            if sig.status == "INSUFFICIENT_DATA" and sig.price is None:
                await reply(update, f"❌ No price data for *{symbol}* – check the ticker.")
            else:
                await reply(update, signal_message(sig))
        except Exception as exc:
            log.exception("analyze %s failed", symbol)
            await msg.edit_text(f"❌ Could not analyze {symbol} ({type(exc).__name__}).")

    async def start(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = update.effective_chat.id
        if not allowed(update):
            await reply(update, f"👋 Your chat id is {chat_id}. Add it to ALLOWED_CHAT_IDS to use this bot.")
            return
        await reply(update, f"👋 Your chat id is {chat_id}.\n\n" + HELP)

    async def help_cmd(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        if allowed(update):
            await reply(update, HELP)

    async def analyze_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not allowed(update):
            return
        if not context.args:
            await reply(update, "Usage: /analyze NVDA")
            return
        await analyze_symbol(update, context.args[0].upper())

    async def market_cmd(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        if not allowed(update):
            return
        async with state.lock:
            ctx = await asyncio.to_thread(state.context, [])
        r = ctx.regime
        lines = [f"*Market mood: {r.mode} ({r.score}/5)* – {brief_mod.MODE_LINE.get(r.mode, '')}"]
        lines += [f"{'⚠️' if c.on else '✅'} {c.detail}" for c in r.components]
        await reply(update, "\n".join(lines))

    async def brief_cmd(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        if not allowed(update):
            return
        wait = BRIEF_COOLDOWN - (time.time() - state.last_brief)
        if state.brief_lock.locked() or wait > 0:
            await reply(update, f"⏳ A brief was just built – try again in {max(1, int(wait // 60))} min.")
            return
        async with state.brief_lock:
            state.last_brief = time.time()
            msg = await update.effective_message.reply_text("☕ Building today's brief (about a minute)…")
            try:
                parts = await asyncio.to_thread(brief_mod.build_messages, settings)
            except Exception as exc:
                log.exception("brief failed")
                await msg.edit_text(f"❌ Brief failed ({type(exc).__name__}). Check the logs.")
                return
            await msg.delete()
            for text in parts:
                await reply(update, text)

    async def text_msg(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        if not allowed(update):
            return
        t = (update.effective_message.text or "").strip().upper().lstrip("$")
        if TICKER.match(t):
            await analyze_symbol(update, t)
        else:
            await reply(update, "Send a ticker like *NVDA*, or /help.")

    async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        log.error("update failed: %s", type(context.error).__name__)

    app = Application.builder().token(settings.telegram_token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("analyze", analyze_cmd))
    app.add_handler(CommandHandler("market", market_cmd))
    app.add_handler(CommandHandler("brief", brief_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_msg))
    app.add_error_handler(on_error)
    return app


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    for noisy in ("httpx", "httpcore", "telegram", "yfinance"):
        logging.getLogger(noisy).setLevel(logging.WARNING)  # httpx logs URLs containing the bot token
    settings = config.load()
    if not settings.telegram_token:
        print("Set TELEGRAM_BOT_TOKEN (from @BotFather) in your environment or .env file.")
        return 1
    if not settings.allowed_chat_ids:
        log.warning("ALLOWED_CHAT_IDS is empty – the bot only answers /start until you add your chat id")
    build_app(settings).run_polling()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
