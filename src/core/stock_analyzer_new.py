"""
Stock Analyzer - Main Module

A comprehensive Python application that identifies strong bullish stocks and
high-probability entry points using a 12-criteria system combining two proven
methodologies.

This is the main entry point that combines all modular components:
- data_fetcher: Fetches stock data from Yahoo Finance
- indicators: Technical indicator calculations (EMA, RSI, Stochastic, ADX)
- criteria_checkers: Checks various bullish/bearish conditions
- trend_analyzer: Analyzes trends based on comprehensive criteria
- stock_analyzer_core: Main StockAnalyzer class
- output_formatter: Formats and displays results

Author: Stock Analysis System
Version: 2.0 (Modular)
"""

from stock_analyzer_core import StockAnalyzer
from output_formatter import print_analysis, format_header


def main():
    """
    Main function to run the stock trend analyzer
    """
    format_header()
    
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
