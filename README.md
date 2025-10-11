# 📈 Stock Trend Analyzer - Telegram Bot

A powerful Telegram bot for **Options Trading Analysis** using The Tao of Trading methodology with Fibonacci EMAs.

💬 **Telegram Bot** | 📊 **Real-Time Analysis** | 🚀 **24/7 Uptime on Railway**

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app)

---

## 🎯 Features

- **📞 CALL Options Signals** - Identifies bullish trends for buying call options
- **📉 PUT Options Signals** - Identifies bearish trends for buying put options  
- **💬 Telegram Bot** - Get instant analysis via Telegram from anywhere in the world
- **✅ Context-Aware Criteria** - Shows bullish OR bearish criteria based on detected trend
- **📊 Technical Analysis** - Fibonacci EMAs (5, 8, 13, 21, 34, 55, 89), RSI, Stochastic, ADX
- **⚡ Always Online** - Runs 24/7 on Railway, never sleeps
- **🌍 Global Access** - Works from any country, any device with Telegram
- **🔄 Auto-Updates** - Push to GitHub = automatic redeployment

---

## 🚀 Quick Start

### Use the Telegram Bot

1. **Open Telegram** on your phone or computer
2. **Search** for your bot (username set with @BotFather)
3. **Send** `/start` to begin
4. **Send stock symbol** (e.g., `AAPL`, `TSLA`, `NVDA`)
5. **Get instant analysis** with options recommendations!

### Example Usage:

```
You: /start

Bot: 👋 Hi! Welcome to Stock Trend Analyzer Bot!
     📈 Send me any stock symbol...

You: AAPL

Bot: 🚀 APPLE INC (AAPL) - $250.32
     
     📊 ANALYSIS
     Trend: STRONG BULLISH ✅
     Current Price: $250.32
     21 EMA: $248.50 (within 0.73%)
     
     📞 OPTIONS RECOMMENDATION
     Strategy: BUY CALL OPTIONS
     Confidence: VERY HIGH
     
     Entry: When price confirms above $249
     Risk: Stop-loss below $245 (-2.1%)
     
     ✅ BULLISH CRITERIA (5/5 met):
     ✅ EMAs stacked bullishly (8>21>34>55>89)
     ✅ Pullback to 21 EMA (within 2%)
     ✅ Stochastic: 38 (oversold, good entry)
     ✅ ADX: 24 (strong trend confirmed)
     ✅ No earnings within 7 days
```

---

## 📋 What You Get

### Options Trading Recommendations

#### 📞 CALL Options (Bullish Signals)
- **Strategy**: BUY CALL OPTIONS
- **Confidence Levels**: VERY HIGH, HIGH, MODERATE, or LOW
- **Entry Guidance**: Specific price levels and conditions
- **Risk Management**: Stop-loss levels and position sizing

#### 📉 PUT Options (Bearish Signals)
- **Strategy**: BUY PUT OPTIONS  
- **Confidence Levels**: VERY HIGH, HIGH, MODERATE, or LOW
- **Entry Guidance**: Specific price levels and conditions
- **Risk Management**: Stop-loss levels and position sizing

---

## ✅ Analysis Criteria

The bot checks different criteria based on detected trend direction:

### 📈 Bullish Criteria (for CALL Options)
1. ✅ **EMAs Stacked Bullishly** - 8>21>34>55>89 (uptrend confirmed)
2. ✅ **Pullback to Support** - Price within 2% of 21 EMA
3. ✅ **Oversold Momentum** - Stochastic ≤40 (good entry point)
4. ✅ **Strong Trend** - ADX ≥20 (trending market)
5. ✅ **No Earnings Risk** - No earnings within 7 days

**Signal**: When 4+ criteria met → **BUY CALL OPTIONS**

---

### 📉 Bearish Criteria (for PUT Options)
1. ✅ **EMAs Stacked Bearishly** - 8<21<34<55<89 (downtrend confirmed)
2. ✅ **Price Below Resistance** - Price below 21 EMA
3. ✅ **Overbought Momentum** - Stochastic ≥60 (rally exhaustion)
4. ✅ **Strong Trend** - ADX ≥20 (trending market)
5. ✅ **No Earnings Risk** - No earnings within 7 days

**Signal**: When 4+ criteria met → **BUY PUT OPTIONS**

---

## 🚀 Deploy Your Own Bot

### Prerequisites:
1. GitHub account
2. Railway account (free $5 credit)
3. Telegram bot token from @BotFather

### Deploy to Railway (5 minutes):

**Step 1: Get Bot Token**
1. Open Telegram, search for `@BotFather`
2. Send `/newbot`
3. Follow instructions, copy your bot token

