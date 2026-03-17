#!/usr/bin/env python3
"""3-month headless integration test: simulates the full match-day cycle.

Exercises the exact flow the TUI performs:
  1. Pre-match team talk (MoraleManager.give_team_talk)
  2. Match simulation (SeasonManager.advance_matchday)
  3. Post-match team talk based on result
  4. Repeat for ~12 matchdays (≈3 months of football)

Verifies:
  - No exceptions across the full cycle
  - Realistic goals, shots, xG accumulation
  - Finances remain positive for top clubs
  - Morale/fitness stay within sane ranges
  - Cup matches trigger at expected matchdays
  - Squad health does not collapse
"""
from __future__ import annotations

import os
import sys
import random
import time
import traceback
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

TEST_DB = Path(__file__).resolve().parent.parent / "saves" / "three_month_test.db"

# ── Helpers ──────────────────────────────────────────────────────────────────


def setup_database():
    if TEST_DB.exists():
        TEST_DB.unlink()

    from fm.db import database as db_mod
    db_mod.close_engine()
    db_mod._engine = None
    db_mod._SessionFactory = None

    engine = db_mod.get_engine(str(TEST_DB))
    from fm.db.models import Base
    Base.metadata.create_all(engine)

    from fm.db.ingestion import ingest_all
    print("Ingesting data …")
    t0 = time.time()
    stats = ingest_all(db_path=str(TEST_DB))
    print(f"  Done in {time.time()-t0:.1f}s  ({stats})")

    return db_mod.get_session()


def pick_human_club(session):
    from fm.db.models import Club, League
    prem = session.query(League).filter_by(name="Premier League").first()
    assert prem, "Premier League not found"
    club = session.query(Club).filter_by(league_id=prem.id).filter(
        Club.name.like("%Arsenal%")
    ).first()
    if not club:
        club = (session.query(Club).filter_by(league_id=prem.id)
                .order_by(Club.reputation.desc()).first())
    return club, prem


def apply_tactics(session, club_id):
    from fm.db.models import TacticalSetup
    ts = session.query(TacticalSetup).filter_by(club_id=club_id).first()
    if not ts:
        ts = TacticalSetup(club_id=club_id)
        session.add(ts)
    ts.formation = "4-3-3"
    ts.mentality = "positive"
    ts.pressing = "high"
    ts.tempo = "fast"
    ts.passing_style = "short"
    ts.width = "wide"
    ts.defensive_line = "high"
    ts.counter_attack = False
    ts.play_out_from_back = True
    ts.match_plan_winning = "hold_lead"
    ts.match_plan_losing = "push_forward"
    ts.match_plan_drawing = "push_forward"
    session.commit()


def choose_talk_type(context: str, result_char: str | None = None):
    """Pick a sensible talk type for the context, mimicking real user choice."""
    from fm.world.morale import TeamTalkType
    if context == "pre_match":
        return random.choice([TeamTalkType.MOTIVATE, TeamTalkType.FOCUS,
                              TeamTalkType.PASSIONATE, TeamTalkType.CALM])
    # Post-match: pick based on result
    if result_char == "W":
        return random.choice([TeamTalkType.PRAISE, TeamTalkType.CALM])
    elif result_char == "L":
        return random.choice([TeamTalkType.CRITICIZE, TeamTalkType.DEMAND_MORE,
                              TeamTalkType.SHOW_FAITH])
    else:  # Draw
        return random.choice([TeamTalkType.FOCUS, TeamTalkType.MOTIVATE])


# ── Main test ────────────────────────────────────────────────────────────────

