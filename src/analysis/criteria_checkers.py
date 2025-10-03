"""
Criteria Checkers Module

This module contains functions to check various bullish/bearish criteria:
- EMA stacking
- Price pullback conditions
- Price extension checks
- 52-week high proximity
- Earnings date checks
- Tao of Trading methodology additions (RSI extended, volume confirmation, risk/reward)
"""

from datetime import datetime
from indicators import calculate_ema, calculate_ema_series, get_52_week_high


def check_ema_stacking_bullish(data):
    """
    Check if EMAs are stacked in bullish fashion:
    8 EMA > 21 EMA > 34 EMA > 55 EMA > 89 EMA
    
    Args:
        data (pd.DataFrame): Price data
        
    Returns:
        tuple: (bool, dict) - Is stacked bullishly, EMA values
    """
    if data is None or data.empty:
        return False, {}
    
    close_prices = data['Close']
    
    ema_8 = calculate_ema(close_prices, 8)
    ema_21 = calculate_ema(close_prices, 21)
    ema_34 = calculate_ema(close_prices, 34)
    ema_55 = calculate_ema(close_prices, 55)
    ema_89 = calculate_ema(close_prices, 89)
    
    emas = {
        'ema_8': ema_8,
        'ema_21': ema_21,
        'ema_34': ema_34,
        'ema_55': ema_55,
        'ema_89': ema_89
    }
    
    is_stacked = (ema_8 > ema_21 > ema_34 > ema_55 > ema_89)
    
    return is_stacked, emas


def check_ema_stacking_bearish(data):
    """
    Check if EMAs are stacked in bearish fashion:
    8 EMA < 21 EMA < 34 EMA < 55 EMA < 89 EMA
    
    Args:
        data (pd.DataFrame): Price data
        
    Returns:
        tuple: (bool, dict) - Is stacked bearishly, EMA values
    """
    if data is None or data.empty:
        return False, {}
    
    close_prices = data['Close']
    
    ema_8 = calculate_ema(close_prices, 8)
    ema_21 = calculate_ema(close_prices, 21)
    ema_34 = calculate_ema(close_prices, 34)
    ema_55 = calculate_ema(close_prices, 55)
    ema_89 = calculate_ema(close_prices, 89)
    
    emas = {
        'ema_8': ema_8,
        'ema_21': ema_21,
        'ema_34': ema_34,
        'ema_55': ema_55,
        'ema_89': ema_89
    }
    
    is_stacked = (ema_8 < ema_21 < ema_34 < ema_55 < ema_89)
    
    return is_stacked, emas


def check_price_above_mas(data, current_price):
    """
    Check if price is above key moving averages: 20 EMA, 40 EMA, 200 EMA
    
    Args:
        data (pd.DataFrame): Price data
        current_price (float): Current price
        
    Returns:
        tuple: (bool, dict) - All above, individual checks
    """
    if data is None or data.empty:
        return False, {}
    
    close_prices = data['Close']
    
    ema_20 = calculate_ema(close_prices, 20)
    ema_40 = calculate_ema(close_prices, 40)
    ema_200 = calculate_ema(close_prices, 200)
    
    above_20 = current_price > ema_20 if ema_20 else False
    above_40 = current_price > ema_40 if ema_40 else False
    above_200 = current_price > ema_200 if ema_200 else False
    
    checks = {
        'ema_20': ema_20,
        'ema_40': ema_40,
        'ema_200': ema_200,
        'above_20': above_20,
        'above_40': above_40,
        'above_200': above_200
    }
    
    all_above = above_20 and above_40 and above_200
    
    return all_above, checks


def check_ma_stacking_2040200(data):
    """
    Check if moving averages are stacked bullishly: 20 EMA > 40 EMA > 200 EMA
    
    Args:
        data (pd.DataFrame): Price data
        
    Returns:
        tuple: (bool, dict) - Is stacked, EMA values
    """
    if data is None or data.empty:
        return False, {}
    
    close_prices = data['Close']
    
    ema_20 = calculate_ema(close_prices, 20)
    ema_40 = calculate_ema(close_prices, 40)
    ema_200 = calculate_ema(close_prices, 200)
    
    emas = {
        'ema_20': ema_20,
        'ema_40': ema_40,
        'ema_200': ema_200
    }
    
    is_stacked = (ema_20 > ema_40 > ema_200) if all([ema_20, ema_40, ema_200]) else False
    
    return is_stacked, emas


