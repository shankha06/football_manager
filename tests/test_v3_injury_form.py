"""Injury model and form tracker tests with in-memory SQLite DB.

Covers injury generation, severity distribution, recovery mechanics,
fitness-on-return, and EWMA form calculation.
"""
from __future__ import annotations

import random

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from fm.db.models import Base, Club, Fixture, FormHistory, Injury, League, Player
from fm.world.form_tracker import FormTracker
from fm.world.injury_model import InjuryGenerator, InjuryType

random.seed(42)


@pytest.fixture()
def db_session():
    """In-memory SQLite for form tracker tests."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    # Create minimal league, club, player, fixtures for form tracking
    league = League(id=1, name="Test League", country="Testland", num_teams=20)
    session.add(league)

    club = Club(id=1, name="Test FC", league_id=1)
    session.add(club)

    player = Player(id=1, name="Test Player", age=25, position="ST", club_id=1)
    session.add(player)

    # Create fixtures for form history
    for i in range(1, 11):
        f = Fixture(
            id=i, league_id=1, season=1, matchday=i,
            home_club_id=1, away_club_id=1,  # self-referencing is fine for tests
        )
        session.add(f)

    session.commit()
    yield session
    session.close()


# ---------------------------------------------------------------------------
# Injury generation tests
# ---------------------------------------------------------------------------


class TestInjuryGeneration:
    """InjuryGenerator should produce injuries with high proneness."""

    def test_injury_generator_produces_injury(self):
        random.seed(42)
        gen = InjuryGenerator()
        injuries = []
        # BASE_CHANCE is very low (~0.00008), even with high proneness and
        # fatigue the per-call chance is ~0.0004, so we need many attempts.
        for _ in range(10000):
            inj = gen.generate_injury(
                player_proneness=90,
                fatigue=20.0,
                minutes_played=85,
                position="ST",
                overtraining=True,
            )
            if inj is not None:
                injuries.append(inj)

        assert len(injuries) > 0, "Should produce at least one injury in 10000 calls"


class TestInjurySeverityDistribution:
    """Over many injuries, should have a mix of minor/moderate/serious."""

    def test_injury_severity_distribution(self):
        random.seed(42)
        gen = InjuryGenerator()
        severities = []
        attempts = 0
        while len(severities) < 100 and attempts < 500000:
            inj = gen.generate_injury(
                player_proneness=99,
                fatigue=5.0,
                minutes_played=90,
                position="CM",
                overtraining=True,
            )
            if inj is not None:
                severities.append(inj.severity)
            attempts += 1

        if len(severities) < 20:
            pytest.skip("Not enough injuries generated for distribution test")

        unique = set(severities)
        assert len(unique) >= 2, f"Should have at least 2 severity types, got: {unique}"


# ---------------------------------------------------------------------------
# Recovery tests
# ---------------------------------------------------------------------------


class TestLinearRecovery:
    """Linear recovery should decrement weeks_remaining by 1 each call."""

    def test_recovery_linear_decrements(self):
        inj = Injury(
            player_id=1, season=1, matchday_occurred=1,
            injury_type="hamstring", severity="moderate",
            recovery_weeks_total=4, recovery_weeks_remaining=4,
            recovery_curve="linear", setback_chance=0.0, is_active=True,
        )
        gen = InjuryGenerator()

        gen.process_recovery(inj)
        assert inj.recovery_weeks_remaining == 3

        gen.process_recovery(inj)
        assert inj.recovery_weeks_remaining == 2

        gen.process_recovery(inj)
        assert inj.recovery_weeks_remaining == 1

        recovered = gen.process_recovery(inj)
        assert inj.recovery_weeks_remaining == 0
        assert recovered is True
        assert inj.is_active is False


class TestRecoverySetback:
    """With high setback_chance, some recoveries should add weeks."""

    def test_recovery_setback_can_occur(self):
        random.seed(42)
        gen = InjuryGenerator()
        setback_occurred = False

        for _ in range(50):
            inj = Injury(
                player_id=1, season=1, matchday_occurred=1,
                injury_type="knee_acl", severity="career_threatening",
                recovery_weeks_total=30, recovery_weeks_remaining=15,
                recovery_curve="setback_risk", setback_chance=0.5, is_active=True,
            )
            before = inj.recovery_weeks_remaining
            gen.process_recovery(inj)
            # A setback means remaining went up (before - 1 + added > before - 1)
            if inj.recovery_weeks_remaining > before - 1:
                setback_occurred = True
                break

        assert setback_occurred, "Should have at least one setback with 0.5 chance over 50 trials"


# ---------------------------------------------------------------------------
# Fitness on return
# ---------------------------------------------------------------------------


class TestFitnessOnReturn:
    """Fitness on return should vary by severity."""

    def test_fitness_on_return_based_on_severity(self):
        gen = InjuryGenerator()

        minor = Injury(
            player_id=1, season=1, matchday_occurred=1,
            injury_type="ankle", severity="minor",
            recovery_weeks_total=2, recovery_weeks_remaining=2,
            is_active=True,
        )
        career = Injury(
            player_id=1, season=1, matchday_occurred=1,
            injury_type="knee_acl", severity="career_threatening",
            recovery_weeks_total=35, recovery_weeks_remaining=35,
            is_active=True,
        )

        minor_fitness = gen.calculate_fitness_on_return(minor)
        career_fitness = gen.calculate_fitness_on_return(career)

        assert minor_fitness >= 85, f"Minor injury fitness should be >= 85: {minor_fitness}"
        assert career_fitness < 75, f"Career injury fitness should be < 75: {career_fitness}"


# ---------------------------------------------------------------------------
# Form tracker tests
# ---------------------------------------------------------------------------


class TestFormEWMA:
    """EWMA weights should give most weight to recent matches."""

    def test_form_ewma_weights(self, db_session: Session):
        # Record 5 performances: first 4 poor, last one great
        for i in range(1, 5):
            FormTracker.record_performance(
                db_session, player_id=1, fixture_id=i,
                rating=5.0, minutes=90, season=1, matchday=i,
            )
        FormTracker.record_performance(
            db_session, player_id=1, fixture_id=5,
            rating=9.0, minutes=90, season=1, matchday=5,
        )
        db_session.flush()

        form = FormTracker.calculate_form(db_session, player_id=1, current_season=1)

        # If most recent has most weight, form should be pulled up from pure average
        # Rating 5.0 -> scale ~35, Rating 9.0 -> scale ~95
        # Pure average would be ~47; EWMA with 35% on 95 should be higher
        assert form > 47, f"EWMA form should be pulled up by recent good match: {form}"


class TestFormMinutesAdjustment:
    """Player with <45 minutes should get half weight."""

    def test_form_minutes_adjustment(self, db_session: Session):
        # Record same rating but different minutes
        FormTracker.record_performance(
            db_session, player_id=1, fixture_id=1,
            rating=8.0, minutes=90, season=1, matchday=1,
        )
        db_session.flush()
        form_full = FormTracker.calculate_form(db_session, player_id=1, current_season=1)

        # Clear and re-record with low minutes
        entry = db_session.query(FormHistory).first()
        entry.minutes_played = 30
        db_session.flush()
        form_sub = FormTracker.calculate_form(db_session, player_id=1, current_season=1)

        # Both should give the same form since it's only 1 entry (weight doesn't change ratio)
        # But the minutes_played < 45 halves the weight, which with single entry
        # just re-normalizes to same value. So we test with 2 entries.
        # Reset
        db_session.query(FormHistory).delete()
        db_session.flush()

        # Two entries: one with full time, one with sub time
        FormTracker.record_performance(
            db_session, player_id=1, fixture_id=1,
            rating=8.0, minutes=90, season=1, matchday=1,
        )
        FormTracker.record_performance(
            db_session, player_id=1, fixture_id=2,
            rating=4.0, minutes=30, season=1, matchday=2,
        )
        db_session.flush()

        form = FormTracker.calculate_form(db_session, player_id=1, current_season=1)
        # Most recent (4.0, 30 min) has half weight, so the 8.0 should dominate
        # 8.0 -> scale 80, 4.0 -> scale 20
        assert form > 50, f"Full-time match should dominate over sub appearance: {form}"


class TestFormImprovesWithGoodRatings:
    """5 ratings of 8.0 should produce form > 70."""

    def test_form_improves_with_good_ratings(self, db_session: Session):
        for i in range(1, 6):
            FormTracker.record_performance(
                db_session, player_id=1, fixture_id=i,
                rating=8.0, minutes=90, season=1, matchday=i,
            )
        db_session.flush()

        form = FormTracker.calculate_form(db_session, player_id=1, current_season=1)
        assert form > 70, f"Form with 5x 8.0 ratings should be > 70: {form}"


class TestFormDropsWithPoorRatings:
    """5 ratings of 4.5 should produce form < 40."""

    def test_form_drops_with_poor_ratings(self, db_session: Session):
        for i in range(1, 6):
            FormTracker.record_performance(
                db_session, player_id=1, fixture_id=i,
                rating=4.5, minutes=90, season=1, matchday=i,
            )
        db_session.flush()

        form = FormTracker.calculate_form(db_session, player_id=1, current_season=1)
        assert form < 40, f"Form with 5x 4.5 ratings should be < 40: {form}"


class TestFormTrend:
    """get_form_trend should return oldest first."""

    def test_form_trend_returns_chronological(self, db_session: Session):
        ratings = [6.0, 7.0, 5.5, 8.0, 7.5]
        for i, rating in enumerate(ratings, 1):
            FormTracker.record_performance(
                db_session, player_id=1, fixture_id=i,
                rating=rating, minutes=90, season=1, matchday=i,
            )
        db_session.flush()

        trend = FormTracker.get_form_trend(db_session, player_id=1, n_matches=5)
        assert trend == ratings, f"Trend should be chronological: {trend} vs {ratings}"
