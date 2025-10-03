"""
Streamlit App - Stock Analyzer with Telegram Bot
Hosts both web dashboard and Telegram bot on Streamlit Cloud
"""

import streamlit as st
import sys
import threading
import time
from pathlib import Path

# Add paths for imports
sys.path.insert(0, str(Path(__file__).parent / 'src' / 'core'))
sys.path.insert(0, str(Path(__file__).parent / 'src' / 'analysis'))

from stock_analyzer import StockAnalyzer
import plotly.graph_objects as go
from datetime import datetime

# Page config
st.set_page_config(
    page_title="Stock Trend Analyzer",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .big-font {
        font-size: 24px !important;
        font-weight: bold;
    }
    .stAlert {
        padding: 1rem;
        border-radius: 0.5rem;
    }
</style>
""", unsafe_allow_html=True)

# Start Telegram bot in background
@st.cache_resource
def start_telegram_bot():
    """Start Telegram bot in background thread"""
    try:
        sys.path.insert(0, str(Path(__file__).parent / 'src' / 'interfaces'))
        from telegram_bot import main as run_bot
        
        bot_thread = threading.Thread(target=run_bot, daemon=True)
        bot_thread.start()
        return "running"
    except Exception as e:
        return f"error: {str(e)}"

# Initialize bot
bot_status = start_telegram_bot()

# Header with bot status
col1, col2 = st.columns([3, 1])
with col1:
    st.title("📈 Stock Trend Analyzer")
    st.markdown("*Advanced technical analysis with options trading recommendations*")
with col2:
    if bot_status == "running":
        st.success("🤖 Bot: Online")
    else:
        st.error("🤖 Bot: Offline")

# Sidebar
with st.sidebar:
    st.header("⚙️ Analysis Settings")
    
    # Stock symbol input
    symbol = st.text_input(
        "Enter Stock Symbol",
        value="AAPL",
        help="Enter a valid stock ticker (e.g., AAPL, TSLA, GOOGL)"
    ).upper()
    
    analyze_button = st.button("🔍 Analyze Stock", type="primary", use_container_width=True)
    
    st.markdown("---")
    
    # Telegram Bot Info
    st.markdown("### 💬 Telegram Bot")
    if bot_status == "running":
        st.success("✅ Active!")
        st.info("📱 Open Telegram and send stock symbols to your bot!")
    else:
        st.warning("⚠️ Starting...")
    
    st.markdown("---")
    st.markdown("### 📚 Trading Signals")
    st.markdown("""
    **Bullish (CALL):**
    - EMAs: 8>21>34>55>89
    - Pullback to 21 EMA
    - Stochastic ≤ 40
    - ADX ≥ 20
    
    **Bearish (PUT):**
    - EMAs: 8<21<34<55<89
    - Price below 21 EMA
    - Stochastic ≥ 60
    - ADX ≥ 20
    """)
    
    st.markdown("---")
    st.caption("⚠️ Educational purposes only")

# Main content
if analyze_button or symbol:
    with st.spinner(f"🔍 Analyzing {symbol}..."):
        try:
            # Analyze stock
            analyzer = StockAnalyzer(symbol)
            trend, reasons, additional_checks, analysis = analyzer.identify_trend()
            
            if analysis is None:
                st.error(f"❌ Unable to analyze {symbol}. Please check the symbol.")
            else:
                # Get options recommendation
                options_rec = analysis.get('options_recommendation', {})
                strategy = options_rec.get('strategy', 'NO TRADE')
                confidence = options_rec.get('confidence', 'N/A')
                
                # Display main signal
                st.markdown("---")
                
                if "CALL" in strategy:
                    st.success(f"### 📞 {strategy}")
                    st.markdown(f"**Confidence:** {confidence}")
                    st.info(options_rec.get('entry', ''))
                elif "PUT" in strategy:
                    st.error(f"### 📉 {strategy}")
                    st.markdown(f"**Confidence:** {confidence}")
                    st.info(options_rec.get('entry', ''))
                else:
                    st.warning(f"### 🚫 {strategy}")
                    st.markdown(f"**Status:** {confidence}")
                
                st.markdown("---")
                
                # Technical indicators
                st.subheader("📊 Key Metrics")
                
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.metric("Current Price", f"${analysis['current_price']}")
                
                with col2:
                    st.metric("RSI (14)", analysis['rsi'])
                    if analysis['rsi'] > 70:
                        st.caption("⚠️ Overbought")
                    elif analysis['rsi'] < 30:
                        st.caption("💡 Oversold")
                
                with col3:
                    st.metric("Stochastic", analysis['stoch_k'])
                    if analysis['stoch_k'] <= 40:
                        st.caption("✅ Bullish zone")
                    elif analysis['stoch_k'] >= 60:
                        st.caption("🔻 Bearish zone")
                
                with col4:
                    st.metric("ADX (13)", analysis['adx'])
                    if analysis['adx'] >= 25:
                        st.caption("✅ Strong trend")
                    else:
                        st.caption("⚠️ Weak trend")
                
                st.markdown("---")
                
                # EMA Stack
                col1, col2 = st.columns(2)
                
                with col1:
                    st.subheader("📈 Fibonacci EMA Stack")
                    
                    ema_df = {
                        'Period': ['8-Day', '21-Day', '34-Day', '55-Day', '89-Day'],
                        'Value': [
                            f"${analysis['ema_8']}",
                            f"${analysis['ema_21']}",
                            f"${analysis['ema_34']}",
                            f"${analysis['ema_55']}",
                            f"${analysis['ema_89']}"
                        ]
                    }
                    st.dataframe(ema_df, use_container_width=True, hide_index=True)
                    
                    if analysis.get('is_bullish_stacked'):
                        st.success("✅ Perfect bullish alignment (8>21>34>55>89)")
                    elif analysis.get('is_bearish_stacked'):
                        st.error("🔻 Bearish alignment (8<21<34<55<89)")
                    else:
                        st.warning("⚠️ Mixed EMA alignment")
                
                with col2:
                    st.subheader("📊 EMA Visualization")
                    
                    # EMA chart
                    fig = go.Figure()
                    
                    emas = [
                        analysis['ema_8'],
                        analysis['ema_21'],
                        analysis['ema_34'],
                        analysis['ema_55'],
                        analysis['ema_89']
                    ]
                    
                    fig.add_trace(go.Scatter(
                        x=['8', '21', '34', '55', '89'],
                        y=emas,
                        mode='lines+markers',
                        name='EMAs',
                        line=dict(color='royalblue', width=3),
                        marker=dict(size=10)
                    ))
                    
                    fig.add_hline(
                        y=analysis['current_price'],
                        line_dash="dash",
                        line_color="red",
                        annotation_text=f"Price: ${analysis['current_price']}"
                    )
                    
                    fig.update_layout(
                        xaxis_title="EMA Period",
                        yaxis_title="Price ($)",
                        height=300,
                        showlegend=False
                    )
                    
                    st.plotly_chart(fig, use_container_width=True)
                
                st.markdown("---")
                
                # Options Strategy Details
                st.subheader("📋 Options Strategy")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    st.markdown("**Entry Guidance:**")
                    st.info(options_rec.get('entry', 'N/A'))
                
                with col2:
                    st.markdown("**Risk Management:**")
                    st.warning(options_rec.get('risk', 'N/A'))
                
                st.markdown("**Reasoning:**")
                st.write(options_rec.get('reasoning', 'N/A'))
                
                st.markdown("---")
                
                # Criteria checklist
                st.subheader("✅ Criteria Analysis")
                
                # Determine which criteria to show
                is_bearish_signal = "BEARISH" in trend or "PUT" in trend
                is_bullish_signal = "BULLISH" in trend or "CALL" in trend
                
                if is_bullish_signal:
                    st.markdown("#### 📈 Bullish Criteria")
                    criteria = [r for r in reasons if r.strip().startswith(('✓', '✗')) and "BEARISH" not in ''.join(reasons[:reasons.index(r) if r in reasons else 0])][:5]
                elif is_bearish_signal:
                    st.markdown("#### 🔻 Bearish Criteria")
                    bearish_start = next((i for i, r in enumerate(reasons) if "BEARISH CRITERIA" in r), -1)
                    if bearish_start >= 0:
                        criteria = [r for r in reasons[bearish_start+1:] if r.strip().startswith(('✓', '✗'))][:5]
                    else:
                        criteria = []
                else:
                    st.markdown("#### 📊 Analysis Criteria")
                    criteria = [r for r in reasons if r.strip().startswith(('✓', '✗'))][:5]
                
                for criterion in criteria:
                    if criterion.strip().startswith('✓'):
                        st.success(criterion)
                    else:
                        st.error(criterion)
                
                # Timestamp
                st.caption(f"⏰ Analysis as of {analysis['date']}")
                
        except Exception as e:
            st.error(f"❌ Error: {str(e)}")
            with st.expander("Error Details"):
                st.exception(e)
else:
    # Welcome screen
    st.info("👈 Enter a stock symbol in the sidebar and click 'Analyze Stock' to begin")
    
    st.markdown("### 🎯 How It Works")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("#### 📞 Call Options")
        st.markdown("""
        **When to buy:**
        - EMAs align bullishly
        - Price pulls back to 21 EMA
        - Stochastic ≤ 40
        - Strong ADX trend
        - No earnings within 2 weeks
        """)
    
    with col2:
        st.markdown("#### 📉 Put Options")
        st.markdown("""
        **When to buy:**
        - EMAs align bearishly
        - Price below 21 EMA
        - Stochastic ≥ 60
        - Strong ADX trend
        - No earnings within 2 weeks
        """)
    
    with col3:
        st.markdown("#### 🚫 No Trade")
        st.markdown("""
        **Avoid when:**
        - Mixed signals
        - Weak trend (ADX < 20)
        - Choppy price action
        - Earnings approaching
        - Extended prices
        """)

# Footer
st.markdown("---")
st.markdown("""
<div style='text-align: center'>
    <p><strong>Built with The Tao of Trading methodology</strong></p>
    <p><small>⚠️ For educational purposes only - Not financial advice</small></p>
</div>
""", unsafe_allow_html=True)
