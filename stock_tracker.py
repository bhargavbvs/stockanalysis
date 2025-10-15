"""
Stock Tracker - Automated Stock Monitoring System

This script monitors a list of stocks at regular intervals and sends alerts
when they meet your trading criteria (CALL or PUT signals).

Features:
- Tracks multiple stocks simultaneously
- Runs on a schedule (every 30 mins, 1 hour, etc.)
- Sends alerts via:
  - Telegram
  - Email (optional)
  - Discord (optional)
  - Webhook (for n8n integration)
- Logs all signals and tracks historical data
- Avoids duplicate alerts

Usage:
    python stock_tracker.py
"""

import sys
from pathlib import Path
import time
from datetime import datetime, timedelta
import json
import logging
from typing import List, Dict, Optional
import schedule
import pytz
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Add paths for imports
sys.path.insert(0, str(Path(__file__).parent / 'src' / 'core'))
sys.path.insert(0, str(Path(__file__).parent / 'src' / 'analysis'))

from stock_analyzer import StockAnalyzer

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('stock_tracker.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class StockTracker:
    """
    Automated stock tracking system that monitors stocks and sends alerts
    """
    
    def __init__(self, config_file: str = 'tracker_config.json'):
        """
        Initialize the stock tracker
        
        Args:
            config_file: Path to configuration file
        """
        self.config = self.load_config(config_file)
        self.watchlist = self.config.get('watchlist', [])
        self.alert_history = self.load_alert_history()
        
        # Set up timezone for market hours
        self.eastern = pytz.timezone('US/Eastern')
        
        logger.info(f"Stock Tracker initialized with {len(self.watchlist)} stocks")
    
    def is_market_hours(self) -> bool:
        """
        Check if current time is within market hours (or 30 min before/after)
        Market hours: 9:00 AM - 4:00 PM ET
        Extended: 8:30 AM - 4:30 PM ET (30 min before/after)
        
        Returns:
            True if within trading window, False otherwise
        """
        # Get current time in ET
        now_et = datetime.now(self.eastern)
        
        # Check if it's a weekday (Monday=0, Sunday=6)
        if now_et.weekday() >= 5:  # Saturday or Sunday
            logger.info(f"Weekend detected ({now_et.strftime('%A')}). Skipping scan.")
            return False
        
        # Define market hours (with 30-minute buffer)
        market_open = now_et.replace(hour=8, minute=30, second=0, microsecond=0)  # 8:30 AM ET
        market_close = now_et.replace(hour=16, minute=30, second=0, microsecond=0)  # 4:30 PM ET
        
        # Check if within hours
        is_open = market_open <= now_et <= market_close
        
        if not is_open:
            next_open = self.get_next_market_open(now_et)
            logger.info(f"Outside market hours. Current time: {now_et.strftime('%I:%M %p ET')}")
            logger.info(f"Market hours: 8:30 AM - 4:30 PM ET (Mon-Fri)")
            logger.info(f"Next scan will be at: {next_open.strftime('%A, %I:%M %p ET')}")
        
        return is_open
    
    def get_next_market_open(self, now_et: datetime) -> datetime:
        """
        Calculate when the market will open next
        
        Args:
            now_et: Current time in Eastern timezone
            
        Returns:
            datetime of next market open (8:30 AM ET)
        """
        # Start with tomorrow
        next_day = now_et + timedelta(days=1)
        next_open = next_day.replace(hour=8, minute=30, second=0, microsecond=0)
        
        # Skip weekends
        while next_open.weekday() >= 5:  # Saturday or Sunday
            next_open += timedelta(days=1)
        
        # If we're still on the same day and before 8:30 AM, use today
        if now_et.hour < 8 or (now_et.hour == 8 and now_et.minute < 30):
            next_open = now_et.replace(hour=8, minute=30, second=0, microsecond=0)
        
        return next_open
    
    def load_config(self, config_file: str) -> Dict:
        """Load configuration from JSON file or environment variables"""
        import os
        
        # Check if running on Railway/cloud (environment variables present)
        if os.getenv('TELEGRAM_BOT_TOKEN'):
            logger.info("Loading config from environment variables (Cloud deployment mode)")
            
            # Parse watchlist from comma-separated string
            watchlist_str = os.getenv('WATCHLIST', 'AAPL,MSFT,GOOGL,AMZN,TSLA')
            watchlist = [s.strip().upper() for s in watchlist_str.split(',')]
            
            return {
                'watchlist': watchlist,
                'scan_interval_minutes': int(os.getenv('SCAN_INTERVAL_MINUTES', '30')),
                'alert_channels': {
                    'telegram': {
                        'enabled': True,
                        'bot_token': os.getenv('TELEGRAM_BOT_TOKEN'),
                        'chat_id': os.getenv('TELEGRAM_CHAT_ID')
                    },
                    'email': {
                        'enabled': os.getenv('EMAIL_ENABLED', 'false').lower() == 'true',
                        'smtp_server': os.getenv('EMAIL_SMTP_SERVER', 'smtp.gmail.com'),
                        'smtp_port': int(os.getenv('EMAIL_SMTP_PORT', '587')),
                        'sender_email': os.getenv('EMAIL_SENDER', ''),
                        'sender_password': os.getenv('EMAIL_PASSWORD', ''),
                        'recipient_email': os.getenv('EMAIL_RECIPIENT', '')
                    },
                    'discord': {
                        'enabled': os.getenv('DISCORD_ENABLED', 'false').lower() == 'true',
                        'webhook_url': os.getenv('DISCORD_WEBHOOK_URL', '')
                    },
                    'webhook': {
                        'enabled': os.getenv('WEBHOOK_ENABLED', 'false').lower() == 'true',
                        'url': os.getenv('WEBHOOK_URL', '')
                    }
                },
                'filters': {
                    'min_confidence': os.getenv('MIN_CONFIDENCE', 'MODERATE'),
                    'signal_types': ['CALL', 'PUT'],
                    'min_criteria_met': int(os.getenv('MIN_CRITERIA_MET', '4')),
                    'avoid_extended_prices': os.getenv('AVOID_EXTENDED', 'true').lower() == 'true'
                },
                'alert_cooldown_hours': int(os.getenv('ALERT_COOLDOWN_HOURS', '4'))
            }
        
        # Otherwise, load from JSON file as usual
        try:
            with open(config_file, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            logger.warning(f"Config file {config_file} not found. Using default config.")
            return self.create_default_config(config_file)
    
    def create_default_config(self, config_file: str) -> Dict:
        """Create default configuration file"""
        default_config = {
            "watchlist": [
                "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA",
                "NVDA", "META", "NFLX", "AMD", "PYPL"
            ],
            "scan_interval_minutes": 30,
            "alert_channels": {
                "telegram": {
                    "enabled": True,
                    "bot_token": "YOUR_BOT_TOKEN",
                    "chat_id": "YOUR_CHAT_ID"
                },
                "email": {
                    "enabled": False,
                    "smtp_server": "smtp.gmail.com",
                    "smtp_port": 587,
                    "sender_email": "your_email@gmail.com",
                    "sender_password": "your_app_password",
                    "recipient_email": "recipient@example.com"
                },
                "webhook": {
                    "enabled": False,
                    "url": "https://your-n8n-webhook-url.com/webhook/stock-alert"
                },
                "discord": {
                    "enabled": False,
                    "webhook_url": "YOUR_DISCORD_WEBHOOK_URL"
                }
            },
            "filters": {
                "min_confidence": "MODERATE",
                "signal_types": ["CALL", "PUT"],
                "min_criteria_met": 4,
                "avoid_extended_prices": True
            },
            "alert_cooldown_hours": 4
        }
        
        # Save default config
        with open(config_file, 'w') as f:
            json.dump(default_config, f, indent=4)
        
        logger.info(f"Created default config file: {config_file}")
        return default_config
    
    def load_alert_history(self) -> Dict:
        """Load alert history to avoid duplicate alerts"""
        try:
            with open('alert_history.json', 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return {}
    
    def save_alert_history(self):
        """Save alert history"""
        with open('alert_history.json', 'w') as f:
            json.dump(self.alert_history, f, indent=4)
    
    def should_alert(self, symbol: str, signal_type: str) -> bool:
        """
        Check if we should send an alert for this stock
        (avoid duplicate alerts within cooldown period)
        """
        cooldown_hours = self.config.get('alert_cooldown_hours', 4)
        
        key = f"{symbol}_{signal_type}"
        
        if key in self.alert_history:
            last_alert_time = datetime.fromisoformat(self.alert_history[key]['last_alert'])
            time_since_alert = datetime.now() - last_alert_time
            
            if time_since_alert < timedelta(hours=cooldown_hours):
                logger.debug(f"Skipping alert for {symbol} - within cooldown period")
                return False
        
        return True
    
    def record_alert(self, symbol: str, signal_type: str, analysis: Dict):
        """Record that we sent an alert"""
        key = f"{symbol}_{signal_type}"
        self.alert_history[key] = {
            'last_alert': datetime.now().isoformat(),
            'signal_type': signal_type,
            'confidence': analysis.get('options_recommendation', {}).get('confidence', 'N/A'),
            'price': analysis.get('current_price')
        }
        self.save_alert_history()
    
    def analyze_stock(self, symbol: str) -> Optional[Dict]:
        """
        Analyze a single stock
        
        Returns:
            Dict with analysis results or None if error
        """
        try:
            logger.info(f"Analyzing {symbol}...")
            analyzer = StockAnalyzer(symbol)
            trend, reasons, additional_checks, analysis = analyzer.identify_trend()
            
            if analysis is None:
                logger.warning(f"Failed to analyze {symbol}")
                return None
            
            return {
                'symbol': symbol,
                'trend': trend,
                'reasons': reasons,
                'additional_checks': additional_checks,
                'analysis': analysis
            }
        
        except Exception as e:
            logger.error(f"Error analyzing {symbol}: {e}")
            return None
    
    def meets_criteria(self, result: Dict) -> bool:
        """
        Check if stock meets alerting criteria
        """
        if not result:
            return False
        
        analysis = result['analysis']
        options_rec = analysis.get('options_recommendation', {})
        
        # Get filter settings
        filters = self.config.get('filters', {})
        min_confidence = filters.get('min_confidence', 'MODERATE')
        signal_types = filters.get('signal_types', ['CALL', 'PUT'])
        avoid_extended = filters.get('avoid_extended_prices', True)
        
        strategy = options_rec.get('strategy', '')
        confidence = options_rec.get('confidence', 'N/A')
        
        # Check if it's a valid signal type
        is_valid_signal = any(sig in strategy for sig in signal_types)
        if not is_valid_signal:
            return False
        
        # Check confidence level
        confidence_levels = ['LOW', 'MODERATE', 'HIGH', 'VERY HIGH']
        min_conf_idx = confidence_levels.index(min_confidence) if min_confidence in confidence_levels else 1
        curr_conf_idx = confidence_levels.index(confidence) if confidence in confidence_levels else 0
        
        if curr_conf_idx < min_conf_idx:
            return False
        
        # Check if price is extended (optional filter)
        if avoid_extended:
            not_extended = analysis.get('not_extended', True)
            if not not_extended:
                logger.info(f"{result['symbol']} - Price too extended, skipping alert")
                return False
        
        return True
    
    def format_alert_message(self, result: Dict) -> str:
        """
        Format a nice alert message
        """
        symbol = result['symbol']
        analysis = result['analysis']
        options_rec = analysis.get('options_recommendation', {})
        
        strategy = options_rec.get('strategy', 'NO TRADE')
        confidence = options_rec.get('confidence', 'N/A')
        reasoning = options_rec.get('reasoning', '')
        entry = options_rec.get('entry', '')
        risk = options_rec.get('risk', '')
        
        # Determine emoji
        if 'CALL' in strategy:
            emoji = '📞'
            signal = 'BULLISH'
        elif 'PUT' in strategy:
            emoji = '📉'
            signal = 'BEARISH'
        else:
            emoji = '⚪'
            signal = 'NEUTRAL'
        
        # Format message
        message = f"""
🚨 **STOCK ALERT: {symbol}** 🚨

{emoji} **{signal} SIGNAL**
Strategy: {strategy}
Confidence: {confidence}

💰 **Price:** ${analysis['current_price']}
📊 **Key Metrics:**
• RSI: {analysis['rsi']}
• Stochastic: {analysis['stoch_k']}
• ADX: {analysis['adx']}

📈 **EMAs:**
• 8-EMA: ${analysis['ema_8']}
• 21-EMA: ${analysis['ema_21']}
• 34-EMA: ${analysis['ema_34']}

💡 **Reasoning:** {reasoning}

🎯 **Entry:** {entry}

⚠️ **Risk:** {risk}

🕒 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
""".strip()
        
        return message
    
    def send_telegram_alert(self, message: str) -> bool:
        """Send alert via Telegram"""
        try:
            telegram_config = self.config['alert_channels']['telegram']
            
            if not telegram_config.get('enabled', False):
                return False
            
            import requests
            
            bot_token = telegram_config.get('bot_token')
            chat_id = telegram_config.get('chat_id')
            
            if not bot_token or not chat_id or bot_token == "YOUR_BOT_TOKEN":
                logger.warning("Telegram not configured properly")
                return False
            
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            data = {
                'chat_id': chat_id,
                'text': message,
                'parse_mode': 'Markdown'
            }
            
            response = requests.post(url, data=data, timeout=10)
            
            if response.status_code == 200:
                logger.info("Telegram alert sent successfully")
                return True
            else:
                logger.error(f"Failed to send Telegram alert: {response.text}")
                return False
        
        except Exception as e:
            logger.error(f"Error sending Telegram alert: {e}")
            return False
    
    def send_email_alert(self, message: str) -> bool:
        """Send alert via Email"""
        try:
            email_config = self.config['alert_channels']['email']
            
            if not email_config.get('enabled', False):
                return False
            
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            
            smtp_server = email_config.get('smtp_server')
            smtp_port = email_config.get('smtp_port')
            sender_email = email_config.get('sender_email')
            sender_password = email_config.get('sender_password')
            recipient_email = email_config.get('recipient_email')
            
            msg = MIMEMultipart()
            msg['From'] = sender_email
            msg['To'] = recipient_email
            msg['Subject'] = '🚨 Stock Trading Alert'
            
            msg.attach(MIMEText(message, 'plain'))
            
            with smtplib.SMTP(smtp_server, smtp_port) as server:
                server.starttls()
                server.login(sender_email, sender_password)
                server.send_message(msg)
            
            logger.info("Email alert sent successfully")
            return True
        
        except Exception as e:
            logger.error(f"Error sending email alert: {e}")
            return False
    
    def send_webhook_alert(self, result: Dict) -> bool:
        """Send alert to webhook (for n8n integration)"""
        try:
            webhook_config = self.config['alert_channels']['webhook']
            
            if not webhook_config.get('enabled', False):
                return False
            
            import requests
            
            webhook_url = webhook_config.get('url')
            
            if not webhook_url or webhook_url == "https://your-n8n-webhook-url.com/webhook/stock-alert":
                logger.warning("Webhook not configured")
                return False
            
            # Prepare payload
            payload = {
                'timestamp': datetime.now().isoformat(),
                'symbol': result['symbol'],
                'trend': result['trend'],
                'analysis': result['analysis'],
                'options_recommendation': result['analysis'].get('options_recommendation')
            }
            
            response = requests.post(webhook_url, json=payload, timeout=10)
            
            if response.status_code == 200:
                logger.info("Webhook alert sent successfully")
                return True
            else:
                logger.error(f"Failed to send webhook alert: {response.text}")
                return False
        
        except Exception as e:
            logger.error(f"Error sending webhook alert: {e}")
            return False
    
    def send_discord_alert(self, message: str) -> bool:
        """Send alert via Discord webhook"""
        try:
            discord_config = self.config['alert_channels']['discord']
            
            if not discord_config.get('enabled', False):
                return False
            
            import requests
            
            webhook_url = discord_config.get('webhook_url')
            
            if not webhook_url or webhook_url == "YOUR_DISCORD_WEBHOOK_URL":
                logger.warning("Discord not configured")
                return False
            
            data = {
                'content': message
            }
            
            response = requests.post(webhook_url, json=data, timeout=10)
            
            if response.status_code == 204:
                logger.info("Discord alert sent successfully")
                return True
            else:
                logger.error(f"Failed to send Discord alert: {response.text}")
                return False
        
        except Exception as e:
            logger.error(f"Error sending Discord alert: {e}")
            return False
    
    def send_alerts(self, result: Dict):
        """Send alerts via all configured channels"""
        message = self.format_alert_message(result)
        
        # Send to all enabled channels
        self.send_telegram_alert(message)
        self.send_email_alert(message)
        self.send_discord_alert(message)
        self.send_webhook_alert(result)
    
    def scan_stocks(self):
        """
        Scan all stocks in watchlist and send alerts for signals
        Only scans during market hours (8:30 AM - 4:30 PM ET, Mon-Fri)
        """
        # Check if we're within market hours
        if not self.is_market_hours():
            logger.info("Skipping scan - outside market hours")
            return
        
        logger.info(f"Starting stock scan at {datetime.now()}")
        logger.info(f"Scanning {len(self.watchlist)} stocks...")
        
        signals_found = 0
        
        for symbol in self.watchlist:
            try:
                # Analyze stock
                result = self.analyze_stock(symbol)
                
                if not result:
                    continue
                
                # Check if meets criteria
                if self.meets_criteria(result):
                    options_rec = result['analysis'].get('options_recommendation', {})
                    strategy = options_rec.get('strategy', '')
                    
                    # Determine signal type
                    if 'CALL' in strategy:
                        signal_type = 'CALL'
                    elif 'PUT' in strategy:
                        signal_type = 'PUT'
                    else:
                        continue
                    
                    # Check if we should alert
                    if self.should_alert(symbol, signal_type):
                        logger.info(f"🚨 SIGNAL FOUND: {symbol} - {strategy}")
                        
                        # Send alerts
                        self.send_alerts(result)
                        
                        # Record alert
                        self.record_alert(symbol, signal_type, result['analysis'])
                        
                        signals_found += 1
                
                # Small delay between stocks to avoid rate limiting
                time.sleep(2)
            
            except Exception as e:
                logger.error(f"Error processing {symbol}: {e}")
                continue
        
        logger.info(f"Scan complete. Found {signals_found} new signals.")
        logger.info(f"Next scan in {self.config.get('scan_interval_minutes', 30)} minutes")
    
    def run_once(self):
        """Run a single scan"""
        self.scan_stocks()
    
    def run_scheduler(self):
        """
        Run the tracker on a schedule
        """
        interval_minutes = self.config.get('scan_interval_minutes', 30)
        
        logger.info("="*80)
        logger.info("STOCK TRACKER STARTED")
        logger.info("="*80)
        logger.info(f"Watchlist: {', '.join(self.watchlist)}")
        logger.info(f"Scan interval: {interval_minutes} minutes")
        logger.info(f"Next scan: {datetime.now() + timedelta(minutes=interval_minutes)}")
        logger.info("="*80)
        
        # Schedule the job
        schedule.every(interval_minutes).minutes.do(self.scan_stocks)
        
        # Run first scan immediately
        self.scan_stocks()
        
        # Keep running
        while True:
            schedule.run_pending()
            time.sleep(60)  # Check every minute


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Stock Tracker - Automated Stock Monitoring')
    parser.add_argument(
        '--config',
        default='tracker_config.json',
        help='Path to configuration file'
    )
    parser.add_argument(
        '--once',
        action='store_true',
        help='Run a single scan and exit'
    )
    
    args = parser.parse_args()
    
    # Create tracker
    tracker = StockTracker(config_file=args.config)
    
    if args.once:
        # Run once and exit
        tracker.run_once()
    else:
        # Run on schedule
        try:
            tracker.run_scheduler()
        except KeyboardInterrupt:
            logger.info("Stock Tracker stopped by user")
        except Exception as e:
            logger.error(f"Stock Tracker error: {e}")


if __name__ == "__main__":
    main()
