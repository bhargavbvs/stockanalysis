"""Interactive Telegram bot.

    /analyze NVDA   (or just send "NVDA")   full check of one stock
    /market                                 market regime score right now
    /brief                                  today's morning brief on demand
    /help

The token comes from TELEGRAM_BOT_TOKEN. Set ALLOWED_CHAT_IDS to your chat id
so strangers who find the bot can't use your API quota. (CallMeBot WhatsApp is
send-only, so interactive questions go through Telegram.)
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

    def context(self, symbols: list[str]) -> scanner.Context:
        if self.ctx is None or time.time() - self.ctx_time > CTX_TTL:
            self.ctx = scanner.build_context(self.s, symbols)
            self.ctx_time = time.time()
        else:
            scanner.ensure_symbols(self.ctx, self.s, symbols)
        return self.ctx


def build_app(settings: config.Settings):
    from telegram import Update
    from telegram.constants import ParseMode
    from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

    state = BotState(settings)

    def allowed(update: Update) -> bool:
        return not settings.allowed_chat_ids or str(update.effective_chat.id) in settings.allowed_chat_ids

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
            await msg.edit_text(f"❌ Could not analyze {symbol}: {exc}")

    async def start(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        if not allowed(update):
            return
        await reply(update, f"👋 Your chat id is `{update.effective_chat.id}`.\n\n" + HELP)

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
        msg = await update.effective_message.reply_text("☕ Building today's brief (about a minute)…")
        text = await asyncio.to_thread(brief_mod.build, settings)
        await msg.delete()
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
        log.error("update %s caused %s", update, context.error)

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
    settings = config.load()
    if not settings.telegram_token:
        print("Set TELEGRAM_BOT_TOKEN (from @BotFather) in your environment or .env file.")
        return 1
    if not settings.allowed_chat_ids:
        log.warning("ALLOWED_CHAT_IDS is not set – anyone who finds the bot can use it")
    build_app(settings).run_polling()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
