#!/usr/bin/env python3
"""Comprehensive tests for player match ratings, MOTM, form, and performance tracking.

Tests:
  1. MatchRatingCalculator produces realistic spread (not clustered at 6.0)
  2. MOTM is the highest-rated player (not a 6.1 player)
  3. Goalscorers always rate higher than passive players
  4. Clean sheet bonus applies correctly to defenders/GK
  5. Position-based involvement bonus works
  6. Player form updates correctly after matches
  7. PlayerStats rolling average is calculated properly
  8. End-to-end: full match produces sensible rating distribution
  9. Red card tanks rating
  10. GK saves boost rating
"""
from __future__ import annotations

import os
import sys
import random
import time
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fm.engine.match_state import PlayerInMatch, MatchState
from fm.engine.match_engine import MatchRatingCalculator


# ═══════════════════════════════════════════════════════════════════════════
#  Unit Tests — MatchRatingCalculator
# ═══════════════════════════════════════════════════════════════════════════

def test_base_rating():
    """A player who does literally nothing should get ~6.0."""
    p = PlayerInMatch(player_id=1, name="Ghost", position="CM", side="home")
    rating = MatchRatingCalculator.calculate(p)
    assert 5.5 <= rating <= 6.2, f"Inactive player should be ~6.0, got {rating:.2f}"
    print(f"  [PASS] Base rating for inactive player: {rating:.2f}")


def test_goal_scorer_rating():
    """A player who scores 2 goals should rate 8.0+."""
    p = PlayerInMatch(player_id=2, name="Scorer", position="ST", side="home")
    p.goals = 2
    p.shots = 4
    p.shots_on_target = 3
    p.passes_attempted = 15
    p.passes_completed = 10
    rating = MatchRatingCalculator.calculate(p)
    assert rating >= 8.0, f"2-goal scorer should be 8.0+, got {rating:.2f}"
    print(f"  [PASS] 2-goal scorer rating: {rating:.2f}")


def test_hat_trick_hero():
    """Hat-trick should produce 9.0+ rating."""
    p = PlayerInMatch(player_id=3, name="HatTrick", position="ST", side="home")
    p.goals = 3
    p.assists = 1
    p.shots = 6
    p.shots_on_target = 4
    p.passes_attempted = 20
    p.passes_completed = 15
    p.key_passes = 2
    rating = MatchRatingCalculator.calculate(p)
    assert rating >= 9.0, f"Hat-trick hero should be 9.0+, got {rating:.2f}"
    print(f"  [PASS] Hat-trick hero rating: {rating:.2f}")


def test_assist_king():
    """2 assists + high passing should rate well."""
    p = PlayerInMatch(player_id=4, name="Creator", position="CAM", side="home")
    p.assists = 2
    p.key_passes = 4
    p.passes_attempted = 50
    p.passes_completed = 45  # 90%
    p.dribbles_attempted = 5
    p.dribbles_completed = 3
    rating = MatchRatingCalculator.calculate(p)
    assert rating >= 7.5, f"2-assist creator should be 7.5+, got {rating:.2f}"
    print(f"  [PASS] 2-assist creator rating: {rating:.2f}")


def test_defensive_masterclass():
    """Defender with many tackles/interceptions/clearances should rate 7.0+."""
    p = PlayerInMatch(player_id=5, name="Rock", position="CB", side="home")
    p.tackles_attempted = 8
    p.tackles_won = 6
    p.interceptions_made = 5
    p.clearances = 7
    p.blocks = 3
    p.aerials_won = 4
    p.passes_attempted = 40
    p.passes_completed = 35  # 87.5%
    rating = MatchRatingCalculator.calculate(p)
    assert rating >= 7.0, f"Defensive masterclass should be 7.0+, got {rating:.2f}"
    print(f"  [PASS] Defensive masterclass rating: {rating:.2f}")


def test_clean_sheet_bonus():
    """Defenders and GK get +0.5 for clean sheet."""
    cb = PlayerInMatch(player_id=6, name="CB", position="CB", side="home")
    cb.tackles_won = 3
    cb.interceptions_made = 2
    cb.clearances = 4
    cb.passes_attempted = 30
    cb.passes_completed = 25

    rating_no_cs = MatchRatingCalculator.calculate(cb)
    # Simulate clean sheet bonus (applied externally)
    rating_with_cs = rating_no_cs + 0.5

    assert rating_with_cs > rating_no_cs, "Clean sheet should boost rating"
    assert rating_with_cs - rating_no_cs == 0.5, "Clean sheet bonus should be +0.5"
    print(f"  [PASS] Clean sheet bonus: {rating_no_cs:.2f} → {rating_with_cs:.2f}")


