import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging
import time

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class StockAnalyzer:
    def __init__(self, symbol):
        """
        Initialize the Stock Analyzer with a stock symbol
        
        Args:
            symbol (str): Stock ticker symbol (e.g., 'AAPL', 'GOOGL')
        """
        self.symbol = symbol.upper()
        self.data = None
        self.ticker_info = None
        logger.info(f"Initialized StockAnalyzer for {self.symbol}")
        
    def fetch_data(self, period='1y'):
        """
        Fetch live stock data from Yahoo Finance
        
        Args:
            period (str): Data period (default: '1y' for 1 year)
        """
        start_time = time.time()
        try:
            logger.info(f"Fetching data for {self.symbol}...")
            stock = yf.Ticker(self.symbol)
            
            fetch_start = time.time()
            self.data = stock.history(period=period)
            fetch_time = time.time() - fetch_start
            logger.info(f"Data fetch completed in {fetch_time:.2f}s")
            
            info_start = time.time()
            self.ticker_info = stock.info
            info_time = time.time() - info_start
            logger.info(f"Ticker info fetch completed in {info_time:.2f}s")
            
            if self.data.empty:
                raise ValueError(f"No data found for symbol: {self.symbol}")
            
            total_time = time.time() - start_time
            logger.info(f"✓ Successfully fetched data for {self.symbol} (Total: {total_time:.2f}s)")
            return True
        except Exception as e:
            total_time = time.time() - start_time
            logger.error(f"✗ Error fetching data for {self.symbol} after {total_time:.2f}s: {e}")
            return False
    
    def calculate_ema(self, period):
        """
        Calculate Exponential Moving Average
        
        Args:
            period (int): Number of days for EMA calculation
            
        Returns:
            float: Current EMA value
        """
        if self.data is None or self.data.empty:
            return None
        
        ema = self.data['Close'].ewm(span=period, adjust=False).mean()
        return round(ema.iloc[-1], 2)
    
    def calculate_rsi(self, period=14):
        """
        Calculate Relative Strength Index
        
        Args:
            period (int): RSI period (default: 14 days)
            
        Returns:
            float: Current RSI value
        """
        if self.data is None or self.data.empty:
            return None
        
        # Calculate price changes
        delta = self.data['Close'].diff()
        
        # Separate gains and losses
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        
        # Calculate RS and RSI
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        
        return round(rsi.iloc[-1], 2)
    
    def calculate_stochastic(self, k_period=8, d_period=3):
        """
        Calculate Slow Stochastic Oscillator
        
        Args:
            k_period (int): Period for %K calculation (default: 8)
            d_period (int): Period for %D smoothing (default: 3)
            
        Returns:
            tuple: (%K, %D) values
        """
        if self.data is None or self.data.empty:
            return None, None
        
        # Calculate %K (Fast Stochastic)
        low_min = self.data['Low'].rolling(window=k_period).min()
        high_max = self.data['High'].rolling(window=k_period).max()
        
        k_fast = 100 * (self.data['Close'] - low_min) / (high_max - low_min)
        
        # Smooth %K to get Slow Stochastic %K
        k_slow = k_fast.rolling(window=d_period).mean()
        
        # Calculate %D (signal line - moving average of %K)
        d_slow = k_slow.rolling(window=d_period).mean()
        
        return round(k_slow.iloc[-1], 2), round(d_slow.iloc[-1], 2)
    
    def calculate_adx(self, period=13):
        """
        Calculate Average Directional Index (ADX)
        
        Args:
            period (int): ADX period (default: 13)
            
        Returns:
            float: Current ADX value
        """
        if self.data is None or self.data.empty:
            return None
        
        high = self.data['High']
        low = self.data['Low']
        close = self.data['Close']
        
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
        plus_dm = pd.Series(plus_dm, index=self.data.index)
        minus_dm = pd.Series(minus_dm, index=self.data.index)
        
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
    
    def get_current_price(self):
        """
        Get the current/latest closing price
        
        Returns:
            float: Current price
        """
        if self.data is None or self.data.empty:
            return None
        
        return round(self.data['Close'].iloc[-1], 2)
    
    def check_earnings_date(self):
        """
        Check if earnings are scheduled in the next two weeks
        
        Returns:
            tuple: (bool, str) - Has upcoming earnings, date string
        """
        try:
            if self.ticker_info is None:
                return None, "Unable to fetch earnings data"
            
            # Try to get earnings date
            earnings_date = self.ticker_info.get('earningsDate')
            
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
    
    def check_ema_stacking_bullish(self):
        """
        Check if EMAs are stacked in bullish fashion:
        8 EMA > 21 EMA > 34 EMA > 55 EMA > 89 EMA
        
        Returns:
            tuple: (bool, dict) - Is stacked bullishly, EMA values
        """
        if self.data is None or self.data.empty:
            return False, {}
        
        ema_8 = self.calculate_ema(8)
        ema_21 = self.calculate_ema(21)
        ema_34 = self.calculate_ema(34)
        ema_55 = self.calculate_ema(55)
        ema_89 = self.calculate_ema(89)
        
        emas = {
            'ema_8': ema_8,
            'ema_21': ema_21,
            'ema_34': ema_34,
            'ema_55': ema_55,
            'ema_89': ema_89
        }
        
        is_stacked = (ema_8 > ema_21 > ema_34 > ema_55 > ema_89)
        
        return is_stacked, emas
    
    def check_ema_stacking_bearish(self):
        """
        Check if EMAs are stacked in bearish fashion:
        8 EMA < 21 EMA < 34 EMA < 55 EMA < 89 EMA
        
        Returns:
            tuple: (bool, dict) - Is stacked bearishly, EMA values
        """
        if self.data is None or self.data.empty:
            return False, {}
        
        ema_8 = self.calculate_ema(8)
        ema_21 = self.calculate_ema(21)
        ema_34 = self.calculate_ema(34)
        ema_55 = self.calculate_ema(55)
        ema_89 = self.calculate_ema(89)
        
        emas = {
            'ema_8': ema_8,
            'ema_21': ema_21,
            'ema_34': ema_34,
            'ema_55': ema_55,
            'ema_89': ema_89
        }
        
        is_stacked = (ema_8 < ema_21 < ema_34 < ema_55 < ema_89)
        
        return is_stacked, emas
    
    def check_pullback_to_21ema(self, tolerance_percent=2):
        """
        Check if price has pulled back to 21 EMA
        
        Args:
            tolerance_percent (float): Tolerance percentage for pullback (default: 2%)
            
        Returns:
            tuple: (bool, float, float) - Is near 21 EMA, current price, 21 EMA
        """
        if self.data is None or self.data.empty:
            return False, None, None
        
        current_price = self.get_current_price()
        ema_21 = self.calculate_ema(21)
        
        # Check if price is within tolerance of 21 EMA
        tolerance = ema_21 * (tolerance_percent / 100)
        is_near = abs(current_price - ema_21) <= tolerance
        
        return is_near, current_price, ema_21
    
    def check_price_above_mas(self):
        """
        Check if price is above key moving averages: 20 EMA, 40 EMA, 200 EMA
        
        Returns:
            tuple: (bool, dict) - All above, individual checks
        """
        if self.data is None or self.data.empty:
            return False, {}
        
        current_price = self.get_current_price()
        ema_20 = self.calculate_ema(20)
        ema_40 = self.calculate_ema(40)
        ema_200 = self.calculate_ema(200)
        
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
    
    def check_ma_stacking_2040200(self):
        """
        Check if moving averages are stacked bullishly: 20 EMA > 40 EMA > 200 EMA
        
        Returns:
            tuple: (bool, dict) - Is stacked, EMA values
        """
        if self.data is None or self.data.empty:
            return False, {}
        
        ema_20 = self.calculate_ema(20)
        ema_40 = self.calculate_ema(40)
        ema_200 = self.calculate_ema(200)
        
        emas = {
            'ema_20': ema_20,
            'ema_40': ema_40,
            'ema_200': ema_200
        }
        
        is_stacked = (ema_20 > ema_40 > ema_200) if all([ema_20, ema_40, ema_200]) else False
        
        return is_stacked, emas
    
    def check_200ema_slope(self, lookback_days=5):
        """
        Check if 200 EMA is rising (positive slope)
        
        Args:
            lookback_days (int): Days to look back for slope calculation (default: 5)
            
        Returns:
            tuple: (bool, float, float) - Is rising, current EMA 200, previous EMA 200
        """
        if self.data is None or self.data.empty:
            return False, None, None
        
        ema_200_series = self.data['Close'].ewm(span=200, adjust=False).mean()
        
        if len(ema_200_series) < lookback_days + 1:
            return False, None, None
        
        current_ema_200 = ema_200_series.iloc[-1]
        previous_ema_200 = ema_200_series.iloc[-lookback_days - 1]
        
        is_rising = current_ema_200 > previous_ema_200
        
        return is_rising, round(current_ema_200, 2), round(previous_ema_200, 2)
    
    def check_price_not_extended(self, max_extension_percent=10):
        """
        Check if price is not extended more than max_extension_percent above 20 EMA
        
        Args:
            max_extension_percent (float): Maximum extension percentage (default: 10%)
            
        Returns:
            tuple: (bool, float) - Not extended, extension percentage
        """
        if self.data is None or self.data.empty:
            return False, None
        
        current_price = self.get_current_price()
        ema_20 = self.calculate_ema(20)
        
        if not ema_20:
            return False, None
        
        extension_percent = ((current_price - ema_20) / ema_20) * 100
        is_not_extended = extension_percent <= max_extension_percent
        
        return is_not_extended, round(extension_percent, 2)
    
    def get_52_week_high(self):
        """
        Get 52-week high price
        
        Returns:
            float: 52-week high
        """
        if self.data is None or self.data.empty:
            return None
        
        # Look at last 252 trading days (approximately 1 year)
        lookback = min(252, len(self.data))
        high_52w = self.data['High'].iloc[-lookback:].max()
        
        return round(high_52w, 2)
    
    def check_proximity_to_52w_high(self, max_distance_percent=20):
        """
        Check if price is within max_distance_percent of 52-week high
        
        Args:
            max_distance_percent (float): Maximum distance from 52w high (default: 20%)
            
        Returns:
            tuple: (bool, float, float) - Within range, 52w high, distance percentage
        """
        if self.data is None or self.data.empty:
            return False, None, None
        
        current_price = self.get_current_price()
        high_52w = self.get_52_week_high()
        
        if not high_52w:
            return False, None, None
        
        distance_percent = ((high_52w - current_price) / high_52w) * 100
        within_range = distance_percent <= max_distance_percent
        
        return within_range, high_52w, round(distance_percent, 2)
    
    def analyze(self):
        """
        Perform complete analysis and return all indicators
        
        Returns:
            dict: Dictionary containing all calculated indicators
        """
        if not self.fetch_data():
            return None
        
        current_price = self.get_current_price()
        
        # Get EMA stacking (original criteria)
        is_bullish_stacked, emas = self.check_ema_stacking_bullish()
        is_bearish_stacked, _ = self.check_ema_stacking_bearish()
        
        # Get 20/40/200 EMA stacking (additional criteria)
        is_2040200_stacked, ma_checks = self.check_ma_stacking_2040200()
        price_above_mas, above_ma_checks = self.check_price_above_mas()
        
        # Check 200 EMA slope
        ema_200_rising, current_200, prev_200 = self.check_200ema_slope()
        
        # Get other indicators
        rsi = self.calculate_rsi()
        stoch_k, stoch_d = self.calculate_stochastic(8, 3)
        adx = self.calculate_adx(13)
        adx_14 = self.calculate_adx(14)  # Additional ADX with 14 period
        
        # Check pullback
        near_21ema, _, ema_21 = self.check_pullback_to_21ema()
        
        # Check price extension
        not_extended, extension_pct = self.check_price_not_extended(10)
        
        # Check 52-week high proximity
        near_52w_high, high_52w, distance_52w = self.check_proximity_to_52w_high(20)
        
        # Check earnings
        has_earnings, earnings_info = self.check_earnings_date()
        
        return {
            'symbol': self.symbol,
            'current_price': current_price,
            # Original EMAs (8, 21, 34, 55, 89)
            'ema_8': emas.get('ema_8'),
            'ema_21': emas.get('ema_21'),
            'ema_34': emas.get('ema_34'),
            'ema_55': emas.get('ema_55'),
            'ema_89': emas.get('ema_89'),
            # Additional EMAs (20, 40, 200)
            'ema_20': above_ma_checks.get('ema_20'),
            'ema_40': above_ma_checks.get('ema_40'),
            'ema_200': above_ma_checks.get('ema_200'),
            # Indicators
            'rsi': rsi,
            'stoch_k': stoch_k,
            'stoch_d': stoch_d,
            'adx': adx,
            'adx_14': adx_14,
            # Stacking checks
            'is_bullish_stacked': is_bullish_stacked,
            'is_bearish_stacked': is_bearish_stacked,
            'is_2040200_stacked': is_2040200_stacked,
            # Price above MAs
            'price_above_20': above_ma_checks.get('above_20'),
            'price_above_40': above_ma_checks.get('above_40'),
            'price_above_200': above_ma_checks.get('above_200'),
            'price_above_all_mas': price_above_mas,
            # 200 EMA slope
            'ema_200_rising': ema_200_rising,
            'ema_200_current': current_200,
            'ema_200_previous': prev_200,
            # Price conditions
            'near_21ema': near_21ema,
            'not_extended': not_extended,
            'extension_percent': extension_pct,
            # 52-week high
            'high_52w': high_52w,
            'near_52w_high': near_52w_high,
            'distance_from_52w_high': distance_52w,
            # Earnings
            'has_upcoming_earnings': has_earnings,
            'earnings_info': earnings_info,
            'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
    
    def calculate_support_resistance(self, lookback_days=60, num_levels=3):
        """
        Calculate support and resistance levels using historical price data
        
        Args:
            lookback_days (int): Number of days to look back (default: 60)
            num_levels (int): Number of S/R levels to identify (default: 3)
            
        Returns:
            dict: Support and resistance levels with additional data
        """
        start_time = time.time()
        logger.info(f"Calculating support/resistance for {self.symbol}...")
        
        try:
            if self.data is None or self.data.empty:
                return {'error': 'No data available'}
            
            # Get recent data for analysis
            recent_data = self.data.tail(lookback_days).copy()
            current_price = recent_data['Close'].iloc[-1]
            
            # Method 1: Find pivot highs and lows
            highs = []
            lows = []
            window = 5  # Look for pivots with 5-day window
            
            for i in range(window, len(recent_data) - window):
                # Check if it's a pivot high
                if recent_data['High'].iloc[i] == recent_data['High'].iloc[i-window:i+window+1].max():
                    highs.append(recent_data['High'].iloc[i])
                
                # Check if it's a pivot low
                if recent_data['Low'].iloc[i] == recent_data['Low'].iloc[i-window:i+window+1].min():
                    lows.append(recent_data['Low'].iloc[i])
            
            # Method 2: Calculate pivot points (classic method)
            latest_high = recent_data['High'].iloc[-1]
            latest_low = recent_data['Low'].iloc[-1]
            latest_close = recent_data['Close'].iloc[-1]
            
            pivot = (latest_high + latest_low + latest_close) / 3
            
            # Calculate support and resistance levels using pivot points
            r1 = 2 * pivot - latest_low
            r2 = pivot + (latest_high - latest_low)
            r3 = r1 + (latest_high - latest_low)
            
            s1 = 2 * pivot - latest_high
            s2 = pivot - (latest_high - latest_low)
            s3 = s1 - (latest_high - latest_low)
            
            # Method 3: Cluster analysis of historical levels
            # Group similar price levels together
            def cluster_levels(levels, tolerance=0.02):
                """Cluster similar price levels within tolerance"""
                if not levels:
                    return []
                
                levels = sorted(levels)
                clusters = []
                current_cluster = [levels[0]]
                
                for level in levels[1:]:
                    if abs(level - np.mean(current_cluster)) / np.mean(current_cluster) < tolerance:
                        current_cluster.append(level)
                    else:
                        clusters.append(np.mean(current_cluster))
                        current_cluster = [level]
                
                clusters.append(np.mean(current_cluster))
                return clusters
            
            # Cluster the pivot points
            resistance_clusters = cluster_levels(highs)
            support_clusters = cluster_levels(lows)
            
            # Get top resistance levels (above current price)
            resistance_above = [r for r in resistance_clusters if r > current_price]
            resistance_above = sorted(resistance_above)[:num_levels] if resistance_above else []
            
            # Get top support levels (below current price)
            support_below = [s for s in support_clusters if s < current_price]
            support_below = sorted(support_below, reverse=True)[:num_levels] if support_below else []
            
            # Calculate distances
            def calc_distance(level):
                return round(((level - current_price) / current_price) * 100, 2)
            
            # Add pivot-based levels if cluster analysis didn't find enough
            pivot_resistance = sorted([r for r in [r1, r2, r3] if r > current_price])
            pivot_support = sorted([s for s in [s1, s2, s3] if s < current_price], reverse=True)
            
            # Combine methods: use cluster analysis first, then fill with pivot points
            final_resistance = resistance_above if len(resistance_above) >= num_levels else resistance_above + pivot_resistance
            final_support = support_below if len(support_below) >= num_levels else support_below + pivot_support
            
            # Limit to requested number of levels
            final_resistance = final_resistance[:num_levels]
            final_support = final_support[:num_levels]
            
            # Calculate 52-week high/low as major S/R levels
            high_52w = recent_data['High'].max()
            low_52w = recent_data['Low'].min()
            
            calc_time = time.time() - start_time
            logger.info(f"Support/Resistance calculation completed in {calc_time:.2f}s")
            
            result = {
                'current_price': round(current_price, 2),
                'pivot_point': round(pivot, 2),
                
                # Resistance levels (sorted nearest to farthest)
                'resistance_levels': [round(r, 2) for r in final_resistance],
                'resistance_distances': [f"{calc_distance(r):+.2f}%" for r in final_resistance],
                
                # Support levels (sorted nearest to farthest)
                'support_levels': [round(s, 2) for s in final_support],
                'support_distances': [f"{calc_distance(s):+.2f}%" for s in final_support],
                
                # Major levels
                '52_week_high': round(high_52w, 2),
                '52_week_low': round(low_52w, 2),
                '52w_high_distance': f"{calc_distance(high_52w):+.2f}%",
                '52w_low_distance': f"{calc_distance(low_52w):+.2f}%",
                
                # Nearest levels
                'nearest_resistance': round(final_resistance[0], 2) if final_resistance else None,
                'nearest_support': round(final_support[0], 2) if final_support else None,
                
                # Analysis metadata
                'lookback_days': lookback_days,
                'calculation_time': f"{calc_time:.2f}s"
            }
            
            return result
            
        except Exception as e:
            calc_time = time.time() - start_time
            logger.error(f"Error calculating S/R for {self.symbol} after {calc_time:.2f}s: {e}")
            return {'error': str(e)}
    
    def calculate_risk_management(self, strategy_type, sr_data, analysis):
        """
        Calculate comprehensive risk management including stop-loss, take-profit, and trailing stops
        
        Args:
            strategy_type (str): 'CALL' or 'PUT'
            sr_data (dict): Support/resistance data from calculate_support_resistance()
            analysis (dict): Full analysis data
            
        Returns:
            dict: Risk management parameters including stops, targets, and trailing stop rules
        """
        start_time = time.time()
        logger.info(f"Calculating risk management for {strategy_type} options on {self.symbol}...")
        
        try:
            current_price = analysis['current_price']
            
            if strategy_type == 'CALL':
                # === CALL OPTIONS RISK MANAGEMENT ===
                
                # 1. Initial Stop-Loss (for underlying stock price)
                # Use nearest support level or 21 EMA, whichever is closer
                support_levels = sr_data.get('support_levels', [])
                nearest_support = support_levels[0] if support_levels else None
                ema_21 = analysis.get('ema_21')
                
                # Choose the tighter stop (closer to current price for better risk management)
                if nearest_support and ema_21:
                    initial_stop = max(nearest_support, ema_21)
                    stop_reason = f"Support level ${nearest_support}" if initial_stop == nearest_support else f"21 EMA ${ema_21}"
                elif nearest_support:
                    initial_stop = nearest_support
                    stop_reason = f"Support level ${nearest_support}"
                elif ema_21:
                    initial_stop = ema_21
                    stop_reason = f"21 EMA ${ema_21}"
                else:
                    # Fallback: 5% below current price
                    initial_stop = current_price * 0.95
                    stop_reason = "5% below entry"
                
                # For options: Typically use -25% to -50% of option premium as stop
                option_stop_loss_percent = 30  # Lose max 30% of option premium
                
                # 2. Take-Profit Targets
                resistance_levels = sr_data.get('resistance_levels', [])
                
                targets = []
                if len(resistance_levels) >= 3:
                    targets = [
                        {
                            'level': 1,
                            'price': resistance_levels[0],
                            'distance': f"{((resistance_levels[0] - current_price) / current_price * 100):.2f}%",
                            'action': 'Take 33% profit',
                            'option_gain': '50-100%'
                        },
                        {
                            'level': 2,
                            'price': resistance_levels[1],
                            'distance': f"{((resistance_levels[1] - current_price) / current_price * 100):.2f}%",
                            'action': 'Take 33% profit',
                            'option_gain': '100-200%'
                        },
                        {
                            'level': 3,
                            'price': resistance_levels[2],
                            'distance': f"{((resistance_levels[2] - current_price) / current_price * 100):.2f}%",
                            'action': 'Close remaining position',
                            'option_gain': '200%+'
                        }
                    ]
                elif len(resistance_levels) >= 1:
                    # Use available resistance levels and calculate others
                    for i, r in enumerate(resistance_levels):
                        targets.append({
                            'level': i + 1,
                            'price': r,
                            'distance': f"{((r - current_price) / current_price * 100):.2f}%",
                            'action': 'Take profit' if i == len(resistance_levels) - 1 else 'Partial profit',
                            'option_gain': f"{50 * (i + 1)}-{100 * (i + 1)}%"
                        })
                else:
                    # Calculate based on percentages if no resistance found
                    targets = [
                        {'level': 1, 'price': round(current_price * 1.03, 2), 'distance': '+3%', 'action': 'Take 33%', 'option_gain': '50-100%'},
                        {'level': 2, 'price': round(current_price * 1.05, 2), 'distance': '+5%', 'action': 'Take 33%', 'option_gain': '100-200%'},
                        {'level': 3, 'price': round(current_price * 1.08, 2), 'distance': '+8%', 'action': 'Close all', 'option_gain': '200%+'}
                    ]
                
                # 3. Trailing Stop Rules
                trailing_stops = [
                    {
                        'trigger': 'Option profit reaches 50%',
                        'action': 'Move stop to breakeven (entry price)',
                        'new_stop_price': current_price,
                        'reason': 'Lock in risk-free trade'
                    },
                    {
                        'trigger': 'Option profit reaches 100%',
                        'action': 'Move stop to lock 50% profit',
                        'new_stop_price': nearest_support if nearest_support and nearest_support > current_price * 1.01 else round(current_price * 1.02, 2),
                        'reason': 'Protect 50% gains'
                    },
                    {
                        'trigger': 'Option profit reaches 200%',
                        'action': 'Trail stop at 34 EMA',
                        'new_stop_price': analysis.get('ema_34'),
                        'reason': 'Let winners run while protecting major gains'
                    }
                ]
                
                risk_reward_ratio = ((targets[0]['price'] - current_price) / (current_price - initial_stop)) if initial_stop < current_price else 0
                
                return {
                    'strategy': 'BUY CALL OPTIONS',
                    'entry_zone': {
                        'price': current_price,
                        'ideal_entry': f"${current_price} - ${round(current_price * 1.01, 2)}",
                        'max_entry': f"${round(current_price * 1.02, 2)} (if strong momentum)"
                    },
                    'stop_loss': {
                        'stock_price_stop': round(initial_stop, 2),
                        'stop_distance': f"-{((current_price - initial_stop) / current_price * 100):.2f}%",
                        'stop_reason': stop_reason,
                        'option_stop': f"-{option_stop_loss_percent}% of option premium",
                        'action': f"Exit if stock closes below ${round(initial_stop, 2)} OR option loses {option_stop_loss_percent}%"
                    },
                    'take_profit_targets': targets,
                    'trailing_stops': trailing_stops,
                    'risk_reward_ratio': f"1:{round(risk_reward_ratio, 2)}",
                    'position_sizing': {
                        'max_risk_per_trade': '2-3% of account',
                        'suggested_allocation': 'Start with 1/3 position, add on confirmation',
                        'max_option_risk': f"Risk only {option_stop_loss_percent}% of premium (${option_stop_loss_percent} per $100 invested)"
                    },
                    'calculation_time': f"{time.time() - start_time:.2f}s"
                }
                
            elif strategy_type == 'PUT':
                # === PUT OPTIONS RISK MANAGEMENT ===
                
                # 1. Initial Stop-Loss (for underlying stock price)
                # Use nearest resistance level or 21 EMA, whichever is closer
                resistance_levels = sr_data.get('resistance_levels', [])
                nearest_resistance = resistance_levels[0] if resistance_levels else None
                ema_21 = analysis.get('ema_21')
                
                # Choose the tighter stop (closer to current price)
                if nearest_resistance and ema_21:
                    initial_stop = min(nearest_resistance, ema_21)
                    stop_reason = f"Resistance level ${nearest_resistance}" if initial_stop == nearest_resistance else f"21 EMA ${ema_21}"
                elif nearest_resistance:
                    initial_stop = nearest_resistance
                    stop_reason = f"Resistance level ${nearest_resistance}"
                elif ema_21:
                    initial_stop = ema_21
                    stop_reason = f"21 EMA ${ema_21}"
                else:
                    # Fallback: 5% above current price
                    initial_stop = current_price * 1.05
                    stop_reason = "5% above entry"
                
                option_stop_loss_percent = 30  # Lose max 30% of option premium
                
                # 2. Take-Profit Targets
                support_levels = sr_data.get('support_levels', [])
                
                targets = []
                if len(support_levels) >= 3:
                    targets = [
                        {
                            'level': 1,
                            'price': support_levels[0],
                            'distance': f"{((current_price - support_levels[0]) / current_price * 100):.2f}%",
                            'action': 'Take 33% profit',
                            'option_gain': '50-100%'
                        },
                        {
                            'level': 2,
                            'price': support_levels[1],
                            'distance': f"{((current_price - support_levels[1]) / current_price * 100):.2f}%",
                            'action': 'Take 33% profit',
                            'option_gain': '100-200%'
                        },
                        {
                            'level': 3,
                            'price': support_levels[2],
                            'distance': f"{((current_price - support_levels[2]) / current_price * 100):.2f}%",
                            'action': 'Close remaining position',
                            'option_gain': '200%+'
                        }
                    ]
                elif len(support_levels) >= 1:
                    for i, s in enumerate(support_levels):
                        targets.append({
                            'level': i + 1,
                            'price': s,
                            'distance': f"{((current_price - s) / current_price * 100):.2f}%",
                            'action': 'Take profit' if i == len(support_levels) - 1 else 'Partial profit',
                            'option_gain': f"{50 * (i + 1)}-{100 * (i + 1)}%"
                        })
                else:
                    # Calculate based on percentages
                    targets = [
                        {'level': 1, 'price': round(current_price * 0.97, 2), 'distance': '-3%', 'action': 'Take 33%', 'option_gain': '50-100%'},
                        {'level': 2, 'price': round(current_price * 0.95, 2), 'distance': '-5%', 'action': 'Take 33%', 'option_gain': '100-200%'},
                        {'level': 3, 'price': round(current_price * 0.92, 2), 'distance': '-8%', 'action': 'Close all', 'option_gain': '200%+'}
                    ]
                
                # 3. Trailing Stop Rules for PUT options
                trailing_stops = [
                    {
                        'trigger': 'Option profit reaches 50%',
                        'action': 'Move stop to breakeven (entry price)',
                        'new_stop_price': current_price,
                        'reason': 'Lock in risk-free trade'
                    },
                    {
                        'trigger': 'Option profit reaches 100%',
                        'action': 'Move stop to lock 50% profit',
                        'new_stop_price': nearest_resistance if nearest_resistance and nearest_resistance < current_price * 0.99 else round(current_price * 0.98, 2),
                        'reason': 'Protect 50% gains'
                    },
                    {
                        'trigger': 'Option profit reaches 200%',
                        'action': 'Trail stop at 34 EMA',
                        'new_stop_price': analysis.get('ema_34'),
                        'reason': 'Let winners run while protecting major gains'
                    }
                ]
                
                risk_reward_ratio = ((current_price - targets[0]['price']) / (initial_stop - current_price)) if initial_stop > current_price else 0
                
                return {
                    'strategy': 'BUY PUT OPTIONS',
                    'entry_zone': {
                        'price': current_price,
                        'ideal_entry': f"${round(current_price * 0.99, 2)} - ${current_price}",
                        'max_entry': f"${round(current_price * 0.98, 2)} (if strong breakdown)"
                    },
                    'stop_loss': {
                        'stock_price_stop': round(initial_stop, 2),
                        'stop_distance': f"+{((initial_stop - current_price) / current_price * 100):.2f}%",
                        'stop_reason': stop_reason,
                        'option_stop': f"-{option_stop_loss_percent}% of option premium",
                        'action': f"Exit if stock closes above ${round(initial_stop, 2)} OR option loses {option_stop_loss_percent}%"
                    },
                    'take_profit_targets': targets,
                    'trailing_stops': trailing_stops,
                    'risk_reward_ratio': f"1:{round(risk_reward_ratio, 2)}",
                    'position_sizing': {
                        'max_risk_per_trade': '2-3% of account',
                        'suggested_allocation': 'Start with 1/3 position, add on confirmation',
                        'max_option_risk': f"Risk only {option_stop_loss_percent}% of premium (${option_stop_loss_percent} per $100 invested)"
                    },
                    'calculation_time': f"{time.time() - start_time:.2f}s"
                }
            
            else:
                return {'error': 'Invalid strategy type. Use CALL or PUT.'}
                
        except Exception as e:
            calc_time = time.time() - start_time
            logger.error(f"Error calculating risk management for {self.symbol} after {calc_time:.2f}s: {e}")
            return {'error': str(e)}

    def identify_trend(self):
        """
        Identify if stock is in UPTREND or DOWNTREND and provide options trading recommendation
        
        BULLISH CRITERIA (BUY CALL OPTIONS):
        1. EMAs stacked bullishly (8>21>34>55>89)
        2. Price pulled back to 21 EMA (within 2%)
        3. Slow Stochastic %K <= 40 (pullback)
        4. ADX(13) >= 20 (trend strength)
        5. No earnings in next 2 weeks
        
        BEARISH CRITERIA (BUY PUT OPTIONS):
        1. EMAs stacked bearishly (8<21<34<55<89)
        2. Price rejected from 21 EMA (resistance)
        3. Slow Stochastic %K >= 60 (overbought in downtrend)
        4. ADX(13) >= 20 (trend strength)
        5. No earnings in next 2 weeks
        
        Additional Enhanced Criteria for both directions
        
        Returns:
            tuple: (str, list, dict, dict) - Trend type, reasons, additional checks, analysis data
        """
        start_time = time.time()
        logger.info(f"Starting trend analysis for {self.symbol}...")
        
        analysis = self.analyze()
        
        if analysis is None:
            return "UNKNOWN", ["Unable to fetch data"], None
        
        reasons = []
        additional_checks = []
        trend = "NEUTRAL"
        
        # ===== ORIGINAL 5 CRITERIA =====
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
        
        # ===== ADDITIONAL ENHANCED CRITERIA =====
        
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
        
        # 9. RSI filter
        rsi = analysis.get('rsi')
        rsi_40_condition = rsi is not None and rsi > 40
        rsi_50_condition = rsi is not None and rsi > 50
        if rsi_50_condition:
            additional_checks.append(f"✓✓ RSI > 50 (strong momentum: {rsi})")
        elif rsi_40_condition:
            additional_checks.append(f"✓ RSI > 40 (minimum momentum: {rsi})")
        else:
            additional_checks.append(f"✗ RSI <= 40 (weak momentum: {rsi})")
        
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
        
        # ===== BEARISH CRITERIA (For PUT OPTIONS) =====
        
        is_bearish_stacked = analysis['is_bearish_stacked']
        
        # Bearish criteria checks
        bearish_ema_stacked = is_bearish_stacked
        bearish_price_condition = not near_21ema and analysis['current_price'] < analysis['ema_21']
        bearish_stoch_condition = stoch_k is not None and stoch_k >= 60
        bearish_adx_condition = adx_13 is not None and adx_13 >= 20
        bearish_no_earnings = not has_earnings
        
        # Count bearish criteria
        bearish_criteria_met = sum([
            bearish_ema_stacked,
            bearish_price_condition,
            bearish_stoch_condition,
            bearish_adx_condition,
            bearish_no_earnings
        ])
        
        # ===== DETERMINE TREND & OPTIONS STRATEGY =====
        
        # Count how many original bullish criteria are met
        original_criteria_met = sum([
            ema_stacked,
            pullback_condition,
            stoch_condition,
            adx_13_condition,
            no_earnings
        ])
        
        # Count how many additional criteria are met
        additional_criteria_met = sum([
            price_above_all,
            ma_stacked,
            ema_200_rising,
            rsi_40_condition,
            adx_14_condition,
            not_extended,
            near_52w
        ])
        
        options_recommendation = {}
        
        # Priority: Check bearish first, then bullish, then neutral
        if bearish_criteria_met >= 4:
            # Strong bearish signal - PUT OPTIONS
            if bearish_criteria_met == 5:
                trend = "STRONG BEARISH - PUT OPTIONS SIGNAL"
                options_recommendation = {
                    'strategy': 'BUY PUT OPTIONS',
                    'confidence': 'HIGH',
                    'reasoning': f'All {bearish_criteria_met}/5 bearish criteria met',
                    'entry': 'Good entry point for PUT options',
                    'risk': 'Place stop loss above recent swing high'
                }
            else:
                trend = "BEARISH TREND - PUT OPTIONS CONSIDERATION"
                options_recommendation = {
                    'strategy': 'BUY PUT OPTIONS',
                    'confidence': 'MODERATE',
                    'reasoning': f'{bearish_criteria_met}/5 bearish criteria met',
                    'entry': 'Consider PUT options with caution',
                    'risk': 'Monitor for reversal signals'
                }
            
            # Add bearish reasons
            reasons.append(f"\n🔻 BEARISH CRITERIA:")
            if bearish_ema_stacked:
                reasons.append(f"✓ EMAs stacked bearishly (8<21<34<55<89)")
            else:
                reasons.append(f"✗ EMAs NOT stacked bearishly")
            
            if bearish_price_condition:
                reasons.append(f"✓ Price below 21 EMA resistance (${analysis['current_price']} < ${analysis['ema_21']})")
            else:
                reasons.append(f"✗ Price not below 21 EMA")
            
            if bearish_stoch_condition:
                reasons.append(f"✓ Stochastic %K >= 60 (%K: {stoch_k})")
            else:
                reasons.append(f"✗ Stochastic %K < 60 (%K: {stoch_k})")
            
            if bearish_adx_condition:
                reasons.append(f"✓ Strong trend ADX(13) >= 20 (ADX: {adx_13})")
            else:
                reasons.append(f"✗ Weak trend ADX(13) < 20 (ADX: {adx_13})")
            
            if bearish_no_earnings:
                reasons.append(f"✓ No earnings in next 2 weeks")
            else:
                reasons.append(f"✗ CAUTION: {analysis['earnings_info']}")
            
        elif original_criteria_met >= 4:
            # Strong bullish signal - CALL OPTIONS
            if original_criteria_met == 5:
                if additional_criteria_met >= 5:
                    trend = "STRONG BULLISH - CALL OPTIONS SIGNAL"
                    options_recommendation = {
                        'strategy': 'BUY CALL OPTIONS',
                        'confidence': 'VERY HIGH',
                        'reasoning': f'All 5/5 bullish criteria + {additional_criteria_met}/7 enhanced criteria met',
                        'entry': 'Excellent entry point for CALL options',
                        'risk': 'Place stop loss below 21 EMA'
                    }
                else:
                    trend = "BULLISH - CALL OPTIONS SIGNAL"
                    options_recommendation = {
                        'strategy': 'BUY CALL OPTIONS',
                        'confidence': 'HIGH',
                        'reasoning': f'All 5/5 bullish criteria met',
                        'entry': 'Good entry point for CALL options',
                        'risk': 'Place stop loss below 21 EMA'
                    }
            else:
                trend = "BULLISH TREND - CALL OPTIONS CONSIDERATION"
                options_recommendation = {
                    'strategy': 'BUY CALL OPTIONS',
                    'confidence': 'MODERATE',
                    'reasoning': f'{original_criteria_met}/5 bullish criteria met',
                    'entry': 'Consider CALL options with caution',
                    'risk': 'Wait for better pullback or confirmation'
                }
        
        elif ema_stacked and original_criteria_met >= 3:
            # In uptrend but not ideal entry
            trend = "BULLISH STRUCTURE - WAIT FOR ENTRY"
            options_recommendation = {
                'strategy': 'WAIT - CALL OPTIONS SETUP',
                'confidence': 'LOW',
                'reasoning': 'Bullish structure but missing entry signals',
                'entry': 'Wait for pullback to 21 EMA and Stochastic <= 40',
                'risk': 'Don\'t chase - wait for proper setup'
            }
        
        elif is_bearish_stacked and bearish_criteria_met >= 3:
            # Bearish structure developing
            trend = "BEARISH STRUCTURE - MONITOR FOR PUT ENTRY"
            options_recommendation = {
                'strategy': 'MONITOR - PUT OPTIONS SETUP',
                'confidence': 'LOW',
                'reasoning': f'Bearish structure with {bearish_criteria_met}/5 criteria',
                'entry': 'Monitor for full bearish confirmation',
                'risk': 'Wait for all criteria before entering'
            }
        
        else:
            # No clear trend
            trend = "NO CLEAR TREND - NO OPTIONS TRADE"
            options_recommendation = {
                'strategy': 'NO TRADE',
                'confidence': 'N/A',
                'reasoning': 'Mixed signals, no clear bullish or bearish trend',
                'entry': 'Stay on sidelines until clear trend emerges',
                'risk': 'Avoid trading in choppy/sideways markets'
            }
        
        # Add scoring summary
        reasons.append(f"\n📊 Criteria Score: BULLISH {original_criteria_met}/5 | BEARISH {bearish_criteria_met}/5 | Enhanced {additional_criteria_met}/7")
        
        # Calculate support/resistance levels
        logger.info(f"Calculating support/resistance levels for {self.symbol}...")
        sr_data = self.calculate_support_resistance()
        
        # Calculate risk management if we have a CALL or PUT recommendation
        risk_management = None
        if "CALL" in trend or "BULLISH" in trend:
            risk_management = self.calculate_risk_management('CALL', sr_data, analysis)
        elif "PUT" in trend or "BEARISH" in trend:
            risk_management = self.calculate_risk_management('PUT', sr_data, analysis)
        
        # Add options recommendation, S/R data, and risk management to analysis
        analysis['options_recommendation'] = options_recommendation
        analysis['support_resistance'] = sr_data
        analysis['risk_management'] = risk_management
        
        # Log completion
        total_time = time.time() - start_time
        logger.info(f"✓ Trend analysis completed for {self.symbol} in {total_time:.2f}s - Result: {trend}")
        logger.info(f"  Criteria met: Bullish {original_criteria_met}/5, Bearish {bearish_criteria_met}/5, Enhanced {additional_criteria_met}/7")
        
        return trend, reasons, additional_checks, analysis


def print_analysis(analyzer):
    """
    Print formatted analysis results with trend identification
    
    Args:
        analyzer (StockAnalyzer): Stock analyzer instance
    """
    print("\n" + "="*80)
    print(f"COMPREHENSIVE STOCK TREND ANALYSIS - {analyzer.symbol}")
    print("="*80)
    
    result = analyzer.identify_trend()
    
    # Handle both old and new return formats
    if len(result) == 4:
        trend, reasons, additional_checks, analysis = result
    else:
        trend, reasons, analysis = result
        additional_checks = []
    
    if analysis:
        print(f"\n📊 Current Data (as of {analysis['date']})")
        print(f"   Current Price: ${analysis['current_price']}")
        print(f"   52-Week High:  ${analysis.get('high_52w', 'N/A')}")
        
        print(f"\n📈 Original EMA Stack (8/21/34/55/89):")
        print(f"   8-Day EMA:   ${analysis['ema_8']}")
        print(f"   21-Day EMA:  ${analysis['ema_21']}")
        print(f"   34-Day EMA:  ${analysis['ema_34']}")
        print(f"   55-Day EMA:  ${analysis['ema_55']}")
        print(f"   89-Day EMA:  ${analysis['ema_89']}")
        
        print(f"\n📊 Additional MAs (20/40/200):")
        print(f"   20-Day EMA:  ${analysis.get('ema_20', 'N/A')}")
        print(f"   40-Day EMA:  ${analysis.get('ema_40', 'N/A')}")
        print(f"   200-Day EMA: ${analysis.get('ema_200', 'N/A')}")
        
        print(f"\n📊 Technical Indicators:")
        print(f"   RSI (14):           {analysis['rsi']}")
        print(f"   Stochastic %K (8):  {analysis['stoch_k']}")
        print(f"   Stochastic %D (3):  {analysis['stoch_d']}")
        print(f"   ADX (13):           {analysis['adx']}")
        print(f"   ADX (14):           {analysis.get('adx_14', 'N/A')}")
        
        print(f"\n🔍 Original 5 Criteria Analysis:")
        for reason in reasons:
            print(f"   {reason}")
        
        if additional_checks:
            print(f"\n🔍 Enhanced Criteria Analysis:")
            for check in additional_checks:
                print(f"   {check}")
        
        print(f"\n{'='*80}")
        
        # Display trend and options recommendation
        options_rec = analysis.get('options_recommendation', {})
        
        if "STRONG BULLISH" in trend or "CALL OPTIONS SIGNAL" in trend:
            print(f"📞 TREND: {trend}")
            print("   🎯 STRONG BULLISH SIGNAL - BUY CALL OPTIONS!")
            if options_rec.get('confidence') == 'VERY HIGH':
                print("   💪 VERY HIGH CONFIDENCE - Excellent risk/reward setup!")
            elif options_rec.get('confidence') == 'HIGH':
                print("   ✅ HIGH CONFIDENCE - Good entry point for CALL options")
        elif "BULLISH" in trend and "CALL" in trend:
            print(f"📞 TREND: {trend}")
            print("   📈 BULLISH SIGNAL - Consider CALL OPTIONS")
            print(f"   ⚠️  {options_rec.get('confidence', 'MODERATE')} confidence - {options_rec.get('reasoning', '')}")
        elif "STRONG BEARISH" in trend or "PUT OPTIONS SIGNAL" in trend:
            print(f"📉 TREND: {trend}")
            print("   🎯 STRONG BEARISH SIGNAL - BUY PUT OPTIONS!")
            if options_rec.get('confidence') == 'HIGH':
                print("   💪 HIGH CONFIDENCE - Good entry point for PUT options")
        elif "BEARISH" in trend and "PUT" in trend:
            print(f"📉 TREND: {trend}")
            print("   📊 BEARISH SIGNAL - Consider PUT OPTIONS")
            print(f"   ⚠️  {options_rec.get('confidence', 'MODERATE')} confidence - {options_rec.get('reasoning', '')}")
        elif "WAIT" in trend:
            print(f"⏳ TREND: {trend}")
            print("   ⌛ BULLISH STRUCTURE - Wait for proper entry signal")
            print("   � Don't chase - wait for pullback to 21 EMA")
        elif "MONITOR" in trend:
            print(f"👁️  TREND: {trend}")
            print("   📊 BEARISH STRUCTURE FORMING - Monitor for confirmation")
            print("   ⚠️  Wait for all bearish criteria before entering")
        elif "NO CLEAR TREND" in trend or "NO OPTIONS TRADE" in trend:
            print(f"⚪ TREND: {trend}")
            print("   🚫 NO TRADE RECOMMENDED")
            print("   ℹ️  Mixed signals - Stay on sidelines until clear trend emerges")
        else:
            print(f"⚪ TREND: {trend}")
            print("   ℹ️  No clear directional bias")
        
        print("="*80)
        
        # Display detailed options recommendation
        if options_rec:
            print(f"\n📋 OPTIONS TRADING RECOMMENDATION:")
            print(f"   Strategy:   {options_rec.get('strategy', 'N/A')}")
            print(f"   Confidence: {options_rec.get('confidence', 'N/A')}")
            print(f"   Reasoning:  {options_rec.get('reasoning', 'N/A')}")
            print(f"   Entry:      {options_rec.get('entry', 'N/A')}")
            print(f"   Risk:       {options_rec.get('risk', 'N/A')}")
            print("="*80)
        
        # Additional insights
        print("\n💡 Additional Insights:")
        
        # EMA relationship
        if analysis['is_bullish_stacked']:
            print("   • ✅ Perfect bullish EMA alignment - Strong uptrend structure")
        elif analysis['is_bearish_stacked']:
            print("   • ⚠️  Bearish EMA alignment - Downtrend structure")
        else:
            print("   • ⚪ EMAs are mixed - No clear trend")
        
        # RSI insights
        if analysis['rsi'] > 70:
            print("   • ⚠️  RSI indicates overbought conditions")
        elif analysis['rsi'] < 30:
            print("   • 💡 RSI indicates oversold conditions")
        else:
            print("   • ✓ RSI in neutral zone")
        
        # Stochastic insights
        if analysis['stoch_k'] <= 20:
            print("   • 💡 Stochastic in oversold zone - potential reversal")
        elif analysis['stoch_k'] >= 80:
            print("   • ⚠️  Stochastic in overbought zone")
        
        # ADX insights
        if analysis['adx'] and analysis['adx'] >= 25:
            print(f"   • ✅ Strong trend strength (ADX: {analysis['adx']})")
        elif analysis['adx'] and analysis['adx'] >= 20:
            print(f"   • ✓ Moderate trend strength (ADX: {analysis['adx']})")
        elif analysis['adx']:
            print(f"   • ⚠️  Weak trend (ADX: {analysis['adx']})")
        
        print("\n")
    else:
        print("Failed to analyze stock. Please check the symbol and try again.")


def main():
    """
    Main function to run the stock trend analyzer
    """
    print("\n" + "="*80)
    print("     📈 COMPREHENSIVE STOCK TREND ANALYZER 📈")
    print("="*80)
    print("\nThis tool identifies strong bullish stocks using:")
    print("\n🎯 Original 5 Criteria:")
    print("  • EMA stacking (8>21>34>55>89)")
    print("  • Pullback to 21 EMA (within 2%)")
    print("  • Slow Stochastic (8,3) <= 40")
    print("  • ADX (13) >= 20")
    print("  • No earnings in 2 weeks")
    print("\n💪 Enhanced Criteria:")
    print("  • Price above key MAs (20/40/200 EMA)")
    print("  • MA stacking (20>40>200)")
    print("  • 200 EMA rising (positive slope)")
    print("  • RSI > 40 (>50 preferred)")
    print("  • ADX(14) > 20 (>25 strong)")
    print("  • Price not extended (<=10% above 20 EMA)")
    print("  • Within 20% of 52-week high")
    print("\n")
    
    while True:
        # Get stock symbol from user
        symbol = input("Enter stock symbol (or 'quit' to exit): ").strip()
        
        if symbol.lower() in ['quit', 'exit', 'q']:
            print("\nThank you for using Stock Trend Analyzer! 👋\n")
            break
        
        if not symbol:
            print("Please enter a valid stock symbol.\n")
            continue
        
        # Analyze the stock
        analyzer = StockAnalyzer(symbol)
        print_analysis(analyzer)
        
        print("\n" + "-"*80 + "\n")


if __name__ == "__main__":
    main()
