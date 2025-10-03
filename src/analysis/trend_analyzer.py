"""
Trend Analyzer Module

This module contains the logic for identifying trends based on
comprehensive criteria combining multiple technical indicators.
Implements The Tao of Trading methodology.
"""

from indicators import calculate_rsi, calculate_stochastic, calculate_adx
from criteria_checkers import (
    check_ema_stacking_bullish,
    check_ema_stacking_bearish,
    check_price_above_mas,
    check_ma_stacking_2040200,
    check_200ema_slope,
    check_pullback_to_21ema,
    check_price_not_extended,
    check_proximity_to_52w_high,
    check_earnings_date,
    check_rsi_extended,
    check_volume_confirmation,
    check_price_above_21ema_sustained,
    suggest_stop_loss_and_target
)


def analyze_stock(data, ticker_info, current_price):
    """
    Perform complete analysis and return all indicators
    
    Args:
        data (pd.DataFrame): Stock OHLC data
        ticker_info (dict): Ticker information from yfinance
        current_price (float): Current stock price
        
    Returns:
        dict: Dictionary containing all calculated indicators
    """
    if data is None or data.empty:
        return None
    
    from datetime import datetime
    
    # === FIBONACCI EMAs (8, 21, 34, 55, 89) ===
    is_bullish_stacked, emas = check_ema_stacking_bullish(data)
    is_bearish_stacked, _ = check_ema_stacking_bearish(data)
    
    # === ADDITIONAL EMAs (20, 40, 200) ===
    is_2040200_stacked, ma_checks = check_ma_stacking_2040200(data)
    price_above_mas, above_ma_checks = check_price_above_mas(data, current_price)
    ema_200_rising, current_200, prev_200 = check_200ema_slope(data)
    
    # === TECHNICAL INDICATORS ===
    rsi = calculate_rsi(data['Close'])
    rsi_extended, rsi_ext_value = check_rsi_extended(data, 80)
    stoch_k, stoch_d = calculate_stochastic(data, 8, 3)
    adx = calculate_adx(data, 13)
    adx_14 = calculate_adx(data, 14)
    
    # === PRICE POSITION & DYNAMICS ===
    near_21ema, _, ema_21 = check_pullback_to_21ema(data, current_price)
    price_sustained_21ema, days_above_21, ema_21_sustained = check_price_above_21ema_sustained(data, current_price, 5)
    not_extended, extension_pct = check_price_not_extended(data, current_price, 10)
    near_52w_high, high_52w, distance_52w = check_proximity_to_52w_high(data, current_price, 20)
    
    # === VOLUME ANALYSIS ===
    volume_confirms, current_vol, avg_vol = check_volume_confirmation(data, 5, 1.5)
    
    # === RISK MANAGEMENT ===
    stop_loss_suggestion, profit_target_suggestion, rr_ratio = suggest_stop_loss_and_target(data, current_price, 2.0)
    
    # === EARNINGS ===
    has_earnings, earnings_info = check_earnings_date(ticker_info)
    
    return {
        # Price and Date
        'current_price': current_price,
        'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        
        # Fibonacci EMAs (8, 21, 34, 55, 89)
        'ema_8': emas.get('ema_8'),
        'ema_21': emas.get('ema_21'),
        'ema_34': emas.get('ema_34'),
        'ema_55': emas.get('ema_55'),
        'ema_89': emas.get('ema_89'),
        
        # Additional EMAs (20, 40, 200)
        'ema_20': above_ma_checks.get('ema_20'),
        'ema_40': above_ma_checks.get('ema_40'),
        'ema_200': above_ma_checks.get('ema_200'),
        'ema_200_current': current_200,
        'ema_200_previous': prev_200,
        'ema_200_rising': ema_200_rising,
        
        # Technical Indicators
        'rsi': rsi,
        'rsi_extended': rsi_extended,
        'stoch_k': stoch_k,
        'stoch_d': stoch_d,
        'adx': adx,
        'adx_14': adx_14,
        
        # EMA Stacking
        'is_bullish_stacked': is_bullish_stacked,
        'is_bearish_stacked': is_bearish_stacked,
        'is_2040200_stacked': is_2040200_stacked,
        
        # Price Position
        'price_above_20': above_ma_checks.get('above_20'),
        'price_above_40': above_ma_checks.get('above_40'),
        'price_above_200': above_ma_checks.get('above_200'),
        'price_above_all_mas': price_above_mas,
        'near_21ema': near_21ema,
        'price_sustained_above_21ema': price_sustained_21ema,
        'days_above_21ema': days_above_21,
        
        # Price Extension
        'not_extended': not_extended,
        'extension_percent': extension_pct,
        
        # 52-Week High
        'high_52w': high_52w,
        'near_52w_high': near_52w_high,
        'distance_from_52w_high': distance_52w,
        
        # Volume Analysis
        'volume_confirms': volume_confirms,
        'current_volume': current_vol,
        'avg_volume': avg_vol,
        
        # Risk Management
        'stop_loss_suggestion': stop_loss_suggestion,
        'profit_target_suggestion': profit_target_suggestion,
        'risk_reward_ratio': rr_ratio,
        
        # Earnings
        'has_upcoming_earnings': has_earnings,
        'earnings_info': earnings_info
    }


