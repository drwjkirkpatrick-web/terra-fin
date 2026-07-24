"""Interactive CLI for the agricultural walking stick agent.

NOTE: Uses only stdlib — no external dependencies. Provides a simple
command loop for the farmer to interact with the agent.

WHY: The CLI is the primary interface on the Pi Zero when no phone
or dashboard is available. It must work with just a keyboard and screen.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

from .engine import Engine
from .prompts import (
    handle_soil_status,
    handle_harvest_advice,
    handle_location,
    handle_weather,
    handle_day_night,
    handle_walk_summary,
    handle_health,
)
from .types import utc_now

logger = logging.getLogger(__name__)

BANNER = """
╔══════════════════════════════════════════╗
║   Terra-Fin Agent      ║
║   --- Mock Mode ---                     ║
╚══════════════════════════════════════════╝
"""

HELP_TEXT = """
Commands:
  soil         - Show soil moisture and pH status
  harvest <crop> <count> <weight_kg> [tree_id] - Log a harvest
  weather      - Show temperature, humidity, and light
  location     - Show GPS location
  daynight     - Show day/night status
  walk         - Show walking summary
  night        - Show night mode events (from recorder)
  health       - Show sensor health
  summary      - Show full sensor summary
  adapt        - Show all adaptation advisories
  adapt weather - Show weather adaptation advisories
  adapt soil    - Show soil adaptation advisories
  adapt animal - Show animal adaptation advisories
  adapt insect - Show insect adaptation advisories
  warnings     - Show only warning/critical advisories
  help         - Show this help
  quit         - Exit the agent