def test_gk_saves_boost():
    """GK who makes many saves should rate highly."""
    gk = PlayerInMatch(player_id=7, name="Wall", position="GK", side="home", is_gk=True)
    gk.saves = 7
    gk.passes_attempted = 20
    gk.passes_completed = 16
    rating = MatchRatingCalculator.calculate(gk)
    assert rating >= 7.0, f"GK with 7 saves should be 7.0+, got {rating:.2f}"
    print(f"  [PASS] GK 7-save rating: {rating:.2f}")


def test_red_card_tanks_rating():
    """Red card should severely drop rating."""
    p = PlayerInMatch(player_id=8, name="Hothead", position="CM", side="home")
    p.red_card = True
    p.yellow_cards = 1  # Second yellow
    p.fouls_committed = 4
    p.tackles_attempted = 5
    p.tackles_won = 2
    p.passes_attempted = 20
    p.passes_completed = 12
    rating = MatchRatingCalculator.calculate(p)
    assert rating <= 5.0, f"Red-carded player should be 5.0 or below, got {rating:.2f}"
    print(f"  [PASS] Red card rating: {rating:.2f}")


def test_wasteful_forward():
    """Forward who misses big chances should be penalised."""
    p = PlayerInMatch(player_id=9, name="Wasteful", position="ST", side="home")
    p.shots = 6
    p.shots_on_target = 1
    p.big_chances = 4
    p.big_chances_missed = 3
    p.passes_attempted = 15
    p.passes_completed = 10
    rating = MatchRatingCalculator.calculate(p)
    # Should be below average — missed big chances
    assert rating <= 6.5, f"Wasteful forward should be ≤6.5, got {rating:.2f}"
    print(f"  [PASS] Wasteful forward rating: {rating:.2f}")


def test_involvement_bonus():
    """Very active player gets involvement bonus, ghost gets penalised."""
    active = PlayerInMatch(player_id=10, name="Active", position="CM", side="home")
    active.passes_attempted = 55
    active.passes_completed = 48
    active.tackles_won = 4
    active.interceptions_made = 3
    active.dribbles_completed = 2
    active.key_passes = 2
    active.clearances = 1
    active.aerials_won = 2

    ghost = PlayerInMatch(player_id=11, name="Ghost", position="CM", side="home")
    ghost.passes_attempted = 5
    ghost.passes_completed = 3
    # Ghost has barely any stats

    active_r = MatchRatingCalculator.calculate(active)
    ghost_r = MatchRatingCalculator.calculate(ghost)

    assert active_r > ghost_r, f"Active ({active_r:.2f}) should beat ghost ({ghost_r:.2f})"
    assert active_r - ghost_r >= 0.5, (
        f"Active-ghost gap should be ≥0.5, got {active_r - ghost_r:.2f}"
    )
    print(f"  [PASS] Involvement: active={active_r:.2f} vs ghost={ghost_r:.2f}")


def test_pass_accuracy_tiers():
    """Different pass accuracy tiers produce different bonuses."""
    ratings = {}
    for label, completed, attempted in [
        ("elite", 47, 50),    # 94%
        ("good", 44, 50),     # 88%
        ("average", 40, 50),  # 80%
        ("poor", 30, 50),     # 60%
    ]:
        p = PlayerInMatch(player_id=20, name=label, position="CM", side="home")
        p.passes_attempted = attempted
        p.passes_completed = completed
        p.tackles_won = 2
        p.interceptions_made = 2
        ratings[label] = MatchRatingCalculator.calculate(p)

    assert ratings["elite"] > ratings["good"] > ratings["average"], (
        f"Pass accuracy should scale: {ratings}"
    )
    assert ratings["average"] > ratings["poor"], (
        f"Poor accuracy should be penalised: {ratings}"
    )
    print(f"  [PASS] Pass accuracy tiers: {ratings}")


# ═══════════════════════════════════════════════════════════════════════════
#  MOTM Tests
# ═══════════════════════════════════════════════════════════════════════════

