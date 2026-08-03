"""Interactive CLI for Terra-Fin Agent (ESP32/MicroPython).

NOTE: Uses only stdlib. Provides a simple command loop.
"""

import logging
import sys
import json

from core.engine import Engine
from core.prompts import (
    handle_soil_status,
    handle_harvest_advice,
    handle_location,
    handle_weather,
    handle_day_night,
    handle_walk_summary,
    handle_health,
)
from core.types import utc_now

logger = logging.getLogger(__name__)

BANNER = """
==============================
  Terra-Fin Agent
  --- ESP32 Ready ---
==============================
"""

HELP_TEXT = """
Commands:
  soil          - Show soil moisture and pH status
  harvest <crop> <count> <weight_kg> [tree_id] - Log a harvest
  weather       - Show temperature, humidity, and light
  location      - Show GPS location
  daynight      - Show day/night status
  walk          - Show walking summary
  night         - Show night mode events (from recorder)
  health        - Show sensor health
  summary       - Show full sensor summary
  adapt         - Show all adaptation advisories
  adapt weather - Show weather adaptation advisories
  adapt soil    - Show soil adaptation advisories
  adapt animal  - Show animal adaptation advisories
  adapt insect  - Show insect adaptation advisories
  warnings      - Show only warning/critical advisories
  help          - Show this help
  quit          - Exit the agent
"""


class CLI:
    """Interactive CLI loop for the walking stick agent."""

    def __init__(self, engine, recorder=None, module_mgr=None):
        self._engine = engine
        self._recorder = recorder
        self._module_mgr = module_mgr
        self._running = True

    def start(self):
        print(BANNER)
        print("Type 'help' for commands.\n")
        while self._running:
            try:
                command = input("Terra-Fin> ").strip()
            except EOFError:
                break
            if not command:
                continue
            self._handle(command)

    def _handle(self, command):
        parts = command.split()
        cmd = parts[0].lower()
        args = parts[1:]

        if cmd == "help":
            print(HELP_TEXT)

        elif cmd == "quit":
            self._running = False
            print("Shutting down...")

        elif cmd == "soil":
            summary = self._engine.get_summary()
            print(handle_soil_status(summary))

        elif cmd == "harvest":
            if len(args) < 3:
                print("Usage: harvest <crop> <count> <weight_kg> [tree_id]")
                return
            crop, count, weight = args[0], int(args[1]), float(args[2])
            tree_id = args[3] if len(args) > 3 else "unknown"
            if self._module_mgr:
                mod = self._module_mgr.get_module(crop)
                if mod:
                    mod.log_harvest(count, weight, tree_id)
                    print("Logged {} {} harvests ({} kg) from tree {}".format(count, crop, weight, tree_id))
                else:
                    print("Unknown crop: {}".format(crop))
            else:
                print("Module manager not available.")

        elif cmd == "weather":
            summary = self._engine.get_summary()
            print(handle_weather(summary))

        elif cmd == "location":
            summary = self._engine.get_summary()
            print(handle_location(summary))

        elif cmd == "daynight":
            summary = self._engine.get_summary()
            print(handle_day_night(summary))

        elif cmd == "walk":
            summary = self._engine.get_summary()
            print(handle_walk_summary(summary))

        elif cmd == "night":
            if self._recorder:
                events = self._recorder.read_events()
                if events:
                    print("Night events ({}):".format(len(events)))
                    for e in events[-5:]:
                        print("  [{}] {}".format(e.get("timestamp", "?"), e.get("advisory", "")))
                else:
                    print("No night events recorded.")
            else:
                print("Recorder not available.")

        elif cmd == "health":
            summary = self._engine.get_summary()
            print(handle_health(summary))

        elif cmd == "summary":
            summary = self._engine.get_summary()
            print(json.dumps(summary, indent=2))

        elif cmd == "adapt":
            if not args:
                advisories = self._engine.get_adaptation_advisories()
                for a in advisories:
                    print("[{}] {} (conf: {:.0f}%)".format(a.get("module", "?"), a.get("advisory", ""), a.get("confidence", 0) * 100))
            else:
                cat = args[0].lower()
                advisories = self._engine.get_adaptation_advisories(category=cat)
                for a in advisories:
                    print("[{}] {}".format(a.get("module", "?"), a.get("advisory", "")))

        elif cmd == "warnings":
            advisories = self._engine.get_adaptation_advisories(severity="warning")
            if advisories:
                for a in advisories:
                    print("[WARN] [{}] {}".format(a.get("module", "?"), a.get("advisory", "")))
            else:
                print("No warnings.")

        else:
            print("Unknown command: {}. Type 'help' for available commands.".format(command))