"""


class CLI:
    """Interactive CLI loop for the walking stick agent."""

    def __init__(
        self,
        engine: Engine,
        recorder: Any = None,
        harvest_modules: dict[str, Any] | None = None,
        adaptation_manager: Any = None,
    ) -> None:
        self._engine = engine
        self._recorder = recorder
        self._harvest_modules = harvest_modules or {}
        self._adaptation_manager = adaptation_manager
        self._running = False

    def start(self) -> None:
        """Enter the CLI loop."""
        print(BANNER)
        print("Type 'help' for commands, 'quit' to exit.\n")
        self._running = True
        while self._running:
            try:
                cmd = input("terra-fin> ").strip()
                if cmd:
                    self._dispatch(cmd)
            except (EOFError, KeyboardInterrupt):
                print("\nGoodbye!")
                self._running = False

    def _dispatch(self, cmd: str) -> None:
        """Route a command to the appropriate handler."""
        parts = cmd.split()
        command = parts[0].lower()
        args = parts[1:]

        if command in ("quit", "exit", "q"):
            print("Goodbye!")
            self._running = False
        elif command == "help":
            print(HELP_TEXT)
        elif command == "soil":
            summary = self._engine.get_summary()
            print(handle_soil_status(summary))
        elif command == "weather":
            summary = self._engine.get_summary()
            print(handle_weather(summary))
        elif command == "location":
            summary = self._engine.get_summary()
            print(handle_location(summary))
        elif command == "daynight":
            summary = self._engine.get_summary()
            print(handle_day_night(summary))
        elif command == "walk":
            summary = self._engine.get_summary()
            trends = self._engine.get_trends()
            print(handle_walk_summary(summary, trends))
        elif command == "health":
            summary = self._engine.get_summary()
            print(handle_health(summary))
        elif command == "summary":
            import json
            summary = self._engine.get_summary()
            print(json.dumps(summary, indent=2, default=str))
        elif command == "harvest":
            self._handle_harvest(args)
        elif command == "night":
            self._handle_night_events()
        elif command == "adapt":
            self._handle_adapt(args)
        elif command == "warnings":
            self._handle_warnings()
        else:
            print(f"Unknown command: {command}. Type 'help' for available commands.")

    def _handle_harvest(self, args: list[str]) -> None:
        """Handle: harvest <crop> <count> <weight_kg> [tree_id]"""
        if len(args) < 3:
            print("Usage: harvest <crop> <count> <weight_kg> [tree_id]")
            print("Crops: avocado, orange, kale, spinach, managu")
            return

        crop = args[0].lower()
        try:
            count = int(args[1])
            weight = float(args[2])
        except ValueError:
            print("Error: count must be an integer, weight a number.")
            return

        tree_id = args[3] if len(args) > 3 else None

        # Find the right harvest module
        module_map = {
            "avocado": "avocado",
            "orange": "orange",
            "kale": "greens",
            "spinach": "greens",
            "managu": "greens",
        }
        module_name = module_map.get(crop)
        if module_name is None:
            print(f"Unknown crop: {crop}")
            return

        module = self._harvest_modules.get(module_name)
        if module is None:
            print(f"Harvest module '{module_name}' not loaded.")
            return

        try:
            entry = module.log_harvest(
                count=count,
                weight_kg=weight,
                location="cli",
                tree_id=tree_id,
            )
            print(f"Logged: {entry.crop} x{entry.count}, {entry.weight_kg}kg")
        except Exception as e:
            print(f"Error logging harvest: {e}")

    def _handle_night_events(self) -> None:
        """Show night mode events from the recorder."""
        if self._recorder is None:
            print("Recorder not available.")
            return
        events = self._recorder.query_night_events()
        if not events:
            print("No night events recorded.")
            return
        print(f"{len(events)} night event(s):")
        for ev in events[:10]:
            print(f"  [{ev['timestamp']}] {ev['event_type']}: {ev['description']}")
        if len(events) > 10:
            print(f"  ... and {len(events) - 10} more.")

    def _handle_adapt(self, args: list[str]) -> None:
        """Show adaptation advisories, optionally filtered by category."""
        if self._adaptation_manager is None:
            print("Adaptation manager not available.")
            return

        # Run all modules with current sensor data
        summary = self._engine.get_summary()
        # Extract the most recent reading for each sensor
        reading = None
        sensors = summary.get("sensors", {})
        if sensors:
            # Use the first available sensor reading
            for sname, sdata in sensors.items():
                metrics = sdata.get("metrics", {})
                if metrics:
                    from core.types import SensorReading, utc_now
                    reading = SensorReading(
                        sensor_name=sname,
                        timestamp=utc_now(),
                        metrics=metrics,
                        units=sdata.get("units", {}),
                    )
                    break

        context = {
            "trends": self._engine.get_trends(),
            "hour": datetime.now().hour if (datetime := __import__("datetime").datetime) else 12,
        }
        self._adaptation_manager.run_all(reading, context)

        if args:
            category = args[0].lower()
            advisories = self._adaptation_manager.get_advisories_by_category(category)
        else:
            advisories = self._adaptation_manager.get_advisories()

        if not advisories:
            print("No adaptation advisories available.")
            return

        print(f"{len(advisories)} adaptation advisory/advisories:")
        for adv in advisories:
            sev = adv["severity"].upper()
            print(f"  [{sev}] {adv['module']}: {adv['advisory']}")

    def _handle_warnings(self) -> None:
        """Show only warning and critical advisories."""
        if self._adaptation_manager is None:
            print("Adaptation manager not available.")
            return

        summary = self._engine.get_summary()
        reading = None
        sensors = summary.get("sensors", {})
        if sensors:
            for sname, sdata in sensors.items():
                metrics = sdata.get("metrics", {})
                if metrics:
                    from core.types import SensorReading, utc_now
                    reading = SensorReading(
                        sensor_name=sname,
                        timestamp=utc_now(),
                        metrics=metrics,
                        units=sdata.get("units", {}),
                    )
                    break

        context = {"trends": self._engine.get_trends()}
        self._adaptation_manager.run_all(reading, context)

        warnings = self._adaptation_manager.get_warnings()
        if not warnings:
            print("No warnings or critical advisories. All clear.")
            return

        print(f"{len(warnings)} warning(s)/critical advisory/advisories:")
        for adv in warnings:
            sev = adv["severity"].upper()
            print(f"  [{sev}] {adv['module']}: {adv['advisory']}")