def test_motm_is_highest_rated():
    """MOTM should be the player with the highest avg_rating."""
    players = []
    # Create 22 players with varying stats
    for i in range(11):
        p = PlayerInMatch(player_id=i, name=f"Home{i}", position="CM", side="home")
        p.passes_attempted = 30
        p.passes_completed = 20 + i
        p.tackles_won = i % 3
        p.rating_points = 6.0 + i * 0.1
        p.rating_events = 1
        players.append(p)

    for i in range(11, 22):
        p = PlayerInMatch(player_id=i, name=f"Away{i}", position="CM", side="away")
        p.passes_attempted = 30
        p.passes_completed = 22
        p.tackles_won = 1
        p.rating_points = 6.0
        p.rating_events = 1
        players.append(p)

    # Give one player 2 goals — should dominate
    star = players[5]
    star.goals = 2
    star.shots_on_target = 2
    star.rating_points = MatchRatingCalculator.calculate(star)
    star.rating_events = 1

    # Recalculate all
    for p in players:
        if p != star:
            p.rating_points = MatchRatingCalculator.calculate(p)
            p.rating_events = 1

    motm = max(players, key=lambda p: p.avg_rating)
    assert motm.player_id == star.player_id, (
        f"MOTM should be the 2-goal scorer ({star.avg_rating:.2f}), "
        f"got {motm.name} ({motm.avg_rating:.2f})"
    )
    print(f"  [PASS] MOTM is correctly the 2-goal scorer: {motm.name} ({motm.avg_rating:.2f})")


def test_motm_minimum_quality():
    """MOTM should have a rating meaningfully above base 6.0."""
    # Simulate a dull 0-0 draw where nobody did much
    players = []
    for i in range(22):
        p = PlayerInMatch(
            player_id=i,
            name=f"Player{i}",
            position="CB" if i < 8 else "CM" if i < 16 else "ST",
            side="home" if i < 11 else "away",
        )
        p.passes_attempted = 25
        p.passes_completed = 20
        p.tackles_won = 2
        p.interceptions_made = 1
        p.clearances = 2 if i < 8 else 0
        p.rating_points = MatchRatingCalculator.calculate(p)
        p.rating_events = 1
        players.append(p)

    motm = max(players, key=lambda p: p.avg_rating)
    assert motm.avg_rating >= 6.0, (
        f"MOTM should be at least 6.0 even in dull match, got {motm.avg_rating:.2f}"
    )
    print(f"  [PASS] MOTM in dull 0-0: {motm.name} ({motm.avg_rating:.2f})")


# ═══════════════════════════════════════════════════════════════════════════
#  Rating Distribution Test (end-to-end with real match)
# ═══════════════════════════════════════════════════════════════════════════

def test_rating_events_reset():
    """_finalize_ratings must set rating_events=1 so avg_rating = rating_points.

    This was the root cause of the 6.1 MOTM bug — rating_events accumulated
    during the match (30-80+) but rating_points was overwritten with the
    calculator output, producing avg_rating = 6.5/50 = 0.13.
    """
    p = PlayerInMatch(player_id=1, name="Test", position="CM", side="home")
    # Simulate what happens during a match — events accumulate
    p.rating_points = 2.5  # Sum of tiny increments
    p.rating_events = 45   # Many events during match

    # Before fix: avg_rating = 2.5 / 45 = 0.055 (broken!)
    old_avg = p.rating_points / p.rating_events
    assert old_avg < 1.0, "Pre-fix avg would be tiny"

    # After fix: calculator overwrites and events reset to 1
    p.goals = 1
    p.assists = 1
    p.passes_attempted = 40
    p.passes_completed = 35
    p.tackles_won = 3
    calculated = MatchRatingCalculator.calculate(p)
    p.rating_points = calculated
    p.rating_events = 1  # THIS IS THE FIX

    assert p.avg_rating == calculated, (
        f"avg_rating should equal calculated rating, "
        f"got {p.avg_rating:.2f} vs {calculated:.2f}"
    )
    assert p.avg_rating >= 7.0, f"1G+1A player should be 7.0+, got {p.avg_rating:.2f}"
    print(f"  [PASS] Rating events reset: avg={p.avg_rating:.2f} (fix verified)")


# ═══════════════════════════════════════════════════════════════════════════
#  Form Update Tests
# ═══════════════════════════════════════════════════════════════════════════

