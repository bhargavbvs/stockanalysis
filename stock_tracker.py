"""Entry point used by Railway (Procfile / railway.json).

    python stock_tracker.py              run forever: scans in market hours + daily brief
    python stock_tracker.py --once       one scan now
    python stock_tracker.py --brief      send the morning brief now
    python stock_tracker.py --test       send a test message to every channel
    add --dry-run to print instead of sending

The code lives in the stockbot/ package (see stockbot/tracker.py).
"""

import sys

from stockbot.tracker import main

if __name__ == "__main__":
    sys.exit(main())
