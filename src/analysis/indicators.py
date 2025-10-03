"""
Technical Indicators Module

This module contains all technical indicator calculations:
- EMA (Exponential Moving Average)
- RSI (Relative Strength Index)
- Stochastic Oscillator
- ADX (Average Directional Index)
"""

import pandas as pd
import numpy as np


def calculate_ema(data, period):
    """
    Calculate Exponential Moving Average
    
    Args:
        data (pd.Series): Price data (typically Close prices)
        period (int): Number of days for EMA calculation
        
    Returns:
        float: Current EMA value
    """
    if data is None or data.empty:
        return None
    
    ema = data.ewm(span=period, adjust=False).mean()
    return round(ema.iloc[-1], 2)


def calculate_ema_series(data, period):
    """
    Calculate Exponential Moving Average series
    
    Args:
        data (pd.Series): Price data (typically Close prices)
        period (int): Number of days for EMA calculation
        
    Returns:
        pd.Series: EMA series
    """
    if data is None or data.empty:
        return None
    
    return data.ewm(span=period, adjust=False).mean()


def calculate_rsi(data, period=14):
    """
    Calculate Relative Strength Index
    
    Args:
        data (pd.Series): Price data (typically Close prices)
        period (int): RSI period (default: 14 days)
        
    Returns:
        float: Current RSI value
    """
    if data is None or data.empty:
        return None
    
    # Calculate price changes
    delta = data.diff()
    
    # Separate gains and losses
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    
    # Calculate RS and RSI
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    
    return round(rsi.iloc[-1], 2)


def calculate_stochastic(data, k_period=8, d_period=3):
    """
    Calculate Slow Stochastic Oscillator
    
    Args:
        data (pd.DataFrame): OHLC data with High, Low, Close columns
        k_period (int): Period for %K calculation (default: 8)
        d_period (int): Period for %D smoothing (default: 3)
        
    Returns:
        tuple: (%K, %D) values
    """
    if data is None or data.empty:
        return None, None
    
    # Calculate %K (Fast Stochastic)
    low_min = data['Low'].rolling(window=k_period).min()
    high_max = data['High'].rolling(window=k_period).max()
    
    k_fast = 100 * (data['Close'] - low_min) / (high_max - low_min)
    
    # Smooth %K to get Slow Stochastic %K
    k_slow = k_fast.rolling(window=d_period).mean()
    
    # Calculate %D (signal line - moving average of %K)
    d_slow = k_slow.rolling(window=d_period).mean()
    
    return round(k_slow.iloc[-1], 2), round(d_slow.iloc[-1], 2)


def calculate_adx(data, period=13):
    """
    Calculate Average Directional Index (ADX)
    
    Args:
        data (pd.DataFrame): OHLC data with High, Low, Close columns
        period (int): ADX period (default: 13)
        
    Returns:
        float: Current ADX value
    """
    if data is None or data.empty:
        return None
    
    high = data['High']
    low = data['Low']
    close = data['Close']
    
    # Calculate True Range (TR)
    tr1 = high - low
    tr2 = abs(high - close.shift())
    tr3 = abs(low - close.shift())
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    # Calculate Directional Movement
    up_move = high - high.shift()
    down_move = low.shift() - low
    
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)
    
    # Convert to Series with proper index
    plus_dm = pd.Series(plus_dm, index=data.index)
    minus_dm = pd.Series(minus_dm, index=data.index)
    
    # Smooth the values using Wilder's smoothing (EMA)
    alpha = 1.0 / period
    
    # Initialize smoothed values
    atr = tr.ewm(alpha=alpha, adjust=False).mean()
    plus_dm_smooth = plus_dm.ewm(alpha=alpha, adjust=False).mean()
    minus_dm_smooth = minus_dm.ewm(alpha=alpha, adjust=False).mean()
    
    # Calculate +DI and -DI
    plus_di = 100 * plus_dm_smooth / atr
    minus_di = 100 * minus_dm_smooth / atr
    
    # Calculate DX and ADX
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
    adx = dx.ewm(alpha=alpha, adjust=False).mean()
    
    return round(adx.iloc[-1], 2) if not pd.isna(adx.iloc[-1]) else None


def get_52_week_high(data):
    """
    Get 52-week high price
    
    Args:
        data (pd.DataFrame): OHLC data with High column
        
    Returns:
        float: 52-week high
    """
    if data is None or data.empty:
        return None
    
    # Look at last 252 trading days (approximately 1 year)
    lookback = min(252, len(data))
    high_52w = data['High'].iloc[-lookback:].max()
    
    return round(high_52w, 2)