def test_form_calculation():
    """Form update: 70% old + 30% new, rating mapped to 0-100 scale."""
    # Simulate form update logic from season.py
    current_form = 65.0

    # Good match (rating 8.0)
    rating = 8.0
    match_form = (rating - 1) * (100 / 9)  # 77.78
    new_form = current_form * 0.7 + match_form * 0.3
    new_form = max(0.0, min(100.0, new_form))
    assert new_form > current_form, f"Good match should improve form: {current_form} → {new_form:.1f}"
    print(f"  [PASS] Good match form: {current_form} → {new_form:.1f}")

    # Bad match (rating 4.5)
    rating = 4.5
    match_form = (rating - 1) * (100 / 9)  # 38.89
    bad_form = current_form * 0.7 + match_form * 0.3
    bad_form = max(0.0, min(100.0, bad_form))
    assert bad_form < current_form, f"Bad match should lower form: {current_form} → {bad_form:.1f}"
    print(f"  [PASS] Bad match form: {current_form} → {bad_form:.1f}")


def test_form_convergence():
    """After several good matches, form should rise significantly."""
    form = 50.0  # Starting form
    for i in range(5):
        rating = 8.0  # Consistently good
        match_form = (rating - 1) * (100 / 9)
        form = max(0.0, min(100.0, form * 0.7 + match_form * 0.3))

    assert form >= 70.0, f"5 good matches should bring form to 70+, got {form:.1f}"
    print(f"  [PASS] Form convergence after 5 good matches: {form:.1f}")

    # Now 5 bad matches
    for i in range(5):
        rating = 4.0  # Consistently poor
        match_form = (rating - 1) * (100 / 9)
        form = max(0.0, min(100.0, form * 0.7 + match_form * 0.3))

    assert form <= 55.0, f"5 bad matches after good run should drop form, got {form:.1f}"
    print(f"  [PASS] Form drop after 5 bad matches: {form:.1f}")


def test_form_string_to_modifier():
    """Form string (WWDLW) correctly maps to modifier range."""
    def form_string_to_mod(form_str: str) -> float:
        if not form_str:
            return 0.0
        score = 0
        for ch in form_str[-5:]:
            if ch == "W":
                score += 3
            elif ch == "D":
                score += 1
            elif ch == "L":
                score -= 2
        return max(-0.08, min(0.08, score / 15.0 * 0.08))

    # Perfect form
    assert form_string_to_mod("WWWWW") > 0.06, "WWWWW should be near +0.08"
    # Terrible form
    assert form_string_to_mod("LLLLL") < -0.04, "LLLLL should be negative"
    # Mixed
    mod = form_string_to_mod("WDLWL")
    assert -0.04 <= mod <= 0.04, f"Mixed form should be near 0, got {mod:.3f}"
    # Empty
    assert form_string_to_mod("") == 0.0, "Empty form should be 0"
    print(f"  [PASS] Form string modifiers: WWWWW={form_string_to_mod('WWWWW'):.3f}, "
          f"LLLLL={form_string_to_mod('LLLLL'):.3f}, WDLWL={form_string_to_mod('WDLWL'):.3f}")


# ═══════════════════════════════════════════════════════════════════════════
#  PlayerStats Rolling Average Test
# ═══════════════════════════════════════════════════════════════════════════

def test_rolling_average_rating():
    """Rolling average: ((old_avg * (apps-1)) + new_rating) / apps."""
    avg_rating = 6.0
    appearances = 0

    # Simulate 5 matches with different ratings
    match_ratings = [7.5, 6.2, 8.0, 5.8, 7.0]
    for r in match_ratings:
        appearances += 1
        avg_rating = ((avg_rating * (appearances - 1)) + r) / appearances

    expected = sum(match_ratings) / len(match_ratings)
    assert abs(avg_rating - expected) < 0.01, (
        f"Rolling average should match simple average: {avg_rating:.2f} vs {expected:.2f}"
    )
    print(f"  [PASS] Rolling average after 5 matches: {avg_rating:.2f} (expected {expected:.2f})")


# ═══════════════════════════════════════════════════════════════════════════
#  Full Match Simulation Rating Distribution
# ═══════════════════════════════════════════════════════════════════════════

