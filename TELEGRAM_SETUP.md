# Telegram Bot Setup Guide 🤖

This guide will help you set up your personal Telegram bot for stock analysis in just 5 minutes!

## Step 1: Create Your Telegram Bot

1. Open Telegram app on your phone or desktop
2. Search for **@BotFather** (this is Telegram's official bot for creating bots)
3. Start a chat with BotFather
4. Send the command: `/newbot`
5. BotFather will ask you to choose a name for your bot (e.g., "My Stock Analyzer")
6. Then choose a username for your bot (must end in 'bot', e.g., "mystockanalyzer_bot")
7. **BotFather will give you a TOKEN** - it looks like this:
   ```
   123456789:ABCdefGHIjklMNOpqrsTUVwxyz
   ```
8. **Copy this token** - you'll need it in the next step!

## Step 2: Configure the Bot

1. Open the file `telegram_bot.py` in your code editor
2. Find this line near the top:
   ```python
   BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
   ```
3. Replace `YOUR_BOT_TOKEN_HERE` with your actual token:
   ```python
   BOT_TOKEN = "123456789:ABCdefGHIjklMNOpqrsTUVwxyz"
   ```
4. Save the file

## Step 3: Install Dependencies

Make sure you're in the virtual environment and install the Telegram library:

```bash
cd "/Users/bhargavbvs/Desktop/stock analysis"
source venv/bin/activate
pip install python-telegram-bot
```

Or install all requirements:
```bash
pip install -r requirements.txt
```

## Step 4: Run Your Bot

```bash
source venv/bin/activate
python telegram_bot.py
```

You should see:
```
🤖 Stock Analyzer Telegram Bot Started!
✅ Bot is running... Send it stock symbols to analyze!
```

## Step 5: Use Your Bot!

1. Go back to Telegram
2. Search for your bot username (the one you created in Step 1)
3. Start a chat with your bot
4. Send `/start` to begin
5. Send any stock symbol like: `AAPL` or `TSLA`
6. Get instant analysis! 📊

## How to Use the Bot

### Commands:
- `/start` - Welcome message and instructions
- `/help` - Detailed help and explanation
- `/analyze AAPL` - Analyze a specific stock

### Quick Analysis:
Just send a stock symbol directly:
- `AAPL` → Analyze Apple
- `TSLA` → Analyze Tesla  
- `GOOGL` → Analyze Google
- `MSFT` → Analyze Microsoft
- `NVDA` → Analyze NVIDIA

### What You'll Get:
- 📊 Current price and EMA stack analysis
- 📈 Technical indicators (RSI, Stochastic, ADX)
- ✅ BUY SIGNAL if all criteria are met
- ⏳ UPTREND status if waiting for pullback
- ❌ DOWNTREND warning
- 🔗 Quick links to Yahoo Finance charts and news

## Example Conversation:

**You:** `/start`
**Bot:** *Welcome message with instructions*

**You:** `AAPL`
**Bot:** 
```
📈 AAPL - Stock Analysis Report
━━━━━━━━━━━━━━━━━━━━━━━━
💰 Current Price: $254.63
📊 EMA Stack:
  8-Day:   $251.99
  21-Day:  $244.14
  ...
⏳ UPTREND - WAITING FOR PULLBACK
📊 Stock is in uptrend but wait for better entry
```

## Tips:

1. **Keep the bot running**: The Python script needs to be running for the bot to work
2. **Run in background**: You can use `screen` or `tmux` to keep it running:
   ```bash
   screen -S stockbot
   python telegram_bot.py
   # Press Ctrl+A then D to detach
   ```
3. **Multiple users**: You can share your bot with friends! They just need to search for your bot's username
4. **Privacy**: Only people who know your bot's username can use it

## Advanced: Deploy to Cloud (Optional)

To keep your bot running 24/7, you can deploy it to:

### Option 1: PythonAnywhere (Free tier available)
1. Create account at pythonanywhere.com
2. Upload your code
3. Set up a scheduled task to run your bot

### Option 2: Heroku (Free tier available)
1. Create account at heroku.com
2. Install Heroku CLI
3. Deploy your app:
   ```bash
   git init
   heroku create
   git push heroku main
   ```

### Option 3: AWS EC2 Free Tier
1. Create AWS account
2. Launch a t2.micro instance (free tier)
3. SSH into instance and run your bot

### Option 4: Run on your local machine 24/7
Use `screen` or `tmux`:
```bash
screen -S stockbot
cd "/Users/bhargavbvs/Desktop/stock analysis"
source venv/bin/activate
python telegram_bot.py
# Press Ctrl+A then D to detach
# To reattach: screen -r stockbot
```

## Troubleshooting

### Bot doesn't respond
- Check if the script is still running
- Verify your bot token is correct
- Make sure you've started a chat with the bot (send /start first)

### "Import telegram" error
```bash
pip install python-telegram-bot
```

### Bot stops after closing terminal
Use `screen` or `tmux` as shown above, or deploy to cloud

### Rate limits
Telegram has rate limits. If analyzing many stocks quickly, add small delays between requests.

## Security Notes

⚠️ **Keep your bot token SECRET!**
- Don't share it publicly
- Don't commit it to public GitHub repos
- Consider using environment variables:
  ```python
  import os
  BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
  ```

## Next Steps

Once your bot is working, you can:
1. Add more commands (e.g., `/scan` to scan multiple stocks)
2. Add watchlists
3. Set up alerts for specific conditions
4. Add more technical indicators
5. Include volume analysis

## Support

If you have issues:
1. Check the terminal output for error messages
2. Verify the bot token is correct
3. Make sure dependencies are installed
4. Test with well-known stocks first (AAPL, MSFT, GOOGL)

Enjoy your personal stock analysis bot! 🚀📈
