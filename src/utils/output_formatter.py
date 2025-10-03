"""
Output Formatter Module

This module handles formatting and displaying analysis results.
"""


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
    
    # Unpack result
    trend, reasons, additional_checks, analysis = result
    
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
        if trend == "STRONG BULLISH - BUY SIGNAL":
            print("✅✅ TREND: STRONG BULLISH - EXCELLENT BUY SIGNAL")
            print("   🎯🎯 ALL original + enhanced criteria met!")
            print("   💪 This is a HIGH-PROBABILITY entry point!")
        elif trend == "UPTREND - BUY SIGNAL":
            print("✅ TREND: UPTREND WITH BUY SIGNAL")
            print("   🎯 All 5 original criteria met - This is a potential entry point!")
        elif trend == "UPTREND - WAIT FOR PULLBACK":
            print("⏳ TREND: UPTREND - WAITING FOR PULLBACK")
            print("   📊 Stock is in uptrend but wait for better entry")
        elif trend == "UPTREND - DEVELOPING":
            print("📈 TREND: UPTREND - DEVELOPING")
            print("   🔄 Some bullish structure forming, monitor for confirmation")
        elif trend == "DOWNTREND":
            print("❌ TREND: DOWNTREND")
            print("   ⚠️  Avoid buying - Stock is in downtrend")
        else:
            print("⚪ TREND: NEUTRAL/MIXED SIGNALS")
            print("   ℹ️  No clear trend identified")
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


def format_header():
    """
    Print application header
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