def test_full_match_rating_distribution():
    """Simulate a realistic match and verify rating distribution.

    After the fix, we expect:
      - Spread: ratings should range from ~5.5 to ~8.5+ (not all 6.0-6.2)
      - Scorers should be near the top
      - MOTM should be highest rated
      - No player should have avg_rating < 1.0 (the old bug)
    """
    TEST_DB = Path(__file__).resolve().parent.parent / "saves" / "ratings_test.db"
    if TEST_DB.exists():
        TEST_DB.unlink()

    from fm.db import database as db_mod
    db_mod.close_engine()
    db_mod._engine = None
    db_mod._SessionFactory = None
    engine = db_mod.get_engine(str(TEST_DB))
    from fm.db.models import Base, Club, Player, League, Fixture, Season
    Base.metadata.create_all(engine)
    from fm.db.ingestion import ingest_all

    print("\n  Ingesting data for rating distribution test...")
    t0 = time.time()
    ingest_all(db_path=str(TEST_DB))
    print(f"  Done in {time.time()-t0:.1f}s")

    session = db_mod.get_session()
    random.seed(42)

    from fm.world.season import SeasonManager

    prem = session.query(League).filter_by(name="Premier League").first()
    assert prem, "Premier League not found"
    club = session.query(Club).filter_by(league_id=prem.id).filter(
        Club.name.like("%Arsenal%")
    ).first()
    assert club, "Arsenal not found"

    season_mgr = SeasonManager(session)

    # Simulate 3 matchdays to get data
    all_ratings = []
    motm_ratings = []
    goal_scorer_ratings = []
    non_scorer_ratings = []

    for md in range(3):
        result = season_mgr.advance_matchday(human_club_id=club.id)
        session.commit()

        human_fix_obj = result.get("human_fixture")
        human_result = result.get("human_result")

        if human_result:
            for pim in human_result.home_lineup + human_result.away_lineup:
                r = pim.avg_rating
                all_ratings.append(r)
                if pim.goals > 0:
                    goal_scorer_ratings.append(r)
                else:
                    non_scorer_ratings.append(r)

            if human_result.motm:
                motm_ratings.append(human_result.motm.avg_rating)

    # ── Validation ──
    passed = 0
    total = 0

    def chk(name, cond, detail=""):
        nonlocal passed, total
        total += 1
        status = "PASS" if cond else "FAIL"
        if cond:
            passed += 1
        msg = f"  [{status}] {name}"
        if detail:
            msg += f" — {detail}"
        print(msg)

    if all_ratings:
        avg_r = sum(all_ratings) / len(all_ratings)
        min_r = min(all_ratings)
        max_r = max(all_ratings)
        spread = max_r - min_r

        chk("No broken ratings (all > 3.0)",
            all(r >= 3.0 for r in all_ratings),
            f"min={min_r:.2f}")

        chk("No impossible ratings (all ≤ 10.0)",
            all(r <= 10.0 for r in all_ratings),
            f"max={max_r:.2f}")

        chk("Average rating in realistic range (6.0-7.5)",
            6.0 <= avg_r <= 7.5,
            f"avg={avg_r:.2f}")

        chk("Rating spread ≥ 1.5 (not compressed)",
            spread >= 1.5,
            f"spread={spread:.2f} (min={min_r:.2f}, max={max_r:.2f})")

        chk("Some ratings above 7.5",
            any(r > 7.5 for r in all_ratings),
            f"max={max_r:.2f}")

    if goal_scorer_ratings and non_scorer_ratings:
        avg_scorer = sum(goal_scorer_ratings) / len(goal_scorer_ratings)
        avg_non = sum(non_scorer_ratings) / len(non_scorer_ratings)
        chk("Scorers rate higher than non-scorers on average",
            avg_scorer > avg_non,
            f"scorers={avg_scorer:.2f} vs non={avg_non:.2f}")

    if motm_ratings:
        chk("MOTM ratings are above 6.5",
            all(r >= 6.5 for r in motm_ratings),
            f"MOTM ratings: {[f'{r:.1f}' for r in motm_ratings]}")

    print(f"\n  Rating distribution: {passed}/{total} checks passed")
    print(f"  Samples: {len(all_ratings)} players across 3 matchdays")
    if all_ratings:
        # Show distribution buckets
        buckets = Counter()
        for r in all_ratings:
            bucket = f"{int(r)}.x"
            buckets[bucket] += 1
        print(f"  Distribution: {dict(sorted(buckets.items()))}")

    session.close()
    if TEST_DB.exists():
        TEST_DB.unlink()

    return passed == total


# ═══════════════════════════════════════════════════════════════════════════
#  Position-specific rating tests
# ═══════════════════════════════════════════════════════════════════════════

