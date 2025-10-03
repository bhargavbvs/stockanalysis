"""
Example usage of the Stock Trend Analyzer module

This script demonstrates how to use the StockAnalyzer class
to analyze multiple stocks programmatically for trend identification.
"""

from stock_analyzer import StockAnalyzer, print_analysis

def analyze_single_stock(symbol):
    """
    Analyze a single stock and return the trend
    """
    analyzer = StockAnalyzer(symbol)
    result = analyzer.identify_trend()
    
    # Handle both old and new return formats
    if len(result) == 4:
        trend, reasons, additional_checks, analysis = result
    else:
        trend, reasons, analysis = result
    
    return trend, analysis

def scan_multiple_stocks(stocks):
    """
    Scan multiple stocks and filter by buy signals
    """
    print("\n" + "="*80)
    print("SCANNING MULTIPLE STOCKS FOR BUY SIGNALS")
    print("="*80 + "\n")
    
    buy_signals = []
    uptrends = []
    
    for symbol in stocks:
        print(f"Analyzing {symbol}...", end=" ")
        try:
            trend, analysis = analyze_single_stock(symbol)
            print(f"✓ {trend}")
            
            if trend == "STRONG BULLISH - BUY SIGNAL" or trend == "UPTREND - BUY SIGNAL":
                buy_signals.append((symbol, analysis))
            elif trend == "UPTREND - WAIT FOR PULLBACK" or trend == "UPTREND - DEVELOPING":
                uptrends.append((symbol, analysis))
        except Exception as e:
            print(f"✗ Error: {e}")
    
    # Print summary
    print("\n" + "="*80)
    print("SCAN RESULTS")
    print("="*80)
    
    if buy_signals:
        print(f"\n🎯 BUY SIGNALS ({len(buy_signals)}):")
        for symbol, analysis in buy_signals:
            print(f"   • {symbol} - Price: ${analysis['current_price']}, ADX: {analysis['adx']}, Stoch: {analysis['stoch_k']}")
    else:
        print("\n⚪ No buy signals found")
    
    if uptrends:
        print(f"\n📊 UPTRENDS - WAITING FOR PULLBACK ({len(uptrends)}):")
        for symbol, analysis in uptrends:
            print(f"   • {symbol} - Price: ${analysis['current_price']}, ADX: {analysis['adx']}")
    
    print("\n")

def main():
    """
    Example: Analyze multiple stocks
    """
    print("\n=== EXAMPLE 1: Detailed Analysis of Single Stock ===")
    analyzer = StockAnalyzer('AAPL')
    print_analysis(analyzer)
    
    print("\n=== EXAMPLE 2: Scan Multiple Stocks for Buy Signals ===")
    # List of popular stocks to scan
    stocks_to_scan = ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'NVDA', 'AMD', 'META']
    scan_multiple_stocks(stocks_to_scan)
    
    print("\n=== EXAMPLE 3: Get Raw Analysis Data ===")
    analyzer = StockAnalyzer('MSFT')
    result = analyzer.identify_trend()
    
    # Handle both old and new return formats
    if len(result) == 4:
        trend, reasons, additional_checks, analysis = result
    else:
        trend, reasons, analysis = result
    
    if analysis:
        print(f"Symbol: {analysis['symbol']}")
        print(f"Trend: {trend}")
        print(f"Current Price: ${analysis['current_price']}")
        print(f"EMAs (8/21/34/55/89): {analysis['ema_8']} / {analysis['ema_21']} / {analysis['ema_34']} / {analysis['ema_55']} / {analysis['ema_89']}")
        print(f"EMAs (20/40/200): {analysis.get('ema_20')} / {analysis.get('ema_40')} / {analysis.get('ema_200')}")
        print(f"ADX(13): {analysis['adx']}, ADX(14): {analysis.get('adx_14')}")
        print(f"RSI: {analysis['rsi']}, Stochastic %K: {analysis['stoch_k']}")
        print(f"52W High: ${analysis.get('high_52w')}, Distance: {analysis.get('distance_from_52w_high')}%")

if __name__ == "__main__":
    main()
