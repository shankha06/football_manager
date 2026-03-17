"""Pub/sub event bus for consequence propagation across game systems."""
from __future__ import annotations

import threading
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable

# ── Event type constants ──────────────────────────────────────────────────

PLAYER_DROPPED = "player_dropped"
PLAYER_SOLD = "player_sold"
PROMISE_BROKEN = "promise_broken"
OVERTRAINING = "overtraining"
YOUTH_PLAYED = "youth_played"
FINANCIAL_OVERSPEND = "financial_overspend"
CAPTAIN_INJURED = "captain_injured"
MATCH_RESULT = "match_result"
MATCH_STATS = "match_stats"
PLAYER_INJURED = "player_injured"
TRANSFER_BID = "transfer_bid"
CONTRACT_EXPIRED = "contract_expired"
BOARD_WARNING = "board_warning"
TEAM_TALK = "team_talk"

# ── Cascading consequence event types ────────────────────────────────────
LOSING_STREAK = "losing_streak"
WINNING_STREAK = "winning_streak"
DRESSING_ROOM_TENSION = "dressing_room_tension"
MEDICAL_CRISIS = "medical_crisis"
FINANCIAL_CRISIS = "financial_crisis"
MANAGER_SACKED = "manager_sacked"
NARRATIVE_TRIGGERED = "narrative_triggered"

# ── Real-life match situation events ─────────────────────────────────────
RED_CARD_INCIDENT = "red_card_incident"
LATE_GOAL = "late_goal"
GOALKEEPER_ERROR = "goalkeeper_error"
MISSED_PENALTY = "missed_penalty"
DEFENSIVE_COLLAPSE = "defensive_collapse"
COMEBACK_VICTORY = "comeback_victory"
UPSET_VICTORY = "upset_victory"
GOAL_DROUGHT = "goal_drought"
SCORING_RUN = "scoring_run"
CLEAN_SHEET = "clean_sheet"
EARLY_RED_CARD = "early_red_card"
SHORT_TURNAROUND_MATCH = "short_turnaround_match"
YOUNG_PLAYER_DEBUT = "young_player_debut"
VETERAN_PERFORMANCE = "veteran_performance"
DERBY_MATCH = "derby_match"
RECURRING_INJURY = "recurring_injury"
VAR_CONTROVERSY = "var_controversy"
PENALTY_DECISION = "penalty_decision"
REFEREE_BIAS = "referee_bias"
OWN_GOAL = "own_goal"
SET_PIECE_FAILURE = "set_piece_failure"
SET_PIECE_SUCCESS = "set_piece_success"
PLAYER_FIGHT = "player_fight"
FIRST_MATCH_BACK = "first_match_back"
ILLNESS_OUTBREAK = "illness_outbreak"
WEATHER_EXTREME = "weather_extreme"
TRAVEL_FATIGUE = "travel_fatigue"
UNBEATEN_RUN_BROKEN = "unbeaten_run_broken"
HISTORIC_RECORD_BROKEN = "historic_record_broken"
PLAYER_SUBSTITUTION_DRAMA = "player_substitution_drama"
TACTICAL_MASTERCLASS = "tactical_masterclass"
MULTIPLE_INJURIES = "multiple_injuries"


@dataclass(order=True)
class _Subscription:
    """Internal wrapper that orders callbacks by priority (descending)."""

    priority: int
    callback: Callable[..., None] = field(compare=False)


class EventBus:
    """Thread-safe publish/subscribe event bus with priority ordering.

    Higher *priority* values run first.  All callbacks receive
    ``(event_type, **kwargs)`` as arguments.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # event_type -> sorted list of _Subscription (highest priority first)
        self._subscribers: dict[str, list[_Subscription]] = defaultdict(list)

    # ── Public API ────────────────────────────────────────────────────────

    def subscribe(
        self,
        event_type: str,
        callback: Callable[..., None],
        priority: int = 0,
    ) -> None:
        """Register *callback* for *event_type*.

        Callbacks with a higher *priority* value are invoked first.
        """
        sub = _Subscription(priority=priority, callback=callback)
        with self._lock:
            subs = self._subscribers[event_type]
            subs.append(sub)
            # Keep sorted descending by priority so we can iterate in order.
            subs.sort(key=lambda s: s.priority, reverse=True)

    def publish(self, event_type: str, **data: Any) -> None:
        """Fire *event_type* and call every registered callback in priority order."""
        with self._lock:
            subs = list(self._subscribers.get(event_type, []))
        for sub in subs:
            sub.callback(event_type, **data)

    def clear(self) -> None:
        """Remove all subscriptions."""
        with self._lock:
            self._subscribers.clear()


# ── Global singleton ──────────────────────────────────────────────────────

_bus_instance: EventBus | None = None
_bus_lock = threading.Lock()


def get_event_bus() -> EventBus:
    """Return (and lazily create) the global :class:`EventBus` singleton."""
    global _bus_instance
    if _bus_instance is None:
        with _bus_lock:
            if _bus_instance is None:
                _bus_instance = EventBus()
    return _bus_instance
