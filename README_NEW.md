# 📈 Stock Trend Analyzer with Options Trading

A comprehensive stock analysis tool with **CALL & PUT Options Recommendations** using The Tao of Trading methodology.

🌐 **[Live Web App](https://your-app.streamlit.app)** | 💬 **Telegram Bot** | 📊 **Interactive Charts**

[![Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://your-app.streamlit.app)

---

## 🎯 Features

- **📞 CALL Options Signals** - Identifies bullish trends for buying call options
- **📉 PUT Options Signals** - Identifies bearish trends for buying put options  
- **📊 Interactive EMA Charts** - Beautiful Fibonacci EMA visualizations with Plotly
- **💬 Telegram Bot** - Get instant analysis via Telegram from anywhere
- **🌐 Web Dashboard** - Full-featured Streamlit web interface
- **✅ Smart Criteria** - Shows bullish OR bearish criteria based on detected trend
- **🎨 Modern UI** - Clean, responsive design with real-time data

---

## 🚀 Quick Start

### Option 1: Use Live Web App (Recommended - No Installation)
Visit: **[https://your-app.streamlit.app](https://your-app.streamlit.app)**

1. Enter a stock symbol (e.g., `AAPL`, `TSLA`, `NVDA`)
2. See instant analysis with EMA charts
3. Get options trading recommendations (CALL/PUT)
4. View criteria checklist

### Option 2: Use Telegram Bot
1. Search for `@YourBotUsername` on Telegram
2. Send `/start` to begin
3. Send any stock symbol (e.g., `AAPL`)
4. Receive instant analysis with options recommendations

### Option 3: Run Locally
```bash
# Clone repository
git clone https://github.com/YOUR_USERNAME/stockanalysis.git
cd stockanalysis

# Install dependencies
pip install -r requirements.txt

# Run Streamlit app (opens in browser)
streamlit run app.py
```

---

## 📋 What You Get

### Options Recommendations

#### 📞 CALL Options (Bullish Signals)
- **Strategy**: BUY CALL OPTIONS
- **Confidence**: VERY HIGH, HIGH, MODERATE, or LOW
- **Entry Guidance**: Specific entry conditions
- **Risk Management**: Stop-loss and position sizing rules

#### 📉 PUT Options (Bearish Signals)
- **Strategy**: BUY PUT OPTIONS
- **Confidence**: VERY HIGH, HIGH, MODERATE, or LOW
- **Entry Guidance**: Specific entry conditions
- **Risk Management**: Stop-loss and position sizing rules

---

## ✅ Analysis Criteria

The system checks different criteria based on detected trend direction:

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

## 🛠️ Tech Stack

- **Backend**: Python 3.9+
- **Data Source**: Yahoo Finance (yfinance)
- **Web Framework**: Streamlit
- **Charts**: Plotly (interactive visualizations)
- **Bot Framework**: python-telegram-bot
- **Hosting**: Streamlit Cloud (free tier)

---

## 📂 Project Structure

```
stockanalysis/
├── app.py                          # Main Streamlit app (web + Telegram bot)
├── requirements.txt                # Python dependencies
├── .streamlit/
│   └── config.toml                # Streamlit configuration
├── src/
│   ├── core/
│   │   ├── stock_analyzer.py      # Core analysis engine
│   │   └── data_fetcher.py        # Yahoo Finance data fetcher
│   ├── analysis/
│   │   ├── indicators.py          # Technical indicators (RSI, Stochastic, ADX)
│   │   ├── trend_analyzer.py      # Trend identification logic
│   │   └── criteria_checkers.py   # Bullish/bearish criteria checks
│   ├── interfaces/
│   │   ├── telegram_bot.py        # Telegram bot interface
│   │   └── stock_analyzer_gui.py  # Legacy GUI (optional)
│   └── utils/
│       └── output_formatter.py    # Pretty formatting
└── docs/
    ├── STREAMLIT_DEPLOY.md        # Deployment guide
    ├── OPTIONS_TRADING_GUIDE.md   # Options trading methodology
    └── TAO_OF_TRADING_METHODOLOGY.md  # Full trading methodology
```

---

## 🔧 Configuration

### Telegram Bot Setup
1. Create bot via [@BotFather](https://t.me/BotFather)
2. Get your bot token
3. Add to Streamlit secrets (for cloud deployment):
   ```toml
   # .streamlit/secrets.toml
   TELEGRAM_BOT_TOKEN = "your_token_here"
   ```
4. Or set environment variable (for local):
   ```bash
   export TELEGRAM_BOT_TOKEN="your_token_here"
   ```

### Streamlit Cloud Deployment
See [STREAMLIT_DEPLOY.md](STREAMLIT_DEPLOY.md) for complete instructions.

**Quick Steps:**
1. Push code to GitHub
2. Go to [streamlit.io/cloud](https://streamlit.io/cloud)
3. Connect GitHub repo
4. Add Telegram bot token to secrets
5. Deploy (takes 2 minutes)

**Cost:** $0/month on free tier

---

## 💡 Usage Examples

### Web Dashboard
1. Open app: `https://your-app.streamlit.app`
2. Enter symbol: `AAPL`
3. Click "Analyze Stock"
4. See results:
   - Options recommendation (CALL/PUT)
   - Confidence level
   - Interactive EMA chart
   - Criteria checklist
   - Risk management guidance

### Telegram Bot
```
You: /start
Bot: Welcome! Send me any stock symbol...

You: TSLA
Bot: 🚀 TESLA INC (TSLA) - $250.32

📊 ANALYSIS
Trend: STRONG BULLISH ✅
Current Price: $250.32
21 EMA: $248.50 (within 0.73%)

📞 OPTIONS RECOMMENDATION
Strategy: BUY CALL OPTIONS
Confidence: VERY HIGH
Entry: When price confirms above $249
Risk: Stop-loss below $245

✅ BULLISH CRITERIA (5/5 met):
✅ EMAs stacked bullishly
✅ Pullback to 21 EMA
✅ Stochastic: 38 (oversold)
✅ ADX: 24 (strong trend)
✅ No earnings within 7 days
```

---

## 📈 Trading Methodology

Based on **The Tao of Trading** by Simon Ree:

1. **Fibonacci EMAs** - Using 5, 8, 13, 21, 34, 55, 89 for multi-timeframe analysis
2. **Pullback Strategy** - Buy pullbacks in uptrends, sell rallies in downtrends
3. **Momentum Confirmation** - Use Stochastic for entry timing
4. **Trend Strength** - ADX confirms strong trending markets
5. **Risk Management** - Never trade into earnings, always use stop-losses

See [TAO_OF_TRADING_METHODOLOGY.md](TAO_OF_TRADING_METHODOLOGY.md) for full details.

---

## ⚠️ Disclaimer

**This tool is for educational purposes only. Not financial advice.**

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
- **Telegram**: @YourBotUsername
- **Email**: your.email@example.com

---

## 🙏 Acknowledgments

- **The Tao of Trading** by Simon Ree - Trading methodology
- **Yahoo Finance** - Market data
- **Streamlit** - Web framework
- **Plotly** - Interactive charts

---

## 📸 Screenshots

### Web Dashboard
![Web Dashboard](docs/screenshots/dashboard.png)

### Telegram Bot
![Telegram Bot](docs/screenshots/telegram.png)

### EMA Chart
![EMA Chart](docs/screenshots/chart.png)

---

Made with ❤️ for traders who want data-driven decisions

**⭐ Star this repo if you find it useful!**