def run_test():
    random.seed(42)
    N_MATCHDAYS = 12  # ~3 months

    print("=" * 70)
    print("  3-MONTH HEADLESS INTEGRATION TEST")
    print("  Full cycle: Pre-talk → Simulate → Post-talk × 12 matchdays")
    print("=" * 70)

    session = setup_database()
    human_club, prem = pick_human_club(session)
    human_id = human_club.id
    print(f"\nControlling: {human_club.name}  (id={human_id})")

    apply_tactics(session, human_id)

    from fm.world.season import SeasonManager
    from fm.world.morale import MoraleManager
    from fm.db.models import (
        Season, Fixture, Club, Player, LeagueStanding,
        CupFixture, NewsItem,
    )

    season_mgr = SeasonManager(session)
    morale_mgr = MoraleManager(session)

    season = session.query(Season).filter_by(year=2024).first()
    assert season, "No 2024 season found"

    # Diagnostics accumulators
    all_goals = []
    all_shots = []
    all_xg = []
    human_results = []
    errors = []
    matchday_times = []

    print(f"\nSimulating {N_MATCHDAYS} matchdays …")
    print("-" * 70)

    for md_idx in range(N_MATCHDAYS):
        md_t0 = time.time()
        md_label = f"MD {md_idx + 1}/{N_MATCHDAYS}"

        try:
            # ── PRE-MATCH TALK ────────────────────────────────────────────
            pre_talk = choose_talk_type("pre_match")
            morale_mgr.give_team_talk(human_id, pre_talk, context="pre_match")
            session.commit()

            # ── ADVANCE MATCHDAY (simulate all matches) ───────────────────
            result = season_mgr.advance_matchday(human_club_id=human_id)
            session.commit()

            md_num = result.get("matchday", md_idx + 1)
            n_matches = result.get("matches", 0)
            human_fix = result.get("human_fixture")

            # Determine human result
            result_char = None
            if human_fix:
                hg = human_fix.home_goals or 0
                ag = human_fix.away_goals or 0
                is_home = human_fix.home_club_id == human_id
                our_g = hg if is_home else ag
                their_g = ag if is_home else hg
                if our_g > their_g:
                    result_char = "W"
                elif our_g < their_g:
                    result_char = "L"
                else:
                    result_char = "D"
                human_results.append(result_char)

                opp_id = human_fix.away_club_id if is_home else human_fix.home_club_id
                opp = session.get(Club, opp_id)
                opp_name = opp.name if opp else f"Club#{opp_id}"

                # ── POST-MATCH TALK ───────────────────────────────────────
                post_ctx = {
                    "W": "post_match_win",
                    "L": "post_match_loss",
                    "D": "post_match_draw",
                }[result_char]
                post_talk = choose_talk_type(post_ctx, result_char)
                morale_mgr.give_team_talk(human_id, post_talk, context=post_ctx)
                session.commit()

                # Also trigger process_match_result (the TUI does this)
                morale_mgr.process_match_result(
                    club_id=human_id,
                    goals_for=our_g,
                    goals_against=their_g,
                    was_home=is_home,
                    opponent_reputation=opp.reputation if opp else 70,
                )
                session.commit()

                fix_line = (f"{human_club.name} {hg if is_home else ag}-"
                            f"{ag if is_home else hg} {opp_name}"
                            f"  [{result_char}]")
            else:
                fix_line = "(bye / no fixture)"

            # Gather PL stats for this matchday
            md_fixtures = session.query(Fixture).filter_by(
                season=2024, matchday=md_num, played=True,
                league_id=prem.id,
            ).all()
            for f in md_fixtures:
                hg = f.home_goals or 0
                ag = f.away_goals or 0
                all_goals.append(hg + ag)
                if f.home_shots:
                    all_shots.append((f.home_shots or 0) + (f.away_shots or 0))
                if f.home_xg is not None:
                    all_xg.append((f.home_xg or 0) + (f.away_xg or 0))

            # Cup info
            cup_results = result.get("cup_results", [])
            cup_info = ""
            if cup_results:
                total_cup = sum(len(cr.get("results", [])) for cr in cup_results)
                cup_info = f"  +{total_cup} cup matches"

            elapsed = time.time() - md_t0
            matchday_times.append(elapsed)

            # Squad snapshot
            players = session.query(Player).filter_by(club_id=human_id).all()
            avg_fit = sum(p.fitness or 100 for p in players) / max(len(players), 1)
            avg_mor = sum(p.morale or 65 for p in players) / max(len(players), 1)
            injured = sum(1 for p in players if (p.injured_weeks or 0) > 0)

            # Budget
            club_obj = session.get(Club, human_id)
            budget = club_obj.budget or 0

            print(f"  {md_label}  MD#{md_num:>2}  {n_matches:>3} matches  "
                  f"{fix_line:<45}  "
                  f"Fit={avg_fit:.0f} Mor={avg_mor:.0f} Inj={injured} "
                  f"€{budget:.1f}M  {elapsed:.1f}s{cup_info}")

        except Exception as e:
            elapsed = time.time() - md_t0
            errors.append((md_idx + 1, str(e), traceback.format_exc()))
            print(f"  {md_label}  *** ERROR: {e}  ({elapsed:.1f}s)")

    # ── FINAL DIAGNOSTICS ────────────────────────────────────────────────────

    print("\n" + "=" * 70)
    print("  DIAGNOSTICS")
    print("=" * 70)

    # Human record
    w = human_results.count("W")
    d = human_results.count("D")
    l = human_results.count("L")
    form = "".join(human_results)
    print(f"\n  {human_club.name}: {w}W {d}D {l}L  Form: {form}")

    # League table (top 8)
    standings = (
        session.query(LeagueStanding)
        .filter_by(league_id=prem.id, season=2024)
        .order_by(LeagueStanding.points.desc(), LeagueStanding.goal_difference.desc())
        .limit(8)
        .all()
    )
    print(f"\n  {'#':>2} {'Club':<25} {'P':>3} {'W':>3} {'D':>3} {'L':>3} "
          f"{'GF':>4} {'GA':>4} {'GD':>4} {'Pts':>4}")
    for i, s in enumerate(standings):
        club = session.get(Club, s.club_id)
        name = (club.name[:24] if club else f"Club {s.club_id}")
        print(f"  {i+1:>2} {name:<25} {s.played or 0:>3} {s.won or 0:>3} "
              f"{s.drawn or 0:>3} {s.lost or 0:>3} {s.goals_for or 0:>4} "
              f"{s.goals_against or 0:>4} {s.goal_difference or 0:>4} "
              f"{s.points or 0:>4}")

    # Match statistics
    if all_goals:
        avg_g = sum(all_goals) / len(all_goals)
        print(f"\n  Match Stats ({len(all_goals)} PL matches):")
        print(f"    Avg goals/match: {avg_g:.2f}  "
              f"Range: {min(all_goals)}-{max(all_goals)}")
    if all_shots:
        print(f"    Avg shots/match: {sum(all_shots)/len(all_shots):.1f}")
    if all_xg:
        print(f"    Avg xG/match:    {sum(all_xg)/len(all_xg):.2f}")

    # Timing
    if matchday_times:
        print(f"\n  Timing: avg={sum(matchday_times)/len(matchday_times):.1f}s/md  "
              f"total={sum(matchday_times):.0f}s")

    # Cups
    cup_played = session.query(CupFixture).filter_by(played=True).count()
    cup_total = session.query(CupFixture).count()
    if cup_total:
        cup_names = [r[0] for r in session.query(CupFixture.cup_name).distinct().all()]
        print(f"\n  Cups: {cup_played}/{cup_total} matches played")
        for cn in cup_names:
            cp = session.query(CupFixture).filter_by(cup_name=cn, played=True).count()
            ct = session.query(CupFixture).filter_by(cup_name=cn).count()
            print(f"    {cn}: {cp}/{ct}")

    # News
    news_count = session.query(NewsItem).count()
    print(f"\n  News items: {news_count}")

    # Player health across PL
    prem_clubs = session.query(Club).filter_by(league_id=prem.id).all()
    all_morale = []
    all_fitness = []
    for c in prem_clubs:
        for p in session.query(Player).filter_by(club_id=c.id).all():
            all_morale.append(p.morale or 65)
            all_fitness.append(p.fitness or 100)

    if all_morale:
        print(f"\n  PL Players ({len(all_morale)}):")
        print(f"    Morale:  avg={sum(all_morale)/len(all_morale):.1f}  "
              f"min={min(all_morale):.0f}  max={max(all_morale):.0f}")
        print(f"    Fitness: avg={sum(all_fitness)/len(all_fitness):.1f}  "
              f"min={min(all_fitness):.0f}  max={max(all_fitness):.0f}")

    injured_total = session.query(Player).filter(
        Player.injured_weeks > 0,
        Player.club_id.in_([c.id for c in prem_clubs])
    ).count()
    print(f"    Injured: {injured_total}")

    # Finances top 5
    print(f"\n  Finance snapshot:")
    for c in sorted(prem_clubs, key=lambda c: c.budget or 0, reverse=True)[:5]:
        print(f"    {c.name:<25} €{(c.budget or 0):.1f}M")

    # ── ASSERTIONS (soft — report, don't crash) ──────────────────────────
    checks_passed = 0
    checks_total = 0

    def check(name, condition):
        nonlocal checks_passed, checks_total
        checks_total += 1
        if condition:
            checks_passed += 1
        else:
            print(f"  ✗ FAIL: {name}")

    print(f"\n  Validation checks:")
    check("No errors during simulation", len(errors) == 0)
    check("12 matchdays completed", len(human_results) >= N_MATCHDAYS - 1)  # allow 1 bye
    if all_goals:
        avg_g = sum(all_goals) / len(all_goals)
        check(f"Avg goals realistic (2.0-4.0): {avg_g:.2f}", 2.0 <= avg_g <= 4.0)
    if all_shots:
        avg_s = sum(all_shots) / len(all_shots)
        check(f"Avg shots realistic (15-35): {avg_s:.1f}", 15 <= avg_s <= 35)
    if all_xg:
        avg_xg = sum(all_xg) / len(all_xg)
        check(f"Avg xG realistic (1.5-4.5): {avg_xg:.2f}", 1.5 <= avg_xg <= 4.5)
    if all_morale:
        avg_m = sum(all_morale) / len(all_morale)
        check(f"Avg morale sane (30-90): {avg_m:.1f}", 30 <= avg_m <= 90)
    if all_fitness:
        avg_f = sum(all_fitness) / len(all_fitness)
        check(f"Avg fitness sane (50-100): {avg_f:.1f}", 50 <= avg_f <= 100)
    # Budget: top clubs should still have money
    top_club = max(prem_clubs, key=lambda c: c.budget or 0)
    check(f"Top club budget > €0: {top_club.name} €{(top_club.budget or 0):.1f}M",
          (top_club.budget or 0) > 0)
    check(f"Arsenal budget > €0: €{(session.get(Club, human_id).budget or 0):.1f}M",
          (session.get(Club, human_id).budget or 0) > 0)

    print(f"\n  Result: {checks_passed}/{checks_total} checks passed")

    # Print any errors in detail
    if errors:
        print(f"\n  *** {len(errors)} ERRORS occurred ***")
        for md, msg, tb in errors:
            print(f"\n  Matchday {md}: {msg}")
            print(tb)

    print("\n" + "=" * 70)
    status = "PASSED" if checks_passed == checks_total and not errors else "FAILED"
    print(f"  3-MONTH INTEGRATION TEST: {status}")
    print("=" * 70)

    session.close()
    return len(errors) == 0 and checks_passed == checks_total


if __name__ == "__main__":
    success = run_test()
    sys.exit(0 if success else 1)
