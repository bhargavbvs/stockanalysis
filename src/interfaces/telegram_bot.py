"""
Telegram Bot for Stock Trend Analyzer

This bot allows you to analyze stocks directly from Telegram.
Simply send a stock symbol and get instant analysis!

Commands:
/start - Start the bot
/help - Get help
/analyze SYMBOL - Analyze a stock (e.g., /analyze AAPL)
Just send a stock symbol directly (e.g., AAPL)
"""

import logging
import sys
from pathlib import Path

# Add parent directories to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'core'))
sys.path.insert(0, str(Path(__file__).parent.parent / 'analysis'))

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from stock_analyzer import StockAnalyzer

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot token
BOT_TOKEN = "8438836269:AAEyOqpzow71w3QbzsNVNrxWQYdYWUdJ2qs"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /start is issued."""
    user = update.effective_user
    welcome_message = f"""
👋 Hi {user.first_name}! Welcome to the **Stock Trend Analyzer Bot**!

📈 I can help you analyze stocks and provide OPTIONS TRADING recommendations:
• CALL OPTIONS for bullish trends
• PUT OPTIONS for bearish trends
• Technical analysis with EMAs, RSI, Stochastic, ADX

🔍 **How to use:**
Just send me a stock symbol like: `AAPL` or `TSLA`
Or use: `/analyze AAPL`

📊 **I'll tell you:**
📞 BUY CALL OPTIONS (bullish signals)
📉 BUY PUT OPTIONS (bearish signals)
🚫 NO TRADE (mixed signals)

Try it now! Send me a stock symbol 🚀
"""
    await update.message.reply_text(welcome_message, parse_mode='Markdown')


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /help is issued."""
    help_text = """
📖 **How to Use the Stock Analyzer Bot**

**Commands:**
/start - Start the bot
/help - Show this help message
/analyze SYMBOL - Analyze a specific stock

**Quick Analysis:**
Just send a stock symbol directly:
• `AAPL` - Analyze Apple
• `TSLA` - Analyze Tesla
• `GOOGL` - Analyze Google

**Understanding Results:**

📞 **BUY CALL OPTIONS**
Bullish signals - All criteria met for uptrend!

📉 **BUY PUT OPTIONS**
Bearish signals - All criteria met for downtrend!

⏳ **WAIT FOR ENTRY**
Structure forming but missing entry signals

🚫 **NO TRADE**
Mixed signals - stay on sidelines

**Bullish Criteria:**
1. EMAs stacked bullishly (8>21>34>55>89)
2. Price pulled back to 21 EMA (within 2%)
3. Stochastic %K ≤ 40
4. ADX ≥ 20 (strong trend)
5. No earnings in next 2 weeks

**Bearish Criteria:**
1. EMAs stacked bearishly (8<21<34<55<89)
2. Price below 21 EMA (resistance)
3. Stochastic %K ≥ 60
4. ADX ≥ 20 (strong trend)
5. No earnings in next 2 weeks

⚠️ **Disclaimer:** This is for educational purposes only, not financial advice!
"""
    await update.message.reply_text(help_text, parse_mode='Markdown')