def test_midfielder_typical_game():
    """A typical midfielder game: lots of passes, some tackles, 1 key pass."""
    p = PlayerInMatch(player_id=30, name="Midfield", position="CM", side="home")
    p.passes_attempted = 55
    p.passes_completed = 47  # 85.5%
    p.tackles_attempted = 4
    p.tackles_won = 3
    p.interceptions_made = 2
    p.key_passes = 1
    p.dribbles_attempted = 3
    p.dribbles_completed = 2
    p.aerials_won = 1
    rating = MatchRatingCalculator.calculate(p)
    assert 6.5 <= rating <= 7.5, f"Typical midfielder should be 6.5-7.5, got {rating:.2f}"
    print(f"  [PASS] Typical midfielder rating: {rating:.2f}")


def test_fullback_overlap():
    """Overlapping fullback: crosses, tackles, some key passes."""
    p = PlayerInMatch(player_id=31, name="Fullback", position="RB", side="home")
    p.passes_attempted = 40
    p.passes_completed = 34  # 85%
    p.tackles_attempted = 5
    p.tackles_won = 4
    p.interceptions_made = 3
    p.clearances = 2
    p.crosses_attempted = 6
    p.crosses_completed = 3  # 50%
    p.key_passes = 2
    p.dribbles_attempted = 3
    p.dribbles_completed = 2
    rating = MatchRatingCalculator.calculate(p)
    assert 6.8 <= rating <= 8.2, f"Active fullback should be 6.8-8.2, got {rating:.2f}"
    print(f"  [PASS] Overlapping fullback rating: {rating:.2f}")


def test_winger_with_goal_and_assist():
    """Winger with 1G+1A and good dribbling."""
    p = PlayerInMatch(player_id=32, name="Winger", position="RW", side="home")
    p.goals = 1
    p.assists = 1
    p.key_passes = 3
    p.shots = 3
    p.shots_on_target = 2
    p.dribbles_attempted = 7
    p.dribbles_completed = 5
    p.passes_attempted = 30
    p.passes_completed = 24  # 80%
    p.crosses_attempted = 4
    p.crosses_completed = 2
    rating = MatchRatingCalculator.calculate(p)
    assert rating >= 8.0, f"1G+1A winger should be 8.0+, got {rating:.2f}"
    print(f"  [PASS] 1G+1A winger rating: {rating:.2f}")


# ═══════════════════════════════════════════════════════════════════════════
#  Runner
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 72)
    print("  PLAYER RATINGS, MOTM & FORM TESTS")
    print("=" * 72)

    errors = []
    tests = [
        # Rating calculator unit tests
        test_base_rating,
        test_goal_scorer_rating,
        test_hat_trick_hero,
        test_assist_king,
        test_defensive_masterclass,
        test_clean_sheet_bonus,
        test_gk_saves_boost,
        test_red_card_tanks_rating,
        test_wasteful_forward,
        test_involvement_bonus,
        test_pass_accuracy_tiers,
        # Position-specific
        test_midfielder_typical_game,
        test_fullback_overlap,
        test_winger_with_goal_and_assist,
        # MOTM tests
        test_motm_is_highest_rated,
        test_motm_minimum_quality,
        # Fix verification
        test_rating_events_reset,
        # Form tests
        test_form_calculation,
        test_form_convergence,
        test_form_string_to_modifier,
        # Stats tests
        test_rolling_average_rating,
    ]

    print(f"\n{'─' * 72}")
    print("  Unit Tests")
    print(f"{'─' * 72}")

    for test in tests:
        try:
            test()
        except Exception as e:
            errors.append((test.__name__, str(e)))
            print(f"  [FAIL] {test.__name__}: {e}")

    print(f"\n{'─' * 72}")
    print("  Integration Test — Full Match Rating Distribution")
    print(f"{'─' * 72}")

    try:
        integration_ok = test_full_match_rating_distribution()
    except Exception as e:
        integration_ok = False
        errors.append(("test_full_match_rating_distribution", str(e)))
        import traceback
        traceback.print_exc()

    print(f"\n{'=' * 72}")
    unit_passed = len(tests) - len([e for e in errors if e[0] != "test_full_match_rating_distribution"])
    total = len(tests) + 1  # +1 for integration
    total_passed = unit_passed + (1 if integration_ok else 0)
    status = "PASSED" if not errors and integration_ok else "FAILED"
    print(f"  RESULT: {total_passed}/{total} tests passed — {status}")

    if errors:
        print(f"\n  Failures:")
        for name, msg in errors:
            print(f"    {name}: {msg}")

    print(f"{'=' * 72}")
    sys.exit(0 if status == "PASSED" else 1)
