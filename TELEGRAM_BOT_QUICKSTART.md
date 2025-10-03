# 🤖 Telegram Bot Quick Start Guide

## ✅ Your Bot is Already Configured!

Your Telegram bot token is already set up in the code. Here's how to run it:

## 🚀 Step 1: Activate Virtual Environment & Run the Bot

Open your terminal and run:

```bash
cd /Users/bhargavbvs/Desktop/stockanalysis
source venv/bin/activate
python3 src/interfaces/telegram_bot.py
```

You should see:
```
🤖 Stock Analyzer Telegram Bot Started!
✅ Bot is running... Send it stock symbols to analyze!
```

## 📱 Step 2: Find Your Bot on Telegram

1. Open Telegram app (on your phone or desktop)
2. Search for your bot by username (the one associated with your token)
3. Start a chat with your bot
4. Send `/start` to begin

## 💬 Step 3: Use Your Bot!

### Available Commands:

| Command | Description | Example |
|---------|-------------|---------|
| `/start` | Welcome message & instructions | `/start` |
| `/help` | Detailed help guide | `/help` |
| `/analyze SYMBOL` | Analyze a specific stock | `/analyze AAPL` |
| **Direct symbol** | Just type the stock symbol | `TSLA` |

### Example Usage:

```
You: /start
Bot: 👋 Welcome message with instructions...

You: AAPL
Bot: 📈 AAPL - Stock Analysis Report
     💰 Current Price: $225.67
     📊 Trend: UPTREND - BUY SIGNAL
     ✅ All 5 criteria met!

You: NVDA
Bot: 📈 NVDA - Stock Analysis Report
     💰 Current Price: $120.34
     📊 Trend: UPTREND - WAIT FOR PULLBACK
     ⏳ Stock is in uptrend but wait for better entry
```

## 🔍 What the Bot Analyzes

### Bullish Criteria (5 Core):
- ✅ EMA stacking (8>21>34>55>89)
- ✅ Pullback to 21 EMA
- ✅ Stochastic <= 40
- ✅ ADX >= 20
- ✅ No earnings in 2 weeks

### Bearish Criteria (5 Core):
- 🔻 EMA stacking bearish (8<21<34<55<89)
- 🔻 Price under 21 EMA
- 🔻 Stochastic >= 60
- 🔻 ADX >= 20
- 🔻 No earnings in 2 weeks

### Response Types:
- **🎯 STRONG BULLISH - BUY SIGNAL**: All criteria met, excellent entry!
- **✅ UPTREND - BUY SIGNAL**: All 5 core bullish criteria met
- **⏳ UPTREND - WAIT FOR PULLBACK**: In uptrend but timing not optimal
- **📈 UPTREND - DEVELOPING**: Bullish structure forming
- **🔻 STRONG BEARISH - SHORT SIGNAL**: All 5 bearish criteria met
- **📉 DOWNTREND - SHORT ON RALLY**: Downtrend, wait for rally to 21 EMA
- **⏳ DOWNTREND - WAIT FOR RALLY**: Downtrend but wait for bounce
- **⚪ NEUTRAL**: No clear trend

## 🛠️ Running the Bot in Background (Keep it Running 24/7)

### Option 1: Using `screen` (Recommended for Mac/Linux)

```bash
# Create a new screen session
screen -S telegram_bot

# Activate venv and run bot
cd /Users/bhargavbvs/Desktop/stockanalysis
source venv/bin/activate
python3 src/interfaces/telegram_bot.py

# Detach from screen: Press Ctrl+A then D

# To reattach later:
screen -r telegram_bot

# To list all screens:
screen -ls

# To kill the screen:
screen -X -S telegram_bot quit
```

### Option 2: Using `nohup` (Simple background process)

```bash
cd /Users/bhargavbvs/Desktop/stockanalysis
source venv/bin/activate
nohup python3 src/interfaces/telegram_bot.py > telegram_bot.log 2>&1 &

# To stop it later, find the process ID:
ps aux | grep telegram_bot.py
kill <PID>
```

### Option 3: Using `tmux` (Alternative to screen)

```bash
# Install tmux if not installed
brew install tmux

# Create new session
tmux new -s telegram_bot

# Run bot
cd /Users/bhargavbvs/Desktop/stockanalysis
source venv/bin/activate
python3 src/interfaces/telegram_bot.py

# Detach: Press Ctrl+B then D
# Reattach: tmux attach -t telegram_bot
```

## 🔧 Troubleshooting

### Issue: Bot doesn't respond
**Solution:**
1. Check if the script is still running in terminal
2. Look for error messages in the terminal output
3. Verify you sent `/start` first to initialize the bot
4. Try restarting the bot script

### Issue: "Module not found" error
**Solution:**
```bash
cd /Users/bhargavbvs/Desktop/stockanalysis
source venv/bin/activate
pip install python-telegram-bot
```

### Issue: Bot can't find StockAnalyzer
**Solution:** Make sure you're running from the correct directory:
```bash
cd /Users/bhargavbvs/Desktop/stockanalysis
python3 src/interfaces/telegram_bot.py
```

### Issue: "No data found for symbol"
**Solution:**
- Check if the stock symbol is correct (use uppercase)
- Some international stocks need suffixes (e.g., `BP.L` for London)
- Try well-known stocks first: AAPL, MSFT, GOOGL, TSLA, NVDA

## 📊 Advanced Usage

### Analyze Multiple Stocks Quickly
```
You: AAPL
Bot: [Analysis for AAPL]

You: MSFT
Bot: [Analysis for MSFT]

You: GOOGL
Bot: [Analysis for GOOGL]
```

### Check Both Bullish and Bearish Opportunities
The bot now analyzes BOTH directions:
- If EMAs stacked bullishly → Shows bullish signals
- If EMAs stacked bearishly → Shows bearish/short signals

## 🔐 Security Tips

- ⚠️ Your bot token is already in the code - keep it private!
- Don't share your bot token with anyone
- Don't commit the token to public repositories
- Consider using environment variables for production:
  ```python
  import os
  BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', 'your-token-here')
  ```

## 📈 Monitoring Your Bot

Check the terminal output for:
- ✅ Successful analyses
- ❌ Errors or failed data fetches
- 📊 User requests

Example output:
```
2025-10-02 10:15:23 - INFO - User @username analyzed AAPL
2025-10-02 10:16:45 - INFO - User @username analyzed TSLA
✓ Successfully fetched data for TSLA
```

## 🚀 Next Steps

Once your bot is running:
1. ✅ Test it with various stock symbols
2. 📱 Share the bot with friends (optional)
3. 🔄 Keep the bot running in background with `screen` or `tmux`
4. 📊 Monitor the terminal for any issues

## 📞 Quick Reference

**Start Bot:**
```bash
cd /Users/bhargavbvs/Desktop/stockanalysis && source venv/bin/activate && python3 src/interfaces/telegram_bot.py
```

**Start Bot in Background:**
```bash
cd /Users/bhargavbvs/Desktop/stockanalysis && source venv/bin/activate && screen -dmS telegram_bot python3 src/interfaces/telegram_bot.py
```

**Check if Bot is Running:**
```bash
ps aux | grep telegram_bot
```

**View Logs (if using screen):**
```bash
screen -r telegram_bot
```

---

**Happy Trading! 📈🤖**