def identify_trend(analysis):
    """
    Identify if stock is in UPTREND or DOWNTREND - Tao of Trading Methodology
    
    Bullish: EMAs stacked upward (8>21>34>55>89), price near 21 EMA, Stoch <= 40
    Bearish: EMAs stacked downward (8<21<34<55<89), price under 21 EMA, Stoch >= 60
    
    Args:
        analysis (dict): Analysis data from analyze_stock()
    
    Returns:
        tuple: (str, list, list) - Trend type, reasons, additional_checks
    """
    if analysis is None:
        return "UNKNOWN", ["Unable to fetch data"], []
    
    reasons = []
    additional_checks = []
    trend = "NEUTRAL"
    
    # ===== BULLISH 5 CRITERIA =====
    is_bullish_stacked = analysis['is_bullish_stacked']
    near_21ema = analysis['near_21ema']
    stoch_k = analysis['stoch_k']
    adx_13 = analysis['adx']
    has_earnings = analysis['has_upcoming_earnings']
    
    # Original criteria checks
    ema_stacked = is_bullish_stacked
    pullback_condition = near_21ema
    stoch_condition = stoch_k is not None and stoch_k <= 40
    adx_13_condition = adx_13 is not None and adx_13 >= 20
    no_earnings = not has_earnings
    
    # Display original criteria
    if ema_stacked:
        reasons.append(f"✓ EMAs stacked bullishly (8>${analysis['ema_8']} > 21>${analysis['ema_21']} > 34>${analysis['ema_34']} > 55>${analysis['ema_55']} > 89>${analysis['ema_89']})")
    else:
        reasons.append(f"✗ EMAs NOT stacked bullishly")
    
    if pullback_condition:
        reasons.append(f"✓ Price pulled back to 21 EMA (Price: ${analysis['current_price']}, 21 EMA: ${analysis['ema_21']})")
    else:
        reasons.append(f"✗ Price not near 21 EMA (Price: ${analysis['current_price']}, 21 EMA: ${analysis['ema_21']})")
    
    if stoch_condition:
        reasons.append(f"✓ Stochastic %K <= 40 (%K: {stoch_k})")
    else:
        reasons.append(f"✗ Stochastic %K > 40 (%K: {stoch_k})")
    
    if adx_13_condition:
        reasons.append(f"✓ Strong trend ADX(13) >= 20 (ADX: {adx_13})")
    else:
        reasons.append(f"✗ Weak trend ADX(13) < 20 (ADX: {adx_13})")
    
    if no_earnings:
        reasons.append(f"✓ No earnings in next 2 weeks ({analysis['earnings_info']})")
    else:
        reasons.append(f"✗ CAUTION: {analysis['earnings_info']}")
    
    # ===== BEARISH 5 CRITERIA =====
    is_bearish_stacked = analysis['is_bearish_stacked']
    
    # Bearish criteria checks
    ema_bearish_stacked = is_bearish_stacked
    under_21ema_condition = not near_21ema and analysis['current_price'] < analysis['ema_21']
    stoch_bearish_condition = stoch_k is not None and stoch_k >= 60
    adx_bearish_condition = adx_13 is not None and adx_13 >= 20
    
    # Display bearish criteria if bearish stacking is present
    if ema_bearish_stacked:
        reasons.append(f"\n⚠️ BEARISH PATTERN DETECTED:")
        reasons.append(f"✓ EMAs stacked bearishly (8<${analysis['ema_8']} < 21<${analysis['ema_21']} < 34<${analysis['ema_34']} < 55<${analysis['ema_55']} < 89<${analysis['ema_89']})")
        
        if under_21ema_condition:
            reasons.append(f"✓ Price under 21 EMA (Price: ${analysis['current_price']}, 21 EMA: ${analysis['ema_21']}) - Resistance overhead")
        else:
            reasons.append(f"✗ Price rallied to/above 21 EMA - Potential short entry at resistance")
        
        if stoch_bearish_condition:
            reasons.append(f"✓ Stochastic %K >= 60 for bearish entry (%K: {stoch_k})")
        else:
            reasons.append(f"✗ Stochastic %K < 60 (%K: {stoch_k}) - Wait for rally")
        
        if adx_bearish_condition:
            reasons.append(f"✓ Strong downtrend ADX(13) >= 20 (ADX: {adx_13})")
        else:
            reasons.append(f"✗ Weak trend ADX(13) < 20 (ADX: {adx_13})")
    
    # ===== ENHANCED CRITERIA (Tao of Trading Methodology) =====
    
    # 6. Price above key MAs
    price_above_all = analysis.get('price_above_all_mas', False)
    if price_above_all:
        additional_checks.append(f"✓ Price above all key MAs (${analysis['current_price']} > 20EMA${analysis['ema_20']} > 40EMA${analysis['ema_40']} > 200EMA${analysis['ema_200']})")
    else:
        additional_checks.append(f"✗ Price not above all MAs")
    
    # 7. 20/40/200 MA stacking
    ma_stacked = analysis.get('is_2040200_stacked', False)
    if ma_stacked:
        additional_checks.append(f"✓ 20/40/200 EMAs stacked (20>${analysis['ema_20']} > 40>${analysis['ema_40']} > 200>${analysis['ema_200']})")
    else:
        additional_checks.append(f"✗ 20/40/200 EMAs not properly stacked")
    
    # 8. 200 EMA slope
    ema_200_rising = analysis.get('ema_200_rising', False)
    if ema_200_rising:
        additional_checks.append(f"✓ 200 EMA rising (${analysis['ema_200_current']} > ${analysis['ema_200_previous']} from 5 days ago)")
    else:
        additional_checks.append(f"✗ 200 EMA not rising or flat")
    
    # 9. RSI filter - Bullish: RSI > 80 = EXTENDED, Bearish: RSI < 20 = OVERSOLD
    rsi = analysis.get('rsi')
    rsi_extended = analysis.get('rsi_extended', False)
    rsi_oversold = rsi is not None and rsi < 20
    rsi_40_condition = rsi is not None and rsi > 40
    rsi_50_condition = rsi is not None and rsi > 50
    rsi_60_condition = rsi is not None and rsi < 60
    
    if rsi_extended:
        additional_checks.append(f"⚠️ RSI > 80 EXTENDED (RSI: {rsi}) - Wait for mean-reversion pullback to 21 EMA!")
    elif rsi_oversold:
        additional_checks.append(f"⚠️ RSI < 20 OVERSOLD (RSI: {rsi}) - Bearish extended, wait for rally to short!")
    elif rsi_50_condition:
        additional_checks.append(f"✓✓ RSI > 50 (strong bullish momentum: {rsi})")
    elif rsi_40_condition and rsi_60_condition:
        additional_checks.append(f"⚪ RSI 40-60 (neutral zone: {rsi})")
    elif rsi_40_condition:
        additional_checks.append(f"✓ RSI > 40 (minimum bullish momentum: {rsi})")
    else:
        additional_checks.append(f"✓ RSI <= 40 (bearish momentum: {rsi})")
    
    # 10. ADX(14) filter
    adx_14 = analysis.get('adx_14')
    adx_14_strong = adx_14 is not None and adx_14 > 25
    adx_14_condition = adx_14 is not None and adx_14 > 20
    if adx_14_strong:
        additional_checks.append(f"✓✓ ADX(14) > 25 (very strong trend: {adx_14})")
    elif adx_14_condition:
        additional_checks.append(f"✓ ADX(14) > 20 (trend confirmed: {adx_14})")
    else:
        additional_checks.append(f"✗ ADX(14) <= 20 (weak or no trend: {adx_14})")
    
    # 11. Price not extended
    not_extended = analysis.get('not_extended', False)
    extension_pct = analysis.get('extension_percent', 0)
    if not_extended:
        additional_checks.append(f"✓ Price not extended (<= 10% above 20 EMA: {extension_pct}%)")
    else:
        additional_checks.append(f"✗ Price too extended (> 10% above 20 EMA: {extension_pct}%)")
    
    # 12. Proximity to 52-week high
    near_52w = analysis.get('near_52w_high', False)
    distance_52w = analysis.get('distance_from_52w_high', 0)
    high_52w = analysis.get('high_52w', 0)
    if near_52w:
        additional_checks.append(f"✓ Within 20% of 52-week high (${high_52w}, distance: {distance_52w}%)")
    else:
        additional_checks.append(f"✗ More than 20% from 52-week high (${high_52w}, distance: {distance_52w}%)")
    
    # Volume confirmation (Must spike during breakouts)
    volume_confirms = analysis.get('volume_confirms', False)
    current_vol = analysis.get('current_volume')
    avg_vol = analysis.get('avg_volume')
    if volume_confirms and current_vol and avg_vol:
        additional_checks.append(f"✓ Volume confirms breakout (Current: {current_vol:,.0f} > Avg: {avg_vol:,.0f}) - Genuine buying pressure")
    elif current_vol and avg_vol:
        additional_checks.append(f"⚪ Volume neutral (Current: {current_vol:,.0f}, Avg: {avg_vol:,.0f})")
    
    # Price sustained above 21 EMA (Prolonged duration)
    price_sustained = analysis.get('price_sustained_above_21ema', False)
    days_above = analysis.get('days_above_21ema', 0)
    if price_sustained:
        additional_checks.append(f"✓ Price sustained above 21 EMA ({days_above} days) - Dynamic support confirmed per Tao of Trading")
    else:
        additional_checks.append(f"⚪ Price not consistently above 21 EMA ({days_above} days)")
    
    # Risk/Reward ratio (2:1 minimum)
    stop_loss = analysis.get('stop_loss_suggestion')
    profit_target = analysis.get('profit_target_suggestion')
    rr_ratio = analysis.get('risk_reward_ratio')
    if stop_loss and profit_target and rr_ratio:
        if rr_ratio >= 2.0:
            additional_checks.append(f"✓ Risk/Reward meets 2:1 Tao of Trading criteria (Stop: ${stop_loss}, Target: ${profit_target}, R/R: {rr_ratio}:1)")
        else:
            additional_checks.append(f"⚠️ Risk/Reward below 2:1 requirement (Stop: ${stop_loss}, Target: ${profit_target}, R/R: {rr_ratio}:1)")
    
    # ===== DETERMINE TREND =====
    
    # Count criteria met
    original_criteria_met = sum([
        ema_stacked,
        pullback_condition,
        stoch_condition,
        adx_13_condition,
        no_earnings
    ])
    
    additional_criteria_met = sum([
        price_above_all,
        ma_stacked,
        ema_200_rising,
        rsi_40_condition and not rsi_extended,  # Don't count if extended
        adx_14_condition,
        not_extended,
        near_52w
    ])
    
    # ===== DETERMINE TREND (BULLISH vs BEARISH) =====
    
    # Count bearish criteria met
    bearish_criteria_met = sum([
        ema_bearish_stacked,
        under_21ema_condition,
        stoch_bearish_condition,
        adx_bearish_condition,
        no_earnings
    ])
    
    # Priority 1: Check for BEARISH trend first
    if ema_bearish_stacked:
        if bearish_criteria_met == 5:
            trend = "STRONG BEARISH - SHORT SIGNAL"
            reasons.append(f"\n🔻 All 5 bearish criteria met - Strong downtrend confirmed")
        elif bearish_criteria_met >= 3:
            if stoch_bearish_condition:
                trend = "DOWNTREND - SHORT ON RALLY TO 21 EMA"
                reasons.append(f"\n⚠️ Tao of Trading: Price rallying to 21 EMA resistance. Enter short when price fails at EMA.")
            else:
                trend = "DOWNTREND - WAIT FOR RALLY"
                reasons.append(f"\n⚠️ Downtrend confirmed but wait for Stochastic >= 60 (rally) before shorting.")
        else:
            trend = "DOWNTREND - DEVELOPING"
            reasons.append(f"\n⚪ Bearish EMA stacking present but not all criteria met yet.")
    
    # Priority 2: Check for BULLISH trend
    elif rsi_extended:
        # RSI > 80: Downgrade to WAIT
        if ema_stacked:
            trend = "UPTREND - WAIT FOR PULLBACK (RSI Extended > 80)"
            reasons.append(f"\n⚠️ Tao of Trading: RSI > 80 means stock is highly extended. Wait for pullback to 21 EMA.")
        else:
            trend = "NEUTRAL"
    elif original_criteria_met == 5:
        if additional_criteria_met >= 5:
            trend = "STRONG BULLISH - BUY SIGNAL"
            reasons.append(f"\n🚀 All 5 bullish criteria + {additional_criteria_met}/7 enhanced criteria met!")
        else:
            trend = "UPTREND - BUY SIGNAL"
            reasons.append(f"\n✅ All 5 core bullish criteria met - Entry signal confirmed")
    elif ema_stacked and original_criteria_met >= 3:
        trend = "UPTREND - WAIT FOR PULLBACK"
        reasons.append(f"\n⚪ Uptrend present but wait for better entry (pullback to 21 EMA or Stoch <= 40)")
    elif ema_stacked or ma_stacked:
        trend = "UPTREND - DEVELOPING"
        reasons.append(f"\n⚪ Bullish EMA structure forming but not all criteria met yet.")
    
    # Priority 3: NEUTRAL
    else:
        trend = "NEUTRAL"
        reasons.append(f"\n⚪ No clear trend - Neither bullish nor bearish criteria met")
    
    reasons.append(f"\n📊 Score: Bullish {original_criteria_met}/5 core + {additional_criteria_met}/7 enhanced | Bearish {bearish_criteria_met}/5")
    
    return trend, reasons, additional_checks