**Step 2: Deploy on Railway**
1. Go to [railway.app](https://railway.app)
2. Sign in with GitHub
3. Click **"New Project"** → **"Deploy from GitHub repo"**
4. Select this repository
5. Add environment variable:
   - Name: `TELEGRAM_BOT_TOKEN`
   - Value: Your bot token from @BotFather
6. Click **"Deploy"**

**Step 3: Test**
- Wait 2-3 minutes for deployment
- Open Telegram, find your bot
- Send `/start` and test with a stock symbol!

**Full deployment guide**: See [RAILWAY_DEPLOYMENT.md](RAILWAY_DEPLOYMENT.md)

---

## 💻 Run Locally (Development)

```bash
# Clone repository
git clone https://github.com/YOUR_USERNAME/stockanalysis.git
cd stockanalysis

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set bot token
export TELEGRAM_BOT_TOKEN="your_token_here"

# Run bot
python bot.py
```

Bot will start and listen for Telegram messages!

---

## 📂 Project Structure

```
stockanalysis/
├── bot.py                          # Main entry point (Telegram bot)
├── requirements.txt                # Python dependencies
├── Procfile                        # Railway start command
├── railway.json                    # Railway configuration
├── runtime.txt                     # Python version (3.11)
├── src/
│   ├── core/
│   │   ├── stock_analyzer.py      # Core analysis engine
│   │   └── data_fetcher.py        # Yahoo Finance data fetcher
│   ├── analysis/
│   │   ├── indicators.py          # Technical indicators (RSI, Stochastic, ADX)
│   │   ├── trend_analyzer.py      # Trend identification logic
│   │   └── criteria_checkers.py   # Bullish/bearish criteria checks
│   ├── interfaces/
│   │   └── telegram_bot.py        # Telegram bot interface
│   └── utils/
│       └── output_formatter.py    # Pretty formatting
└── docs/
    ├── RAILWAY_DEPLOYMENT.md       # Complete deployment guide
    ├── RAILWAY_BUILD_FIX.md        # Build troubleshooting
    ├── OPTIONS_TRADING_GUIDE.md    # Options trading methodology
    └── TAO_OF_TRADING_METHODOLOGY.md # Full trading methodology
```

---

## 🛠️ Tech Stack

- **Language**: Python 3.11
- **Bot Framework**: python-telegram-bot
- **Data Source**: Yahoo Finance (yfinance)
- **Hosting**: Railway (always-on, $5/month)
- **Data Processing**: pandas, numpy
- **Indicators**: Custom implementations (RSI, Stochastic, ADX)

---

## 📊 Technical Indicators

### Fibonacci EMAs (5, 8, 13, 21, 34, 55, 89)
- **Purpose**: Identify trend direction and strength
- **Bullish**: Higher EMAs below lower EMAs (stacked bullishly)
- **Bearish**: Higher EMAs above lower EMAs (stacked bearishly)

### RSI (Relative Strength Index)
- **Range**: 0-100
- **Overbought**: >70 (potential reversal down)
- **Oversold**: <30 (potential reversal up)

### Stochastic Oscillator
- **Range**: 0-100
- **Bullish Entry**: ≤40 (pullback in uptrend)
- **Bearish Entry**: ≥60 (rally in downtrend)

### ADX (Average Directional Index)
- **Range**: 0-100
- **Strong Trend**: ≥25
- **Minimum Trend**: ≥20
- **Weak/No Trend**: <20

---

## 💰 Pricing

### Railway Hosting:
- **First Month**: FREE ($5 credit included)
- **After First Month**: $5/month
- **Year 1**: $55 total

### Compare to Alternatives:
| Platform | Cost | Always-On | Speed |
|----------|------|-----------|-------|
| **Railway** ⭐ | $55/year | ✅ Yes | ⚡ Fast |
| AWS EC2 | $120/year | ✅ Yes | ⚡ Fast |
| DigitalOcean | $144/year | ✅ Yes | ⚡ Fast |
| Render.com | $77/year | ✅ Yes | ⚡ Fast |
| Heroku | $84/year | ✅ Yes | 🟡 OK |

**Railway = Best value!** 🏆

---

## 📈 Trading Methodology

Based on **The Tao of Trading** by Simon Ree:

1. **Fibonacci EMAs** - Multi-timeframe analysis using 5, 8, 13, 21, 34, 55, 89
2. **Pullback Strategy** - Buy pullbacks in uptrends, sell rallies in downtrends
3. **Momentum Confirmation** - Use Stochastic for precise entry timing
4. **Trend Strength** - ADX confirms strong trending markets
5. **Risk Management** - Never trade into earnings, always use stop-losses

See [TAO_OF_TRADING_METHODOLOGY.md](docs/TAO_OF_TRADING_METHODOLOGY.md) for complete details.

---

## ⚠️ Disclaimer

**This bot is for educational purposes only. Not financial advice.**

- Always do your own research
- Never risk more than you can afford to lose
- Options trading carries significant risk
- Past performance doesn't guarantee future results
- Consult a licensed financial advisor before trading

---

## 🤝 Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit changes (`git commit -m 'Add AmazingFeature'`)
4. Push to branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

---

## 📄 License

This project is licensed under the MIT License - see [LICENSE](LICENSE) file for details.

---

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/YOUR_USERNAME/stockanalysis/issues)
- **Documentation**: See `/docs` folder
- **Railway Deployment**: [RAILWAY_DEPLOYMENT.md](RAILWAY_DEPLOYMENT.md)
- **Build Troubleshooting**: [RAILWAY_BUILD_FIX.md](RAILWAY_BUILD_FIX.md)

---

## 🙏 Acknowledgments

- **The Tao of Trading** by Simon Ree - Trading methodology foundation
- **Yahoo Finance** - Free market data API
- **Railway.app** - Affordable, reliable hosting platform
- **Telegram** - Powerful bot platform

---

## 📸 Screenshots

### Telegram Bot in Action

**Starting the Bot:**
```
/start
👋 Hi! Welcome to Stock Trend Analyzer Bot!
📈 I can analyze stocks and provide options recommendations
```

**Analyzing a Stock:**
```
AAPL
🚀 Analysis complete!
📞 Recommendation: BUY CALL OPTIONS
✅ Confidence: VERY HIGH
```

---

Made with ❤️ for traders who want data-driven options trading decisions

**⭐ Star this repo if you find it useful!**

**🚀 Deploy your own bot today!** → [Railway Deployment Guide](RAILWAY_DEPLOYMENT.md)
