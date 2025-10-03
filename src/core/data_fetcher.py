"""
Data Fetcher Module

This module handles fetching stock data from Yahoo Finance.
"""

import yfinance as yf


class DataFetcher:
    """Fetch stock data from Yahoo Finance"""
    
    @staticmethod
    def fetch_stock_data(symbol, period='1y'):
        """
        Fetch live stock data from Yahoo Finance
        
        Args:
            symbol (str): Stock ticker symbol (e.g., 'AAPL', 'GOOGL')
            period (str): Data period (default: '1y' for 1 year)
            
        Returns:
            tuple: (data, ticker_info, success) - OHLC data, ticker info, success flag
        """
        try:
            stock = yf.Ticker(symbol)
            data = stock.history(period=period)
            ticker_info = stock.info
            
            if data.empty:
                print(f"✗ No data found for symbol: {symbol}")
                return None, None, False
            
            print(f"✓ Successfully fetched data for {symbol}")
            return data, ticker_info, True
            
        except Exception as e:
            print(f"✗ Error fetching data for {symbol}: {e}")
            return None, None, False
    
    @staticmethod
    def get_current_price(data):
        """
        Get the current/latest closing price
        
        Args:
            data (pd.DataFrame): Stock OHLC data
            
        Returns:
            float: Current price
        """
        if data is None or data.empty:
            return None
        
        return round(data['Close'].iloc[-1], 2)
