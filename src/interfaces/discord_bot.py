"""
Discord Bot for Stock Trend Analyzer

This bot allows you to analyze stocks directly from Discord.
Simply mention the bot with a stock symbol and get instant analysis!

Commands:
!stock SYMBOL - Analyze a stock (e.g., !stock AAPL)
!help - Get help
"""

import discord
from discord.ext import commands
from stock_analyzer import StockAnalyzer
import logging

# Enable logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Bot token - You'll need to set this from Discord Developer Portal
BOT_TOKEN = "YOUR_DISCORD_BOT_TOKEN_HERE"

# Create bot with command prefix
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)


@bot.event
async def on_ready():
    """Called when bot is ready."""
    print(f'\n{"="*60}')
    print(f'🤖 Discord Bot Logged in as {bot.user.name}')
    print(f'{"="*60}')
    print(f'✅ Bot is ready! Use !stock SYMBOL to analyze')
    print(f'{"="*60}\n')


@bot.command(name='stock')
async def analyze_stock(ctx, symbol: str = None):
    """Analyze a stock symbol."""
    if symbol is None:
        await ctx.send("❌ Please provide a stock symbol.\nExample: `!stock AAPL`")
        return
    
    symbol = symbol.upper()
    
    # Send analyzing message
    status_msg = await ctx.send(f"🔍 Analyzing {symbol}... Please wait...")
    
    try:
        # Create analyzer and get trend
        analyzer = StockAnalyzer(symbol)
        trend, reasons, analysis = analyzer.identify_trend()
        
        if analysis is None:
            await status_msg.edit(content=f"❌ Unable to analyze {symbol}. Please check the symbol and try again.")
            return
        
        # Create embed
        embed = create_analysis_embed(analysis, trend, reasons)
        
        # Edit the status message with results
        await status_msg.edit(content=None, embed=embed)
        
    except Exception as e:
        logger.error(f"Error analyzing {symbol}: {e}")
        await status_msg.edit(content=f"❌ Error analyzing {symbol}: {str(e)}")


def create_analysis_embed(analysis, trend, reasons):
    """Create a Discord embed with analysis results."""
    
    # Determine color and status
    if trend == "UPTREND - BUY SIGNAL":
        color = discord.Color.green()
        status_emoji = "✅"
        status_text = "UPTREND WITH BUY SIGNAL"
        status_note = "🎯 All criteria met - This is a potential entry point!"
    elif trend == "UPTREND - WAIT FOR PULLBACK":
        color = discord.Color.gold()
        status_emoji = "⏳"
        status_text = "UPTREND - WAITING FOR PULLBACK"
        status_note = "📊 Stock is in uptrend but wait for better entry"
    elif trend == "DOWNTREND":
        color = discord.Color.red()
        status_emoji = "❌"
        status_text = "DOWNTREND"
        status_note = "⚠️ Avoid buying - Stock is in downtrend"
    else:
        color = discord.Color.light_grey()
        status_emoji = "⚪"
        status_text = "NEUTRAL/MIXED SIGNALS"
        status_note = "ℹ️ No clear trend identified"
    
    # Create embed
    embed = discord.Embed(
        title=f"📈 {analysis['symbol']} - Stock Analysis Report",
        description=f"**{status_emoji} {status_text}**\n{status_note}",
        color=color
    )
    
    # Add fields
    embed.add_field(
        name="💰 Current Price",
        value=f"${analysis['current_price']}",
        inline=True
    )
    
    embed.add_field(
        name="📊 ADX (Trend Strength)",
        value=f"{analysis['adx']}" if analysis['adx'] else "N/A",
        inline=True
    )
    
    embed.add_field(
        name="📈 RSI",
        value=f"{analysis['rsi']}",
        inline=True
    )
    
    # EMA Stack
    ema_stack = (
        f"8-Day:   ${analysis['ema_8']}\n"
        f"21-Day:  ${analysis['ema_21']}\n"
        f"34-Day:  ${analysis['ema_34']}\n"
        f"55-Day:  ${analysis['ema_55']}\n"
        f"89-Day:  ${analysis['ema_89']}"
    )
    embed.add_field(
        name="📊 EMA Stack",
        value=f"```{ema_stack}```",
        inline=False
    )
    
    # Technical Indicators
    indicators = (
        f"Stochastic %K: {analysis['stoch_k']}\n"
        f"Stochastic %D: {analysis['stoch_d']}"
    )
    embed.add_field(
        name="📈 Stochastic Oscillator",
        value=f"```{indicators}```",
        inline=False
    )
    
    # Criteria Check (first 5)
    criteria_text = "\n".join(reasons[:5])
    embed.add_field(
        name="🔍 Criteria Check",
        value=criteria_text,
        inline=False
    )
    
    # Insights
    insights = []
    if analysis['is_bullish_stacked']:
        insights.append("✅ Perfect bullish EMA alignment")
    if analysis['rsi'] > 70:
        insights.append("⚠️ RSI indicates overbought")
    elif analysis['rsi'] < 30:
        insights.append("💡 RSI indicates oversold")
    if analysis['adx'] and analysis['adx'] >= 25:
        insights.append(f"✅ Strong trend (ADX: {analysis['adx']})")
    
    if insights:
        embed.add_field(
            name="💡 Insights",
            value="\n".join(insights),
            inline=False
        )
    
    # Footer
    embed.set_footer(text=f"⚠️ Not financial advice | Data as of {analysis['date']}")
    
    # Add Yahoo Finance link
    embed.add_field(
        name="🔗 Links",
        value=f"[View Chart on Yahoo Finance](https://finance.yahoo.com/chart/{analysis['symbol']})",
        inline=False
    )
    
    return embed


