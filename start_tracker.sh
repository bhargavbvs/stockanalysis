#!/bin/bash

# Stock Tracker Quick Start Script
# This script helps you set up and run the stock tracker

set -e  # Exit on error

echo "================================================"
echo "  📈 Stock Tracker Quick Start"
echo "================================================"
echo ""

# Check Python version
echo "🔍 Checking Python version..."
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "   ✓ Python $python_version found"
echo ""

# Install dependencies
echo "📦 Installing dependencies..."
pip3 install -r requirements.txt
echo "   ✓ Dependencies installed"
echo ""

# Create config if it doesn't exist
if [ ! -f "tracker_config.json" ]; then
    echo "⚙️  Creating default configuration..."
    cp tracker_config.example.json tracker_config.json
    echo "   ✓ Configuration created at tracker_config.json"
    echo ""
    echo "⚠️  IMPORTANT: Please edit tracker_config.json with your settings:"
    echo "   - Add your Telegram bot token and chat ID"
    echo "   - Customize your watchlist"
    echo "   - Adjust scan interval and filters"
    echo ""
else
    echo "✓ Configuration file already exists"
    echo ""
fi

# Ask what to do
echo "What would you like to do?"
echo ""
echo "1) Test run (scan once and exit)"
echo "2) Run continuously (recommended)"
echo "3) View configuration"
echo "4) Edit configuration"
echo "5) View logs"
echo "6) Clear alert history"
echo ""
read -p "Enter choice [1-6]: " choice

case $choice in
    1)
        echo ""
        echo "🔍 Running test scan..."
        python3 stock_tracker.py --once
        ;;
    2)
        echo ""
        echo "🚀 Starting stock tracker..."
        echo "   Press Ctrl+C to stop"
        echo ""
        python3 stock_tracker.py
        ;;
    3)
        echo ""
        echo "📋 Current configuration:"
        echo ""
        cat tracker_config.json | python3 -m json.tool
        ;;
    4)
        echo ""
        echo "📝 Opening configuration in editor..."
        ${EDITOR:-nano} tracker_config.json
        ;;
    5)
        echo ""
        echo "📄 Viewing logs (Ctrl+C to exit)..."
        echo ""
        if [ -f "stock_tracker.log" ]; then
            tail -f stock_tracker.log
        else
            echo "No logs found yet. Run the tracker first."
        fi
        ;;
    6)
        echo ""
        read -p "⚠️  This will re-enable all alerts. Continue? [y/N]: " confirm
        if [ "$confirm" = "y" ] || [ "$confirm" = "Y" ]; then
            rm -f alert_history.json
            echo "   ✓ Alert history cleared"
        else
            echo "   Cancelled"
        fi
        ;;
    *)
        echo ""
        echo "Invalid choice. Exiting."
        exit 1
        ;;
esac

echo ""
echo "================================================"
echo "  Done! Happy trading! 📊"
echo "================================================"