def check_200ema_slope(data, lookback_days=5):
    """
    Check if 200 EMA is rising (positive slope)
    
    Args:
        data (pd.DataFrame): Price data
        lookback_days (int): Days to look back for slope calculation (default: 5)
        
    Returns:
        tuple: (bool, float, float) - Is rising, current EMA 200, previous EMA 200
    """
    if data is None or data.empty:
        return False, None, None
    
    ema_200_series = calculate_ema_series(data['Close'], 200)
    
    if ema_200_series is None or len(ema_200_series) < lookback_days + 1:
        return False, None, None
    
    current_ema_200 = ema_200_series.iloc[-1]
    previous_ema_200 = ema_200_series.iloc[-lookback_days - 1]
    
    is_rising = current_ema_200 > previous_ema_200
    
    return is_rising, round(current_ema_200, 2), round(previous_ema_200, 2)


def check_pullback_to_21ema(data, current_price, tolerance_percent=2):
    """
    Check if price has pulled back to 21 EMA
    
    Args:
        data (pd.DataFrame): Price data
        current_price (float): Current price
        tolerance_percent (float): Tolerance percentage for pullback (default: 2%)
        
    Returns:
        tuple: (bool, float, float) - Is near 21 EMA, current price, 21 EMA
    """
    if data is None or data.empty:
        return False, None, None
    
    ema_21 = calculate_ema(data['Close'], 21)
    
    if not ema_21:
        return False, None, None
    
    # Check if price is within tolerance of 21 EMA
    tolerance = ema_21 * (tolerance_percent / 100)
    is_near = abs(current_price - ema_21) <= tolerance
    
    return is_near, current_price, ema_21


def check_price_not_extended(data, current_price, max_extension_percent=10):
    """
    Check if price is not extended more than max_extension_percent above 20 EMA
    
    Args:
        data (pd.DataFrame): Price data
        current_price (float): Current price
        max_extension_percent (float): Maximum extension percentage (default: 10%)
        
    Returns:
        tuple: (bool, float) - Not extended, extension percentage
    """
    if data is None or data.empty:
        return False, None
    
    ema_20 = calculate_ema(data['Close'], 20)
    
    if not ema_20:
        return False, None
    
    extension_percent = ((current_price - ema_20) / ema_20) * 100
    is_not_extended = extension_percent <= max_extension_percent
    
    return is_not_extended, round(extension_percent, 2)


def check_proximity_to_52w_high(data, current_price, max_distance_percent=20):
    """
    Check if price is within max_distance_percent of 52-week high
    
    Args:
        data (pd.DataFrame): Price data
        current_price (float): Current price
        max_distance_percent (float): Maximum distance from 52w high (default: 20%)
        
    Returns:
        tuple: (bool, float, float) - Within range, 52w high, distance percentage
    """
    if data is None or data.empty:
        return False, None, None
    
    high_52w = get_52_week_high(data)
    
    if not high_52w:
        return False, None, None
    
    distance_percent = ((high_52w - current_price) / high_52w) * 100
    within_range = distance_percent <= max_distance_percent
    
    return within_range, high_52w, round(distance_percent, 2)


def check_earnings_date(ticker_info):
    """
    Check if earnings are scheduled in the next two weeks
    
    Args:
        ticker_info (dict): Stock ticker info from yfinance
        
    Returns:
        tuple: (bool, str) - Has upcoming earnings, date string
    """
    try:
        if ticker_info is None:
            return None, "Unable to fetch earnings data"
        
        # Try to get earnings date
        earnings_date = ticker_info.get('earningsDate')
        
        if earnings_date is None or len(earnings_date) == 0:
            return False, "No upcoming earnings date found"
        
        # Get the next earnings date (usually first in the list)
        next_earnings = earnings_date[0] if isinstance(earnings_date, list) else earnings_date
        
        # Convert to datetime if it's a timestamp
        if hasattr(next_earnings, 'timestamp'):
            next_earnings = datetime.fromtimestamp(next_earnings.timestamp())
        elif isinstance(next_earnings, str):
            next_earnings = datetime.strptime(next_earnings, '%Y-%m-%d')
        
        # Check if within next 14 days
        days_until = (next_earnings - datetime.now()).days
        
        if 0 <= days_until <= 14:
            return True, f"Earnings in {days_until} days ({next_earnings.strftime('%Y-%m-%d')})"
        else:
            return False, f"Earnings date: {next_earnings.strftime('%Y-%m-%d')} ({days_until} days away)"
            
    except Exception as e:
        return None, f"Unable to determine earnings date: {str(e)}"


# ===== TAO OF TRADING METHODOLOGY ADDITIONS =====

def check_rsi_extended(data, rsi_threshold=80):
    """
    Check if RSI indicates stock is extended (overbought) - Tao of Trading methodology
    RSI > 80% indicates stock is highly extended and likely due for pullback
    
    Args:
        data (pd.DataFrame): Price data
        rsi_threshold (float): RSI threshold for extension (default: 80)
        
    Returns:
        tuple: (bool, float) - Is extended, RSI value
    """
    if data is None or data.empty:
        return False, None
    
    from indicators import calculate_rsi
    rsi = calculate_rsi(data['Close'])
    
    if rsi is None:
        return False, None
    
    is_extended = rsi > rsi_threshold
    
    return is_extended, round(rsi, 2)


