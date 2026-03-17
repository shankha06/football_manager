"""Maps event types to consequence chains and bootstraps the engine."""
from __future__ import annotations

from fm.core.event_bus import (
    CAPTAIN_INJURED,
    EventBus,
    FINANCIAL_OVERSPEND,
    MATCH_RESULT,
    OVERTRAINING,
    PLAYER_DROPPED,
    PLAYER_SOLD,
    PROMISE_BROKEN,
    YOUTH_PLAYED,
)
from fm.core.consequence_engine import ConsequenceEngine

# ── Consequence chain definitions ─────────────────────────────────────────
#
# Each key is an event-bus event type.  The value is an ordered list of
# ``(handler_name, delay_matchdays)`` tuples describing the chain of effects
# that fire when the event is published.
#
# *delay_matchdays* is informational for now — the engine applies all
# delay-0 effects immediately.  Future versions can defer delayed effects
# via the Season tick.

CONSEQUENCE_CHAINS: dict[str, list[tuple[str, int]]] = {
    PLAYER_DROPPED: [
        ("morale_impact", 0),
        ("friend_reaction", 0),
        ("leadership_impact", 0),
    ],
    PLAYER_SOLD: [
        ("morale_impact", 0),
        ("fan_reaction", 0),
        ("squad_unrest", 1),
    ],
    PROMISE_BROKEN: [
        ("trust_impact", 0),
        ("happiness_impact", 0),
        ("transfer_request", 0),
    ],
    OVERTRAINING: [
        ("injury_risk_boost", 0),
        ("fitness_drain", 1),
    ],
    YOUTH_PLAYED: [
        ("development_boost", 0),
    ],
    FINANCIAL_OVERSPEND: [
        ("board_confidence_drop", 0),
        ("transfer_embargo", 0),
        ("ultimatum_check", 0),
    ],
    CAPTAIN_INJURED: [
        ("spirit_drop", 0),
        ("squad_morale_drop", 0),
    ],
    MATCH_RESULT: [
        ("board_confidence_adjust", 0),
    ],
}


def register_all(engine: ConsequenceEngine, bus: EventBus) -> None:
    """Register every consequence handler on *bus* via *engine*.

    This is the single entry-point the game bootstrap should call after
    creating the :class:`ConsequenceEngine` and the :class:`EventBus`.
    """
    engine.register_handlers(bus)
