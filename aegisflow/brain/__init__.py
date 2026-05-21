"""
AegisFlow Brain — GBrain-inspired ambient knowledge layer.

Ported from garrytan/gbrain:
- BrainFirstLookup: 5-step mandatory lookup before any external API call
- SignalDetector: always-on parallel ambient capture of ideas + entities
- BrainDoctor: filesystem-first health checker with health score
"""

from aegisflow.brain.doctor import (
    BrainDoctor,
    BrainHealthReport,
    HealthCheck,
    HealthStatus,
    run_doctor,
)
from aegisflow.brain.lookup import BrainFirstLookup, BrainLookupResult, brain_first
from aegisflow.brain.signal_detector import (
    SignalCapture,
    SignalDetector,
    SignalSummary,
)

__all__ = [
    # Lookup
    "BrainFirstLookup",
    "BrainLookupResult",
    "brain_first",
    # Signal
    "SignalDetector",
    "SignalSummary",
    "SignalCapture",
    # Doctor
    "BrainDoctor",
    "BrainHealthReport",
    "HealthCheck",
    "HealthStatus",
    "run_doctor",
]
