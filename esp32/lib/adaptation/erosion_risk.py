"""ErosionRisk — assesses erosion risk from rainfall estimates and slope.

NOTE: This adaptation module inherits from AdaptationModule so the orchestrator,
CLI, and dashboard can manage it identically to every other adaptation module.
It reads rainfall and slope data from the orchestrator context dict rather than
from a direct sensor reading, because both values are typically derived or
estimated by upstream modules (e.g. RainPredictor and GPS/terrain analysis).

Decision rules (evaluated in order, first match wins):
  1. No rainfall data in context  → no-data advisory, confidence 0.0
  2. rain > 20 mm and slope > 10 % → high risk,   confidence 0.7 (warning)
  3. rain 10–20 mm and slope > 10% → moderate risk, confidence 0.5 (advisory)
  4. rain > 20 mm and slope < 5 %  → low risk,    confidence 0.5 (info)
  5. rain < 10 mm                  → minimal,    confidence 0.6 (info)
  6. Otherwise (catch-all)         → low risk,   confidence 0.5 (info)

WHY: Soil erosion is the single biggest threat to long-term farmland
productivity on sloped terrain. Heavy rain on steep ground can wash away
topsoil and nutrients in a single storm. By combining a rainfall estimate
with the local slope percentage, this module gives the farmer an actionable
advisory — contour barriers when risk is high, drainage checks when rain is
heavy but the ground is flat, and reassurance when rainfall is light. The
thresholds (20 mm / 10 mm rain, 10 % / 5 % slope) are empirical heuristics
tuned for highland-tropical smallholder agronomy.
"""


import logging

from core.adaptation_base import AdaptationModule, AdaptationResult
from core.types import SensorReading, utc_now

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Thresholds
# --------------------------------------------------------------------------- #

# Rainfall thresholds (millimetres).
HEAVY_RAIN_THRESHOLD = 20.0  # heavy rain above this
LIGHT_RAIN_THRESHOLD = 10.0  # light rain below this

# Slope thresholds (percent grade).
STEEP_SLOPE_THRESHOLD = 10.0  # steep / erosion-prone above this
FLAT_SLOPE_THRESHOLD = 5.0    # flat ground below this


class ErosionRisk(AdaptationModule):
    """Assesses erosion risk from rainfall estimates and slope.

    Class attributes follow the AdaptationModule contract so the framework can
    introspect every adaptation module uniformly (health checks, dashboards,
    recorder).

    The ``analyze`` method reads ``rain_estimate_mm`` and ``slope_percent``
    from the orchestrator-supplied context dict. The sensor ``reading``
    parameter is accepted for interface compatibility but is not used —
    erosion risk is a composite assessment driven by context, not a single
    raw sensor value.
    """

    name: str = "erosion_risk"
    category: str = "soil"
    description: str = "Assesses erosion risk from rainfall estimates and slope"

    # ------------------------------------------------------------------ #
    # Core analysis
    # ------------------------------------------------------------------ #

    def analyze(self, reading, context):
        """Assess erosion risk from rainfall estimate and slope.

        Args:
            reading: Latest SensorReading (unused by this module — erosion
                risk is context-driven — but required by the
                AdaptationModule contract).
            context: Orchestrator context dict. Must contain
                ``rain_estimate_mm`` (float, millimetres) and
                ``slope_percent`` (float, percent grade) for a meaningful
                assessment.

        Returns:
            An AdaptationResult with an advisory, confidence, severity, and
            a data dict containing ``rain_mm``, ``slope_percent``, and
            ``risk_level``.
        """
        # --- No rainfall data in context -------------------------------- #\
        if "rain_estimate_mm" not in context:
            return self._result(
                advisory="No rainfall data for erosion assessment.",
                confidence=0.0,
                severity="info",
                rain_mm=None,
                slope_percent=context.get("slope_percent", 0.0),
                risk_level="unknown",
            )

        rain = float(context.get("rain_estimate_mm", 0.0))
        slope = float(context.get("slope_percent", 0.0))

        # --- Heavy rain on steep slope → high erosion risk ------------- #\
        if rain > HEAVY_RAIN_THRESHOLD and slope > STEEP_SLOPE_THRESHOLD:
            return self._result(
                advisory=(
                    "High erosion risk - heavy rain on sloped ground. "
                    "Consider contour barriers."
                ),
                confidence=0.7,
                severity="warning",
                rain_mm=rain,
                slope_percent=slope,
                risk_level="high",
            )

        # --- Moderate rain on steep slope → moderate erosion risk ------ #\
        if (
            LIGHT_RAIN_THRESHOLD <= rain <= HEAVY_RAIN_THRESHOLD
            and slope > STEEP_SLOPE_THRESHOLD
        ):
            return self._result(
                advisory=(
                    "Moderate erosion risk - light rain on slope. "
                    "Monitor runoff."
                ),
                confidence=0.5,
                severity="advisory",
                rain_mm=rain,
                slope_percent=slope,
                risk_level="moderate",
            )

        # --- Heavy rain on flat ground → low risk but check drainage --- #\
        if rain > HEAVY_RAIN_THRESHOLD and slope < FLAT_SLOPE_THRESHOLD:
            return self._result(
                advisory=(
                    "Heavy rain on flat ground - low erosion risk but "
                    "check drainage."
                ),
                confidence=0.5,
                severity="info",
                rain_mm=rain,
                slope_percent=slope,
                risk_level="low",
            )

        # --- Light rain → minimal erosion risk ------------------------ #\
        if rain < LIGHT_RAIN_THRESHOLD:
            return self._result(
                advisory="Low rain - minimal erosion risk.",
                confidence=0.6,
                severity="info",
                rain_mm=rain,
                slope_percent=slope,
                risk_level="minimal",
            )

        # --- Catch-all (moderate rain on flat/moderate ground, or ----- #\
        #     heavy rain on a moderate 5–10 % slope)                    #\
        return self._result(
            advisory="Moderate rain - low erosion risk.",
            confidence=0.5,
            severity="info",
            rain_mm=rain,
            slope_percent=slope,
            risk_level="low",
        )

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _result(self, advisory, confidence, severity, rain_mm, slope_percent, risk_level):
        """Build an AdaptationResult with the standard data dict."""
        return AdaptationResult(
            module_name=self.name,
            category=self.category,
            timestamp=utc_now(),
            advisory=advisory,
            confidence=confidence,
            data={
                "rain_mm": rain_mm,
                "slope_percent": slope_percent,
                "risk_level": risk_level,
            },
            severity=severity,
        )