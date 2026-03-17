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
