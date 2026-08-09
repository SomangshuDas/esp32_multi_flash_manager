#!/usr/bin/env python3
"""
run.py
======
Convenience launcher: run `python run.py` from the project root to start
ESP32 Multi Flash Manager. Equivalent to `python -m app.main`.
"""

import sys

from app.main import main

if __name__ == "__main__":
    sys.exit(main())