def check_volume_confirmation(data, lookback_days=5, volume_multiplier=1.5):
    """
    Check if volume confirms price action - Tao of Trading methodology
    Volume should spike during bullish breakouts above resistance levels
    
    Args:
        data (pd.DataFrame): OHLCV data
        lookback_days (int): Days to look back for volume comparison (default: 5)
        volume_multiplier (float): Volume spike multiplier (default: 1.5x)
        
    Returns:
        tuple: (bool, float, float) - Volume confirms, current volume, avg volume
    """
    if data is None or data.empty or 'Volume' not in data.columns:
        return False, None, None
    
    if len(data) < lookback_days + 1:
        return False, None, None
    
    current_volume = data['Volume'].iloc[-1]
    avg_volume = data['Volume'].iloc[-lookback_days-1:-1].mean()
    
    volume_confirms = current_volume > (avg_volume * volume_multiplier)
    
    return volume_confirms, current_volume, round(avg_volume, 0)


def check_price_above_21ema_sustained(data, current_price, min_days=5):
    """
    Check if price has sustained above 21 EMA for prolonged duration - Tao of Trading methodology
    Price must sustain levels above 21 EMA for prolonged duration as critical dynamic support
    
    Args:
        data (pd.DataFrame): Price data
        current_price (float): Current price
        min_days (int): Minimum days above 21 EMA (default: 5)
        
    Returns:
        tuple: (bool, int, float) - Sustained above, days above, 21 EMA
    """
    if data is None or data.empty or len(data) < min_days:
        return False, 0, None
    
    ema_21_series = calculate_ema_series(data['Close'], 21)
    
    if ema_21_series is None:
        return False, 0, None
    
    # Count consecutive days above 21 EMA
    days_above = 0
    for i in range(len(data) - 1, -1, -1):
        if data['Close'].iloc[i] > ema_21_series.iloc[i]:
            days_above += 1
        else:
            break
    
    is_sustained = days_above >= min_days
    current_ema_21 = ema_21_series.iloc[-1]
    
    return is_sustained, days_above, round(current_ema_21, 2)


def calculate_risk_reward_ratio(entry_price, stop_loss, profit_target):
    """
    Calculate risk/reward ratio - Tao of Trading methodology
    Minimum 2:1 Reward-to-Risk ratio required for trades
    
    Args:
        entry_price (float): Entry price
        stop_loss (float): Stop loss price
        profit_target (float): Profit target price
        
    Returns:
        tuple: (float, bool, dict) - Risk/reward ratio, meets criteria, details
    """
    if not all([entry_price, stop_loss, profit_target]):
        return None, False, {}
    
    risk = abs(entry_price - stop_loss)
    reward = abs(profit_target - entry_price)
    
    if risk == 0:
        return None, False, {}
    
    risk_reward_ratio = reward / risk
    
    # Tao of Trading requires minimum 2:1 ratio
    meets_criteria = risk_reward_ratio >= 2.0
    
    details = {
        'entry_price': entry_price,
        'stop_loss': stop_loss,
        'profit_target': profit_target,
        'risk': risk,
        'reward': reward,
        'ratio': round(risk_reward_ratio, 2)
    }
    
    return round(risk_reward_ratio, 2), meets_criteria, details


def suggest_stop_loss_and_target(data, current_price, atr_multiplier=2.0):
    """
    Suggest stop loss and profit target based on ATR - Tao of Trading methodology
    Provides guidance for 2:1 risk/reward setup
    
    Args:
        data (pd.DataFrame): OHLCV data
        current_price (float): Current price
        atr_multiplier (float): ATR multiplier for stop loss (default: 2.0)
        
    Returns:
        tuple: (float, float, float) - Stop loss, profit target, risk/reward ratio
    """
    if data is None or data.empty:
        return None, None, None
    
    import pandas as pd
    
    # Calculate ATR for stop loss
    high = data['High']
    low = data['Low']
    close = data['Close']
    
    tr1 = high - low
    tr2 = abs(high - close.shift())
    tr3 = abs(low - close.shift())
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=14).mean().iloc[-1]
    
    if pd.isna(atr):
        return None, None, None
    
    # Suggest stop loss below current price (for long position)
    stop_loss = current_price - (atr * atr_multiplier)
    
    # Suggest profit target for 2:1 risk/reward
    risk = current_price - stop_loss
    profit_target = current_price + (risk * 2)
    
    risk_reward_ratio = (profit_target - current_price) / (current_price - stop_loss)
    
    return round(stop_loss, 2), round(profit_target, 2), round(risk_reward_ratio, 2)

