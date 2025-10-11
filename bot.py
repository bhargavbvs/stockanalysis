#!/usr/bin/env python3
"""
Telegram Bot Runner (Standalone)
Use this for Railway/production deployments instead of running through Streamlit
"""

import os
import sys
from pathlib import Path

# Add paths
sys.path.insert(0, str(Path(__file__).parent / 'src' / 'core'))
sys.path.insert(0, str(Path(__file__).parent / 'src' / 'analysis'))
sys.path.insert(0, str(Path(__file__).parent / 'src' / 'interfaces'))

def main():
    """Run Telegram bot in main thread (proper way for production)"""
    print("🤖 Starting Telegram Bot (Production Mode)...")
    
    from telegram_bot import main as run_bot
    
    try:
        run_bot()
    except KeyboardInterrupt:
        print("\n👋 Bot stopped by user")
    except Exception as e:
        print(f"❌ Bot error: {e}")
        raise

if __name__ == "__main__":
    main()
