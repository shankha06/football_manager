"""EWMA-based form calculation from recent match performances."""
from __future__ import annotations

from sqlalchemy.orm import Session

from fm.db.models import FormHistory
from fm.utils.helpers import clamp


class FormTracker:
    """Tracks and computes player form using an Exponentially Weighted Moving Average."""

    # Weights for last 5 matches (most recent first)
    WEIGHTS: list[float] = [0.35, 0.25, 0.20, 0.12, 0.08]

    # ── Form calculation ──────────────────────────────────────────────────

    @staticmethod
    def calculate_form(session: Session, player_id: int, current_season: int) -> float:
        """Compute EWMA form on a 0-100 scale from recent :class:`FormHistory` entries.

        Mapping from match-rating (1-10) to the 0-100 scale:
            6.0 -> 50,  7.0 -> 65,  8.0 -> 80,  9.0 -> 95,  5.0 -> 35, etc.

        If fewer than 5 records exist, only the available weights are used
        (re-normalised).  Minutes adjustment: entries where *minutes_played*
        < 45 have their weight halved.
        """
        entries: list[FormHistory] = (
            session.query(FormHistory)
            .filter(
                FormHistory.player_id == player_id,
                FormHistory.season == current_season,
            )
            .order_by(FormHistory.matchday.desc())
            .limit(5)
            .all()
        )

        if not entries:
            return 50.0  # neutral default

        weights = FormTracker.WEIGHTS[: len(entries)]

        weighted_sum = 0.0
        weight_total = 0.0
        for entry, w in zip(entries, weights):
            # Halve weight for sub-appearances (< 45 min)
            effective_weight = w * 0.5 if entry.minutes_played < 45 else w
            # Convert 1-10 rating to 0-100 scale
            scaled_rating = FormTracker._rating_to_scale(entry.rating)
            weighted_sum += scaled_rating * effective_weight
            weight_total += effective_weight

        if weight_total == 0.0:
            return 50.0

        return round(clamp(weighted_sum / weight_total, 0.0, 100.0), 1)

    # ── Recording ─────────────────────────────────────────────────────────

    @staticmethod
    def record_performance(
        session: Session,
        player_id: int,
        fixture_id: int,
        rating: float,
        minutes: int,
        season: int,
        matchday: int,
    ) -> FormHistory:
        """Create (or update) a :class:`FormHistory` entry for one match.

        Returns the created / updated row.
        """
        existing: FormHistory | None = (
            session.query(FormHistory)
            .filter_by(player_id=player_id, fixture_id=fixture_id)
            .first()
        )

        if existing is not None:
            existing.rating = rating
            existing.minutes_played = minutes
            existing.matchday = matchday
            return existing

        entry = FormHistory(
            player_id=player_id,
            fixture_id=fixture_id,
            season=season,
            rating=rating,
            minutes_played=minutes,
            matchday=matchday,
        )
        session.add(entry)
        return entry

    # ── Trend / history ───────────────────────────────────────────────────

    @staticmethod
    def get_form_trend(
        session: Session, player_id: int, n_matches: int = 10,
    ) -> list[float]:
        """Return the last *n_matches* match ratings (oldest first) for graphing."""
        entries: list[FormHistory] = (
            session.query(FormHistory)
            .filter(FormHistory.player_id == player_id)
            .order_by(FormHistory.matchday.desc())
            .limit(n_matches)
            .all()
        )
        # Reverse so oldest is first (natural left-to-right timeline)
        return [e.rating for e in reversed(entries)]

    # ── Internal helpers ──────────────────────────────────────────────────

    @staticmethod
    def _rating_to_scale(rating: float) -> float:
        """Convert a 1-10 match rating to a 0-100 form scale.

        Linear mapping where 6.0 = 50, 7.0 = 65, 8.0 = 80, etc.
        Slope is 15 per 1.0 rating point; anchor at 6.0 -> 50.
        """
        return clamp(50.0 + (rating - 6.0) * 15.0, 0.0, 100.0)
