"""
Stock Analyzer Package

A comprehensive stock analysis system with modular architecture.
"""

# Make it easier to import from submodules
from src.core.stock_analyzer_core import StockAnalyzer
from src.utils.output_formatter import print_analysis, format_header

__version__ = "2.0"
__author__ = "Stock Analysis System"

__all__ = ['StockAnalyzer', 'print_analysis', 'format_header']
