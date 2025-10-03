"""
GUI version of Stock Analyzer using tkinter
Provides a simple graphical interface for stock analysis
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
from stock_analyzer import StockAnalyzer
import threading


class StockAnalyzerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("📈 Stock Investment Analyzer")
        self.root.geometry("700x650")
        self.root.resizable(True, True)
        
        # Configure style
        style = ttk.Style()
        style.theme_use('clam')
        
        # Create main frame
        main_frame = ttk.Frame(root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Title
        title_label = ttk.Label(main_frame, text="Stock Investment Analyzer", 
                                font=('Helvetica', 18, 'bold'))
        title_label.grid(row=0, column=0, columnspan=2, pady=10)
        
        # Stock Symbol Input
        ttk.Label(main_frame, text="Stock Symbol:", font=('Helvetica', 11)).grid(
            row=1, column=0, sticky=tk.W, pady=5)
        self.symbol_entry = ttk.Entry(main_frame, width=20, font=('Helvetica', 11))
        self.symbol_entry.grid(row=1, column=1, sticky=tk.W, pady=5)
        self.symbol_entry.insert(0, "AAPL")
        
        # RSI Threshold Input
        ttk.Label(main_frame, text="RSI Threshold:", font=('Helvetica', 11)).grid(
            row=2, column=0, sticky=tk.W, pady=5)
        self.rsi_entry = ttk.Entry(main_frame, width=20, font=('Helvetica', 11))
        self.rsi_entry.grid(row=2, column=1, sticky=tk.W, pady=5)
        self.rsi_entry.insert(0, "40")
        
        # Analyze Button
        self.analyze_button = ttk.Button(main_frame, text="Analyze Stock", 
                                         command=self.analyze_stock)
        self.analyze_button.grid(row=3, column=0, columnspan=2, pady=15)
        
        # Progress Bar
        self.progress = ttk.Progressbar(main_frame, mode='indeterminate', length=300)
        self.progress.grid(row=4, column=0, columnspan=2, pady=5)
        
        # Results Frame
        results_frame = ttk.LabelFrame(main_frame, text="Analysis Results", padding="10")
        results_frame.grid(row=5, column=0, columnspan=2, pady=10, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Results Text Area
        self.results_text = scrolledtext.ScrolledText(results_frame, width=75, height=25,
                                                       font=('Courier', 10), wrap=tk.WORD)
        self.results_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configure tags for colored text
        self.results_text.tag_config('title', font=('Courier', 12, 'bold'))
        self.results_text.tag_config('success', foreground='green', font=('Courier', 11, 'bold'))
        self.results_text.tag_config('fail', foreground='red', font=('Courier', 11, 'bold'))
        self.results_text.tag_config('info', foreground='blue')
        
        # Configure grid weights
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(5, weight=1)
        results_frame.columnconfigure(0, weight=1)
        results_frame.rowconfigure(0, weight=1)
        
        # Initial message
        self.results_text.insert(tk.END, "Enter a stock symbol and click 'Analyze Stock' to begin.\n\n")
        self.results_text.insert(tk.END, "Examples: AAPL, GOOGL, MSFT, TSLA, AMZN\n")
        self.results_text.insert(tk.END, "\nThe analyzer will check:\n")
        self.results_text.insert(tk.END, "  • 20-day, 40-day, and 200-day EMAs\n")
        self.results_text.insert(tk.END, "  • RSI indicator\n")
        self.results_text.insert(tk.END, "  • Investment recommendation\n")
    
    def analyze_stock(self):
        """Analyze the stock in a separate thread"""
        symbol = self.symbol_entry.get().strip().upper()
        rsi_threshold_str = self.rsi_entry.get().strip()
        
        if not symbol:
            messagebox.showwarning("Input Error", "Please enter a stock symbol.")
            return
        
        try:
            rsi_threshold = float(rsi_threshold_str)
        except ValueError:
            messagebox.showwarning("Input Error", "RSI threshold must be a number.")
            return
        
        # Disable button and start progress
        self.analyze_button.config(state='disabled')
        self.progress.start(10)
        
        # Clear previous results
        self.results_text.delete(1.0, tk.END)
        
        # Run analysis in separate thread
        thread = threading.Thread(target=self.run_analysis, 
                                  args=(symbol, rsi_threshold))
        thread.daemon = True
        thread.start()
    
    def run_analysis(self, symbol, rsi_threshold):
        """Run the analysis and update GUI"""
        try:
            analyzer = StockAnalyzer(symbol)
            invest, reasons, analysis = analyzer.should_invest(rsi_threshold)
            
            # Schedule GUI update in main thread
            self.root.after(0, self.display_results, invest, reasons, analysis)
        except Exception as e:
            self.root.after(0, self.display_error, str(e))
    
    def display_results(self, invest, reasons, analysis):
        """Display analysis results"""
        self.progress.stop()
        self.analyze_button.config(state='normal')
        
        if not analysis:
            self.results_text.insert(tk.END, "Failed to analyze stock.\n", 'fail')
            self.results_text.insert(tk.END, "Please check the symbol and try again.")
            return
        
        # Title
        self.results_text.insert(tk.END, "="*60 + "\n", 'title')
        self.results_text.insert(tk.END, f"STOCK ANALYSIS REPORT - {analysis['symbol']}\n", 'title')
        self.results_text.insert(tk.END, "="*60 + "\n\n", 'title')
        
        # Current Data
        self.results_text.insert(tk.END, f"📊 Current Data (as of {analysis['date']})\n", 'info')
        self.results_text.insert(tk.END, f"   Current Price: ${analysis['current_price']}\n\n")
        
        # Technical Indicators
        self.results_text.insert(tk.END, "📈 Technical Indicators:\n", 'info')
        self.results_text.insert(tk.END, f"   20-Day EMA:  ${analysis['ema_20']}\n")
        self.results_text.insert(tk.END, f"   40-Day EMA:  ${analysis['ema_40']}\n")
        self.results_text.insert(tk.END, f"   200-Day EMA: ${analysis['ema_200']}\n")
        self.results_text.insert(tk.END, f"   RSI (14):    {analysis['rsi']}\n\n")
        
        # Analysis
        self.results_text.insert(tk.END, "🔍 Analysis:\n", 'info')
        for reason in reasons:
            self.results_text.insert(tk.END, f"   {reason}\n")
        
        # Recommendation
        self.results_text.insert(tk.END, "\n" + "="*60 + "\n")
        if invest:
            self.results_text.insert(tk.END, "✅ RECOMMENDATION: GOOD TIME TO INVEST\n", 'success')
        else:
            self.results_text.insert(tk.END, "❌ RECOMMENDATION: NOT A GOOD TIME TO INVEST\n", 'fail')
        self.results_text.insert(tk.END, "="*60 + "\n\n")
        
        # Additional Insights
        self.results_text.insert(tk.END, "💡 Additional Insights:\n", 'info')
        if analysis['ema_20'] > analysis['ema_40'] > analysis['ema_200']:
            self.results_text.insert(tk.END, "   • Strong uptrend (EMAs aligned bullishly)\n")
        elif analysis['ema_20'] < analysis['ema_40'] < analysis['ema_200']:
            self.results_text.insert(tk.END, "   • Strong downtrend (EMAs aligned bearishly)\n")
        else:
            self.results_text.insert(tk.END, "   • Mixed signals from EMAs\n")
        
        if analysis['rsi'] > 70:
            self.results_text.insert(tk.END, "   • Stock may be overbought (RSI > 70)\n")
        elif analysis['rsi'] < 30:
            self.results_text.insert(tk.END, "   • Stock may be oversold (RSI < 30)\n")
        else:
            self.results_text.insert(tk.END, "   • RSI in neutral zone\n")
        
        self.results_text.insert(tk.END, "\n⚠️  Disclaimer: This is for educational purposes only.\n")
        self.results_text.insert(tk.END, "   Always do your own research before investing.\n")
    
    def display_error(self, error_msg):
        """Display error message"""
        self.progress.stop()
        self.analyze_button.config(state='normal')
        self.results_text.insert(tk.END, f"Error: {error_msg}\n", 'fail')


def main():
    root = tk.Tk()
    app = StockAnalyzerGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
