"""
Stock Analyzer Class

Main class that combines all modules to provide a unified interface
for stock analysis.
"""

from data_fetcher import DataFetcher
from trend_analyzer import analyze_stock, identify_trend


class StockAnalyzer:
    """
    Main Stock Analyzer class that coordinates all analysis modules
    """
    
    def __init__(self, symbol):
        """
        Initialize the Stock Analyzer with a stock symbol
        
        Args:
            symbol (str): Stock ticker symbol (e.g., 'AAPL', 'GOOGL')
        """
        self.symbol = symbol.upper()
        self.data = None
        self.ticker_info = None
        self.current_price = None
    
    def fetch_data(self, period='1y'):
        """
        Fetch live stock data from Yahoo Finance
        
        Args:
            period (str): Data period (default: '1y' for 1 year)
            
        Returns:
            bool: Success flag
        """
        self.data, self.ticker_info, success = DataFetcher.fetch_stock_data(self.symbol, period)
        
        if success:
            self.current_price = DataFetcher.get_current_price(self.data)
        
        return success
    
    def analyze(self):
        """
        Perform complete analysis and return all indicators
        
        Returns:
            dict: Dictionary containing all calculated indicators
        """
        if not self.fetch_data():
            return None
        
        analysis = analyze_stock(self.data, self.ticker_info, self.current_price)
        
        if analysis:
            analysis['symbol'] = self.symbol
        
        return analysis
    
    def identify_trend(self):
        """
        Identify if stock is in UPTREND or DOWNTREND based on comprehensive criteria
        
        Returns:
            tuple: (str, list, list, dict) - Trend type, reasons, additional_checks, analysis data
        """
        analysis = self.analyze()
        
        if analysis is None:
            return "UNKNOWN", ["Unable to fetch data"], [], None
        
        trend, reasons, additional_checks = identify_trend(analysis)
        
        return trend, reasons, additional_checks, analysis