async def analyze_stock(update: Update, context: ContextTypes.DEFAULT_TYPE, symbol: str):
    """Analyze a stock and send results."""
    # Send "analyzing" message
    status_msg = await update.message.reply_text(f"🔍 Analyzing {symbol.upper()}... Please wait...")
    
    try:
        # Create analyzer and get trend
        analyzer = StockAnalyzer(symbol)
        trend, reasons, additional_checks, analysis = analyzer.identify_trend()
        
        if analysis is None:
            await status_msg.edit_text(f"❌ Unable to analyze {symbol.upper()}. Please check the symbol and try again.")
            return
        
        # Format the response
        response = format_analysis_message(analysis, trend, reasons)
        
        # Create inline keyboard for quick actions
        keyboard = [
            [
                InlineKeyboardButton("📊 View Chart", url=f"https://finance.yahoo.com/chart/{symbol.upper()}"),
                InlineKeyboardButton("📰 News", url=f"https://finance.yahoo.com/quote/{symbol.upper()}/news")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Send the analysis
        await status_msg.edit_text(response, parse_mode='Markdown', reply_markup=reply_markup)
        
    except Exception as e:
        logger.error(f"Error analyzing {symbol}: {e}")
        await status_msg.edit_text(f"❌ Error analyzing {symbol.upper()}: {str(e)}")


def format_analysis_message(analysis, trend, reasons):
    """Format the analysis results into a Telegram message."""
    
    # Get options recommendation
    options_rec = analysis.get('options_recommendation', {})
    strategy = options_rec.get('strategy', 'NO TRADE')
    
    # Determine emoji and status based on trend
    if "STRONG BULLISH" in trend or "CALL OPTIONS SIGNAL" in trend:
        status_emoji = "📞"
        status_text = "**BUY CALL OPTIONS**"
        status_note = f"🎯 {options_rec.get('confidence', 'HIGH')} CONFIDENCE - {options_rec.get('reasoning', 'Strong bullish signal')}"
    elif "BULLISH" in trend and "CALL" in trend:
        status_emoji = "📈"
        status_text = "**CONSIDER CALL OPTIONS**"
        status_note = f"⚠️ {options_rec.get('confidence', 'MODERATE')} confidence - {options_rec.get('reasoning', 'Bullish signals present')}"
    elif "STRONG BEARISH" in trend or "PUT OPTIONS SIGNAL" in trend:
        status_emoji = "📉"
        status_text = "**BUY PUT OPTIONS**"
        status_note = f"🎯 {options_rec.get('confidence', 'HIGH')} CONFIDENCE - {options_rec.get('reasoning', 'Strong bearish signal')}"
    elif "BEARISH" in trend and "PUT" in trend:
        status_emoji = "📊"
        status_text = "**CONSIDER PUT OPTIONS**"
        status_note = f"⚠️ {options_rec.get('confidence', 'MODERATE')} confidence - {options_rec.get('reasoning', 'Bearish signals present')}"
    elif "WAIT" in trend:
        status_emoji = "⏳"
        status_text = "**WAIT FOR ENTRY**"
        status_note = "⌛ Bullish structure but missing entry signals - Don't chase!"
    elif "MONITOR" in trend:
        status_emoji = "👁️"
        status_text = "**MONITOR FOR ENTRY**"
        status_note = "📊 Bearish structure forming - Wait for confirmation"
    elif "NO CLEAR TREND" in trend or "NO OPTIONS TRADE" in trend:
        status_emoji = "🚫"
        status_text = "**NO TRADE**"
        status_note = "⚪ Mixed signals - Stay on sidelines"
    else:
        status_emoji = "⚪"
        status_text = "**NEUTRAL/MIXED SIGNALS**"
        status_note = "ℹ️ No clear trend identified"
    
    # Build message
    message = f"""
📈 **{analysis['symbol']} - Stock Analysis Report**
━━━━━━━━━━━━━━━━━━━━━━━━

💰 **Current Price:** ${analysis['current_price']}

📊 **EMA Stack:**
  8-Day:   ${analysis['ema_8']}
  21-Day:  ${analysis['ema_21']}
  34-Day:  ${analysis['ema_34']}
  55-Day:  ${analysis['ema_55']}
  89-Day:  ${analysis['ema_89']}

📈 **Technical Indicators:**
  RSI (14):          {analysis['rsi']}
  Stochastic %K (8): {analysis['stoch_k']}
  ADX (13):          {analysis['adx']}

━━━━━━━━━━━━━━━━━━━━━━━━
{status_emoji} {status_text}
{status_note}
━━━━━━━━━━━━━━━━━━━━━━━━

📋 **Options Strategy:**
  Strategy:   {options_rec.get('strategy', 'N/A')}
  Confidence: {options_rec.get('confidence', 'N/A')}
  Entry:      {options_rec.get('entry', 'N/A')}
  Risk:       {options_rec.get('risk', 'N/A')}

🔍 **Criteria Check:**
"""
    
    # Determine if showing bullish or bearish criteria
    is_bearish_signal = "BEARISH" in trend or "PUT" in trend
    is_bullish_signal = "BULLISH" in trend or "CALL" in trend
    
    # Find where bearish criteria starts in reasons (if present)
    bearish_section_start = -1
    for i, reason in enumerate(reasons):
        if "BEARISH CRITERIA" in reason:
            bearish_section_start = i
            break
    
    # Add appropriate criteria based on trend
    if is_bearish_signal and bearish_section_start >= 0:
        # Show bearish criteria
        message += "🔻 **BEARISH CRITERIA:**\n"
        criteria_count = 0
        for i in range(bearish_section_start + 1, len(reasons)):
            reason = reasons[i]
            # Stop if we hit the scoring summary
            if "📊 Criteria Score:" in reason:
                break
            # Only show criteria checks (lines starting with ✓ or ✗)
            if reason.strip().startswith(('✓', '✗')):
                message += f"{reason}\n"
                criteria_count += 1
                if criteria_count >= 5:  # Show only 5 bearish criteria
                    break
    elif is_bullish_signal:
        # Show bullish criteria
        message += "📈 **BULLISH CRITERIA:**\n"
        criteria_count = 0
        for reason in reasons:
            # Stop if we hit bearish section or scoring
            if "BEARISH CRITERIA" in reason or "📊 Criteria Score:" in reason:
                break
            # Only show criteria checks (lines starting with ✓ or ✗)
            if reason.strip().startswith(('✓', '✗')):
                message += f"{reason}\n"
                criteria_count += 1
                if criteria_count >= 5:  # Show only 5 bullish criteria
                    break
    else:
        # For neutral/wait signals, show first 5 criteria
        message += "�� **CRITERIA ANALYSIS:**\n"
        criteria_count = 0
        for reason in reasons:
            if "📊 Criteria Score:" in reason:
                break
            if reason.strip().startswith(('✓', '✗')):
                message += f"{reason}\n"
                criteria_count += 1
                if criteria_count >= 5:
                    break
    
    # Add support/resistance levels
    sr_data = analysis.get('support_resistance')
    if sr_data and 'current_price' in sr_data:
        message += "\n━━━━━━━━━━━━━━━━━━━━━━━━"
        message += "\n🎯 **SUPPORT & RESISTANCE LEVELS:**\n"
        message += f"  Current: ${sr_data['current_price']}\n"
        message += f"  Pivot:   ${sr_data['pivot_point']}\n\n"
        
        message += "🔺 **Resistance Levels:**\n"
        res_levels = sr_data.get('resistance_levels', [])
        res_distances = sr_data.get('resistance_distances', [])
        for i, (level, dist) in enumerate(zip(res_levels[:3], res_distances[:3])):
            message += f"  R{i+1}: ${level} ({dist})\n"
        
        message += "\n🔻 **Support Levels:**\n"
        sup_levels = sr_data.get('support_levels', [])
        sup_distances = sr_data.get('support_distances', [])
        for i, (level, dist) in enumerate(zip(sup_levels[:3], sup_distances[:3])):
            message += f"  S{i+1}: ${level} ({dist})\n"
        
        # Add 52-week high/low if available
        if '52_week_high' in sr_data:
            message += f"\n📊 **52-Week Range:**\n"
            message += f"  High: ${sr_data['52_week_high']}\n"
            message += f"  Low:  ${sr_data['52_week_low']}\n"
    
    # Add risk management section
    risk_mgmt = analysis.get('risk_management')
    if risk_mgmt and 'stop_loss' in risk_mgmt:
        message += "\n━━━━━━━━━━━━━━━━━━━━━━━━"
        message += "\n🛡️ **RISK MANAGEMENT:**\n"
        
        # Entry zone
        entry = risk_mgmt.get('entry_zone', {})
        message += f"\n📍 **Entry Zone:**\n"
        message += f"  Ideal: {entry.get('ideal_entry', 'N/A')}\n"
        message += f"  Max:   {entry.get('max_entry', 'N/A')}\n"
        
        # Stop loss
        stop = risk_mgmt.get('stop_loss', {})
        message += f"\n🛑 **Stop Loss:**\n"
        message += f"  Stock: ${stop.get('stock_price_stop', 'N/A')} ({stop.get('stop_distance', 'N/A')})\n"
        message += f"  Option: {stop.get('option_stop', 'N/A')}\n"
        message += f"  Why: {stop.get('stop_reason', 'N/A')}\n"
        
        # Take profit targets
        targets = risk_mgmt.get('take_profit_targets', [])
        if targets:
            message += f"\n🎯 **Take Profit Targets:**\n"
            for target in targets[:3]:
                message += f"  T{target['level']}: ${target['price']} ({target['distance']}) - {target['action']}\n"
                message += f"       Expected gain: {target['option_gain']}\n"
        
        # Trailing stops
        trailing = risk_mgmt.get('trailing_stops', [])
        if trailing:
            message += f"\n📈 **Trailing Stop Rules:**\n"
            for i, rule in enumerate(trailing[:3], 1):
                message += f"  {i}. When {rule['trigger']}:\n"
                message += f"     → {rule['action']}\n"
        
        # Risk/Reward
        rr = risk_mgmt.get('risk_reward_ratio', 'N/A')
        message += f"\n⚖️ **Risk/Reward:** {rr}\n"
    
    # Add insights
    message += "\n━━━━━━━━━━━━━━━━━━━━━━━━"
    message += "\n💡 **Insights:**\n"
    if analysis.get('is_bullish_stacked'):
        message += "• ✅ Perfect bullish EMA alignment\n"
    if analysis.get('is_bearish_stacked'):
        message += "• ⚠️ Bearish EMA alignment - downtrend structure\n"
    if analysis['rsi'] > 70:
        message += "• ⚠️ RSI indicates overbought\n"
    elif analysis['rsi'] < 30:
        message += "• 💡 RSI indicates oversold\n"
    if analysis['adx'] and analysis['adx'] >= 25:
        message += f"• ✅ Strong trend (ADX: {analysis['adx']})\n"
    
    # Add nearest S/R insight
    if sr_data and 'nearest_resistance' in sr_data and 'nearest_support' in sr_data:
        message += f"• 🎯 Nearest resistance: ${sr_data['nearest_resistance']}\n"
        message += f"• 🛡️ Nearest support: ${sr_data['nearest_support']}\n"
    
    message += f"\n⏰ *As of {analysis['date']}*"
    message += "\n\n⚠️ *Not financial advice - for educational purposes only*"
    
    return message


async def analyze_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /analyze command."""
    if not context.args:
        await update.message.reply_text("Please provide a stock symbol.\nExample: `/analyze AAPL`", parse_mode='Markdown')
        return
    
    symbol = context.args[0].upper()
    await analyze_stock(update, context, symbol)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle regular messages (stock symbols)."""
    text = update.message.text.strip().upper()
    
    # Check if it looks like a stock symbol (1-5 letters)
    if len(text) <= 5 and text.isalpha():
        await analyze_stock(update, context, text)
    else:
        await update.message.reply_text(
            "Please send a valid stock symbol (e.g., AAPL, TSLA, GOOGL)\n"
            "Or use `/help` for more information.",
            parse_mode='Markdown'
        )


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button callbacks."""
    query = update.callback_query
    await query.answer()


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Log errors."""
    logger.error(f"Update {update} caused error {context.error}")


def main():
    """Start the bot."""
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("\n" + "="*60)
        print("⚠️  ERROR: Bot token not set!")
        print("="*60)
        print("\nPlease follow these steps:")
        print("1. Open Telegram and search for @BotFather")
        print("2. Send /newbot and follow instructions")
        print("3. Copy the token you receive")
        print("4. Open telegram_bot.py and replace YOUR_BOT_TOKEN_HERE with your token")
        print("5. Run this script again")
        print("\n" + "="*60)
        return
    
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Register handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("analyze", analyze_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Register error handler
    application.add_error_handler(error_handler)
    
    # Start the bot
    print("\n" + "="*60)
    print("🤖 Stock Analyzer Telegram Bot Started!")
    print("="*60)
    print("\n✅ Bot is running... Send it stock symbols to analyze!")
    print("Press Ctrl+C to stop\n")
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