@bot.command(name='help')
async def help_command(ctx):
    """Show help message."""
    embed = discord.Embed(
        title="📖 Stock Analyzer Bot - Help",
        description="Analyze stocks using advanced technical indicators!",
        color=discord.Color.blue()
    )
    
    embed.add_field(
        name="Commands",
        value=(
            "`!stock SYMBOL` - Analyze a stock\n"
            "`!help` - Show this help message"
        ),
        inline=False
    )
    
    embed.add_field(
        name="Examples",
        value=(
            "`!stock AAPL` - Analyze Apple\n"
            "`!stock TSLA` - Analyze Tesla\n"
            "`!stock GOOGL` - Analyze Google"
        ),
        inline=False
    )
    
    embed.add_field(
        name="Understanding Results",
        value=(
            "✅ **UPTREND - BUY SIGNAL**: All criteria met\n"
            "⏳ **UPTREND - WAIT**: Stock trending but wait for pullback\n"
            "❌ **DOWNTREND**: Avoid buying\n"
            "⚪ **NEUTRAL**: Mixed signals"
        ),
        inline=False
    )
    
    embed.add_field(
        name="The 5 Criteria",
        value=(
            "1. EMAs stacked bullishly (8>21>34>55>89)\n"
            "2. Price pulled back to 21 EMA (within 2%)\n"
            "3. Stochastic %K ≤ 40\n"
            "4. ADX ≥ 20 (strong trend)\n"
            "5. No earnings in next 2 weeks"
        ),
        inline=False
    )
    
    embed.set_footer(text="⚠️ This is for educational purposes only, not financial advice!")
    
    await ctx.send(embed=embed)


@bot.command(name='scan')
async def scan_stocks(ctx, *symbols):
    """Scan multiple stocks at once."""
    if not symbols:
        await ctx.send("❌ Please provide stock symbols.\nExample: `!scan AAPL TSLA GOOGL MSFT`")
        return
    
    if len(symbols) > 10:
        await ctx.send("❌ Maximum 10 stocks at a time please!")
        return
    
    status_msg = await ctx.send(f"🔍 Scanning {len(symbols)} stocks... Please wait...")
    
    results = []
    for symbol in symbols:
        try:
            analyzer = StockAnalyzer(symbol.upper())
            trend, _, analysis = analyzer.identify_trend()
            if analysis:
                results.append((symbol.upper(), trend, analysis))
        except Exception as e:
            logger.error(f"Error scanning {symbol}: {e}")
    
    # Create summary embed
    embed = discord.Embed(
        title=f"📊 Stock Scan Results ({len(results)} stocks)",
        color=discord.Color.blue()
    )
    
    buy_signals = []
    uptrends = []
    others = []
    
    for symbol, trend, analysis in results:
        info = f"${analysis['current_price']} | ADX: {analysis['adx']} | Stoch: {analysis['stoch_k']}"
        
        if trend == "UPTREND - BUY SIGNAL":
            buy_signals.append(f"✅ **{symbol}** - {info}")
        elif trend == "UPTREND - WAIT FOR PULLBACK":
            uptrends.append(f"⏳ **{symbol}** - {info}")
        else:
            others.append(f"⚪ **{symbol}** - {trend}")
    
    if buy_signals:
        embed.add_field(name="🎯 BUY SIGNALS", value="\n".join(buy_signals), inline=False)
    
    if uptrends:
        embed.add_field(name="📈 UPTRENDS (Wait for Pullback)", value="\n".join(uptrends), inline=False)
    
    if others:
        embed.add_field(name="📊 Other Signals", value="\n".join(others), inline=False)
    
    if not results:
        embed.description = "No valid results found. Please check the symbols."
    
    embed.set_footer(text="⚠️ Not financial advice - Use !stock SYMBOL for detailed analysis")
    
    await status_msg.edit(content=None, embed=embed)


def main():
    """Start the bot."""
    if BOT_TOKEN == "YOUR_DISCORD_BOT_TOKEN_HERE":
        print("\n" + "="*60)
        print("⚠️  ERROR: Bot token not set!")
        print("="*60)
        print("\nPlease follow these steps:")
        print("1. Go to https://discord.com/developers/applications")
        print("2. Click 'New Application' and give it a name")
        print("3. Go to 'Bot' section and click 'Add Bot'")
        print("4. Under TOKEN, click 'Reset Token' and copy it")
        print("5. Open discord_bot.py and replace YOUR_DISCORD_BOT_TOKEN_HERE")
        print("6. Go to OAuth2 > URL Generator")
        print("   - Select 'bot' scope")
        print("   - Select permissions: Send Messages, Embed Links, Read Messages")
        print("   - Copy the URL and open in browser to invite bot to your server")
        print("7. Run this script again")
        print("\n" + "="*60)
        return
    
    try:
        bot.run(BOT_TOKEN)
    except Exception as e:
        logger.error(f"Error starting bot: {e}")


if __name__ == '__main__':
    main()
