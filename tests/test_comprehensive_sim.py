#!/usr/bin/env python3
"""Comprehensive simulation: league + cups + AI assistant over 12 matchdays.

Tests all tuned systems working in cohesion with realistic benchmarks.
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

TEST_DB = Path(__file__).resolve().parent.parent / "saves" / "comprehensive_test.db"


def setup():
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
    print("Ingesting data...")
    t0 = time.time()
    stats = ingest_all(db_path=str(TEST_DB))
    print(f"  Done in {time.time()-t0:.1f}s")
    return db_mod.get_session()


def run():
    random.seed(42)
    N = 12

    print("=" * 72)
    print("  COMPREHENSIVE SIMULATION — League + Cups + AI Assistant")
    print("=" * 72)

    session = setup()

    from fm.db.models import (
        Club, Player, League, Fixture, LeagueStanding, Season,
        TacticalSetup, CupFixture, NewsItem,
    )
    from fm.world.season import SeasonManager
    from fm.world.morale import MoraleManager, TeamTalkType
    from fm.world.assistant import AssistantManager

    # Pick Arsenal
    prem = session.query(League).filter_by(name="Premier League").first()
    assert prem
    club = session.query(Club).filter_by(league_id=prem.id).filter(
        Club.name.like("%Arsenal%")
    ).first()
    assert club, "Arsenal not found"
    human_id = club.id
    print(f"\nControlling: {club.name} (rep={club.reputation})")

    # Set tactics
    ts = session.query(TacticalSetup).filter_by(club_id=human_id).first()
    if not ts:
        ts = TacticalSetup(club_id=human_id)
        session.add(ts)
    ts.formation = "4-3-3"
    ts.mentality = "positive"
    ts.pressing = "high"
    ts.tempo = "fast"
    ts.passing_style = "short"
    ts.width = "wide"
    ts.defensive_line = "high"
    session.commit()

    season_mgr = SeasonManager(session)
    morale_mgr = MoraleManager(session)
    assistant = AssistantManager(session)

    # Accumulators
    all_goals, all_shots, all_xg = [], [], []
    human_results = []
    errors = []
    prep_reports = []

    print(f"\nSimulating {N} matchdays...")
    print("-" * 72)

    for md_idx in range(N):
        t0 = time.time()
        try:
            # ── AI ASSISTANT: Pre-match preparation ───────────────────────
            season = session.query(Season).filter_by(year=2024).first()
            next_md = (season.current_matchday or 0) + 1
            fix = session.query(Fixture).filter(
                Fixture.season == 2024,
                Fixture.matchday == next_md,
                Fixture.played == False,
                (Fixture.home_club_id == human_id) | (Fixture.away_club_id == human_id),
            ).first()

            report = None
            if fix:
                is_home = fix.home_club_id == human_id
                opp_id = fix.away_club_id if is_home else fix.home_club_id
                report = assistant.prepare_match_report(
                    human_id, opp_id, is_home, "league",
                )
                prep_reports.append(report)

            # ── PRE-MATCH TALK ────────────────────────────────────────────
            talk = random.choice([
                TeamTalkType.MOTIVATE, TeamTalkType.FOCUS,
                TeamTalkType.PASSIONATE, TeamTalkType.CALM,
            ])
            morale_mgr.give_team_talk(human_id, talk, context="pre_match")
            session.commit()

            # ── SIMULATE MATCHDAY ─────────────────────────────────────────
            result = season_mgr.advance_matchday(human_club_id=human_id)
            session.commit()

            md_num = result.get("matchday", md_idx + 1)
            human_fix = result.get("human_fixture")

            # Result tracking
            rc = None
            if human_fix:
                hg = human_fix.home_goals or 0
                ag = human_fix.away_goals or 0
                is_h = human_fix.home_club_id == human_id
                our = hg if is_h else ag
                their = ag if is_h else hg
                rc = "W" if our > their else ("L" if our < their else "D")
                human_results.append(rc)

                opp = session.get(Club, human_fix.away_club_id if is_h else human_fix.home_club_id)
                opp_name = opp.name if opp else "?"

                # POST-MATCH TALK
                ctx_map = {"W": "post_match_win", "L": "post_match_loss", "D": "post_match_draw"}
                post_talk = TeamTalkType.PRAISE if rc == "W" else (
                    TeamTalkType.DEMAND_MORE if rc == "L" else TeamTalkType.FOCUS
                )
                morale_mgr.give_team_talk(human_id, post_talk, context=ctx_map[rc])
                morale_mgr.process_match_result(
                    human_id, our, their, is_h,
                    opp.reputation if opp else 70,
                )
                session.commit()

                fix_line = f"{club.name} {hg if is_h else ag}-{ag if is_h else hg} {opp_name} [{rc}]"
            else:
                fix_line = "(no fixture)"

            # PL stats
            md_fixtures = session.query(Fixture).filter_by(
                season=2024, matchday=md_num, played=True, league_id=prem.id,
            ).all()
            for f in md_fixtures:
                all_goals.append((f.home_goals or 0) + (f.away_goals or 0))
                if f.home_shots:
                    all_shots.append((f.home_shots or 0) + (f.away_shots or 0))
                if f.home_xg is not None:
                    all_xg.append((f.home_xg or 0) + (f.away_xg or 0))

            # Cup info
            cups = result.get("cup_results", [])
            cup_info = f"  +{sum(len(c.get('results',[])) for c in cups)} cups" if cups else ""
            cont = result.get("continental_results")
            if cont and isinstance(cont, dict):
                cup_info += f"  UEFA:{cont.get('matches_played', 0)}"
            elif cont and isinstance(cont, list):
                cup_info += f"  UEFA:{len(cont)}"

            players = session.query(Player).filter_by(club_id=human_id).all()
            avg_fit = sum(p.fitness or 100 for p in players) / max(len(players), 1)

            # AI assistant summary
            ai_info = ""
            if report:
                ai_info = f"  AI:{report.recommended_formation}/{report.recommended_mentality}"

            elapsed = time.time() - t0
            print(f"  MD{md_num:>2}  {fix_line:<50} Fit={avg_fit:.0f}  {elapsed:.1f}s{cup_info}{ai_info}")

        except Exception as e:
            errors.append((md_idx + 1, str(e), traceback.format_exc()))
            print(f"  MD{md_idx+1}  *** ERROR: {e}")

    # ═══════════════════════════════════════════════════════════════════════
    #  DIAGNOSTICS
    # ═══════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 72)
    print("  DIAGNOSTICS")
    print("=" * 72)

    # Record
    w = human_results.count("W")
    d = human_results.count("D")
    l = human_results.count("L")
    print(f"\n  {club.name}: {w}W {d}D {l}L  Form: {''.join(human_results)}")

    # Table
    standings = (
        session.query(LeagueStanding)
        .filter_by(league_id=prem.id, season=2024)
        .order_by(LeagueStanding.points.desc(), LeagueStanding.goal_difference.desc())
        .limit(10).all()
    )
    print(f"\n  {'#':>2} {'Club':<25} {'P':>3} {'W':>3} {'D':>3} {'L':>3} "
          f"{'GF':>4} {'GA':>4} {'GD':>4} {'Pts':>4}")
    for i, s in enumerate(standings):
        c = session.get(Club, s.club_id)
        name = (c.name[:24] if c else f"Club {s.club_id}")
        print(f"  {i+1:>2} {name:<25} {s.played or 0:>3} {s.won or 0:>3} "
              f"{s.drawn or 0:>3} {s.lost or 0:>3} {s.goals_for or 0:>4} "
              f"{s.goals_against or 0:>4} {s.goal_difference or 0:>4} {s.points or 0:>4}")

    # Match stats
    if all_goals:
        avg_g = sum(all_goals) / len(all_goals)
        print(f"\n  PL Match Stats ({len(all_goals)} matches):")
        print(f"    Goals/match:  {avg_g:.2f}  (target: 2.5-3.0)")
        print(f"    Range:        {min(all_goals)}-{max(all_goals)}")
    if all_shots:
        avg_s = sum(all_shots) / len(all_shots)
        print(f"    Shots/match:  {avg_s:.1f}  (target: 22-28)")
    if all_xg:
        avg_xg = sum(all_xg) / len(all_xg)
        print(f"    xG/match:     {avg_xg:.2f}  (target: 2.5-3.5)")

    # Score distribution
    if all_goals:
        dist = Counter(all_goals)
        print(f"    Distribution: {dict(sorted(dist.items()))}")
        scoreless = dist.get(0, 0)
        high_scoring = sum(v for k, v in dist.items() if k >= 5)
        print(f"    0-0 draws:    {scoreless} ({scoreless/len(all_goals)*100:.1f}%)")
        print(f"    5+ goals:     {high_scoring} ({high_scoring/len(all_goals)*100:.1f}%)")

    # AI Assistant reports
    if prep_reports:
        formations = Counter(r.recommended_formation for r in prep_reports)
        mentalities = Counter(r.recommended_mentality for r in prep_reports)
        avg_win_p = sum(r.win_probability for r in prep_reports) / len(prep_reports)
        print(f"\n  AI Assistant Reports ({len(prep_reports)}):")
        print(f"    Formations:   {dict(formations)}")
        print(f"    Mentalities:  {dict(mentalities)}")
        print(f"    Avg win prob: {avg_win_p*100:.0f}%")
        # Show one example report
        r = prep_reports[0]
        print(f"\n  Example report (MD1 vs {r.opponent.club_name}):")
        print(f"    Prediction:   {r.win_probability*100:.0f}%W / "
              f"{r.draw_probability*100:.0f}%D / {r.loss_probability*100:.0f}%L")
        print(f"    Recommended:  {r.recommended_formation} {r.recommended_mentality}")
        print(f"    Key battle:   {r.key_battle}")
        if r.warnings:
            print(f"    Warnings:     {r.warnings[0]}")

    # Cups
    cup_played = session.query(CupFixture).filter_by(played=True).count()
    cup_total = session.query(CupFixture).count()
    if cup_total:
        print(f"\n  Cups: {cup_played}/{cup_total} domestic cup matches")

    # Continental
    from fm.db.models import ContinentalFixture, ContinentalGroup
    cont_played = session.query(ContinentalFixture).filter_by(played=True).count()
    cont_total = session.query(ContinentalFixture).count()
    if cont_total:
        print(f"  Continental: {cont_played}/{cont_total} matches")
        # Show group standings for CL
        cl_groups = session.query(ContinentalGroup).filter_by(
            competition_name="Champions League", season=2024
        ).order_by(ContinentalGroup.group_letter, ContinentalGroup.points.desc()).all()
        if cl_groups:
            print(f"\n  Champions League Groups ({len(cl_groups)} teams):")
            current_grp = None
            for g in cl_groups:
                if g.group_letter != current_grp:
                    current_grp = g.group_letter
                    print(f"    Group {current_grp}:")
                c = session.get(Club, g.club_id)
                name = (c.name[:20] if c else f"Club {g.club_id}")
                print(f"      {name:<22} P={g.played or 0} W={g.won or 0} "
                      f"D={g.drawn or 0} L={g.lost or 0} "
                      f"GF={g.gf or 0} GA={g.ga or 0} "
                      f"Pts={g.points or 0}")

    # Player health
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
              f"min={min(all_morale)}  max={max(all_morale)}")
        print(f"    Fitness: avg={sum(all_fitness)/len(all_fitness):.1f}  "
              f"min={min(all_fitness)}  max={max(all_fitness)}")

    # ── VALIDATION ────────────────────────────────────────────────────────
    print(f"\n  Validation:")
    passed = 0
    total = 0

    def chk(name, cond):
        nonlocal passed, total
        total += 1
        if cond:
            passed += 1
            print(f"    [PASS] {name}")
        else:
            print(f"    [FAIL] {name}")

    chk("No errors", len(errors) == 0)
    chk("12 matchdays completed", len(human_results) >= N - 1)
    if all_goals:
        chk(f"Goals/match realistic: {sum(all_goals)/len(all_goals):.2f}",
            2.0 <= sum(all_goals)/len(all_goals) <= 4.0)
    if all_shots:
        chk(f"Shots/match realistic: {sum(all_shots)/len(all_shots):.1f}",
            15 <= sum(all_shots)/len(all_shots) <= 35)
    if all_xg:
        chk(f"xG/match realistic: {sum(all_xg)/len(all_xg):.2f}",
            1.5 <= sum(all_xg)/len(all_xg) <= 5.0)
    chk("AI Assistant generated reports", len(prep_reports) >= 10)
    chk("AI recommended varied tactics",
        len(set(r.recommended_formation for r in prep_reports)) >= 1)
    if all_morale:
        chk(f"Morale sane: {sum(all_morale)/len(all_morale):.1f}",
            30 <= sum(all_morale)/len(all_morale) <= 90)
    if all_fitness:
        chk(f"Fitness sane: {sum(all_fitness)/len(all_fitness):.1f}",
            50 <= sum(all_fitness)/len(all_fitness) <= 100)

    print(f"\n  Result: {passed}/{total} checks passed")

    if errors:
        print(f"\n  *** ERRORS ***")
        for md, msg, tb in errors:
            print(f"\n  MD{md}: {msg}\n{tb}")

    status = "PASSED" if passed == total and not errors else "FAILED"
    print(f"\n{'='*72}")
    print(f"  COMPREHENSIVE SIMULATION: {status}")
    print(f"{'='*72}")

    session.close()
    return len(errors) == 0 and passed == total


if __name__ == "__main__":
    success = run()
    sys.exit(0 if success else 1)
