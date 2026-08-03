"""Terra-Fin Agent — top-level ESP32 entry point.

This file goes in the ESP32 root directory alongside boot.py.
It delegates to the main agent in lib/main.py.
"""

import sys
sys.path.insert(0, "/lib")

from main import main as run_agent

run_agent()