#!/usr/bin/env python3
"""Full integration test: simulates a season with all systems active.

Creates a fresh DB, picks a Premier League club, and advances 8+ matchdays
checking that all engines (match, tactics, morale, training, finance,
transfers, scouting, weather, form, fitness, injuries, AI adaptation)
produce realistic results in cohesion.
"""
from __future__ import annotations

import os
import sys
import random
import time
from pathlib import Path
from collections import Counter

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# --- Config override: use a temp DB ---
TEST_DB = Path(__file__).resolve().parent.parent / "saves" / "integration_test.db"


def setup_database():
    """Create a fresh DB with full ingestion."""
    if TEST_DB.exists():
        TEST_DB.unlink()

    # Reset singleton engine to point to test DB
    from fm.db import database as db_mod
    db_mod.close_engine()
    db_mod._engine = None
    db_mod._SessionFactory = None

    engine = db_mod.get_engine(str(TEST_DB))
    from fm.db.models import Base
    Base.metadata.create_all(engine)

    # Run full ingestion (it calls init_db + get_session internally)
    from fm.db.ingestion import ingest_all
    print("Ingesting data (players, clubs, leagues, staff, contracts, boards)...")
    t0 = time.time()
    stats = ingest_all(db_path=str(TEST_DB))
    print(f"  Done in {time.time()-t0:.1f}s")
    print(f"  Stats: {stats}")

    session = db_mod.get_session()
    return session


def setup_season(session, human_club_id: int):
    """Get existing Season (created by ingestion) and return SeasonManager."""
    from fm.db.models import Season
    from fm.world.season import SeasonManager

    mgr = SeasonManager(session)

    # Season + fixtures + standings already created by ingest_all
    season = session.query(Season).filter_by(year=2024).first()
    if not season:
        raise RuntimeError("No season found — ingestion should have created it")

    session.commit()
    return mgr, season


def print_league_table(session, league_id: int, season_year: int, top_n: int = 20):
    """Print current league standings."""
    from fm.db.models import LeagueStanding, Club, League
    league = session.get(League, league_id)
    standings = (
        session.query(LeagueStanding)
        .filter_by(league_id=league_id, season=season_year)
        .order_by(LeagueStanding.points.desc(), LeagueStanding.goal_difference.desc())
        .limit(top_n)
        .all()
    )
    print(f"\n{'='*65}")
    print(f"  {league.name} - Matchday {standings[0].played if standings else '?'}")
    print(f"{'='*65}")
    print(f"  {'#':>2} {'Club':<25} {'P':>3} {'W':>3} {'D':>3} {'L':>3} {'GF':>4} {'GA':>4} {'GD':>4} {'Pts':>4} {'Form':>6}")
    print(f"  {'-'*60}")
    for i, s in enumerate(standings):
        club = session.get(Club, s.club_id)
        name = club.name[:24] if club else f"Club {s.club_id}"
        form = (s.form or "")[-5:]
        print(f"  {i+1:>2} {name:<25} {s.played or 0:>3} {s.won or 0:>3} "
              f"{s.drawn or 0:>3} {s.lost or 0:>3} {s.goals_for or 0:>4} "
              f"{s.goals_against or 0:>4} {s.goal_difference or 0:>4} "
              f"{s.points or 0:>4} {form:>6}")


def print_fixture_details(session, fixture, human_club_id: int):
    """Print detailed fixture info including tactical matchup."""
    from fm.db.models import Club
    home = session.get(Club, fixture.home_club_id)
    away = session.get(Club, fixture.away_club_id)

    is_human = (fixture.home_club_id == human_club_id or
                fixture.away_club_id == human_club_id)
    marker = " *** YOUR MATCH ***" if is_human else ""

    hg = fixture.home_goals or 0
    ag = fixture.away_goals or 0
    print(f"  {home.name} {hg}-{ag} {away.name}{marker}")

    # Print tactical info if available
    if fixture.home_formation:
        h_tac = f"{fixture.home_formation} {fixture.home_mentality or ''} {fixture.home_pressing or ''}"
        a_tac = f"{fixture.away_formation} {fixture.away_mentality or ''} {fixture.away_pressing or ''}"
        print(f"    Tactics: {home.name[:15]}={h_tac}  {away.name[:15]}={a_tac}")

    if fixture.home_xg is not None:
        poss = fixture.home_possession or 50
        print(f"    Poss: {poss:.0f}%-{100-poss:.0f}%  "
              f"Shots: {fixture.home_shots or 0}-{fixture.away_shots or 0}  "
              f"xG: {fixture.home_xg or 0:.1f}-{fixture.away_xg or 0:.1f}")


def print_squad_status(session, club_id: int, club_name: str):
    """Print key squad metrics: fitness, morale, injuries."""
    from fm.db.models import Player
    players = session.query(Player).filter_by(club_id=club_id).all()
    if not players:
        return

    avg_fitness = sum(p.fitness or 100 for p in players) / len(players)
    avg_morale = sum(p.morale or 65 for p in players) / len(players)
    avg_form = sum(p.form or 65 for p in players) / len(players)
    injured = [p for p in players if (p.injured_weeks or 0) > 0]

    print(f"\n  Squad Status ({club_name}):")
    print(f"    Avg Fitness: {avg_fitness:.1f}  Avg Morale: {avg_morale:.1f}  "
          f"Avg Form: {avg_form:.1f}  Injured: {len(injured)}")
    if injured:
        for p in injured[:5]:
            print(f"      {p.name} ({p.position}) - {p.injured_weeks}w remaining")


def print_finance_status(session, club_id: int, club_name: str):
    """Print club financial status."""
    from fm.db.models import Club
    club = session.get(Club, club_id)
    if not club:
        return
    print(f"    Budget: €{(club.budget or 0):.1f}M  "
          f"Wage bill: €{(club.total_wages or 0):.0f}K/w")


def print_tactical_analysis(session, club_id: int, club_name: str):
    """Print what tactics the club has been using."""
    from fm.db.models import Fixture
    fixtures = (
        session.query(Fixture)
        .filter(
            Fixture.played == True,
            (Fixture.home_club_id == club_id) | (Fixture.away_club_id == club_id)
        )
        .order_by(Fixture.matchday.desc())
        .limit(6)
        .all()
    )
    if not fixtures:
        return

    formations = []
    mentalities = []
    for f in fixtures:
        if f.home_club_id == club_id:
            if f.home_formation:
                formations.append(f.home_formation)
            if f.home_mentality:
                mentalities.append(f.home_mentality)
        else:
            if f.away_formation:
                formations.append(f.away_formation)
            if f.away_mentality:
                mentalities.append(f.away_mentality)

    if formations:
        fm_counter = Counter(formations)
        ment_counter = Counter(mentalities)
        print(f"    Recent tactics: {dict(fm_counter)}  Mentality: {dict(ment_counter)}")


def run_integration_test():
    """Main test: set up, simulate 8 matchdays, verify all systems."""
    random.seed(42)  # Reproducible

    print("=" * 70)
    print("  FULL INTEGRATION TEST - Football Manager")
    print("  All systems: match engine, tactics, morale, training,")
    print("  finance, transfers, weather, form, fitness, injuries,")
    print("  AI adaptation, scouting, news generation")
    print("=" * 70)

    # ── 1. Setup ──
    session = setup_database()

    # Pick a Premier League club to control
    from fm.db.models import Club, League, Player, Manager, Fixture, TacticalSetup
    prem = session.query(League).filter_by(name="Premier League").first()
    if not prem:
        print("ERROR: Premier League not found!")
        return

    # Pick Arsenal as the human team
    human_club = session.query(Club).filter_by(league_id=prem.id).filter(
        Club.name.like("%Arsenal%")
    ).first()
    if not human_club:
        # Fallback: pick the highest-rep PL club
        human_club = (
            session.query(Club)
            .filter_by(league_id=prem.id)
            .order_by(Club.reputation.desc())
            .first()
        )

    print(f"\nControlling: {human_club.name} (rep: {human_club.reputation})")
    human_id = human_club.id

    # Show squad overview
    squad = session.query(Player).filter_by(club_id=human_id).all()
    print(f"  Squad size: {len(squad)}")
    top5 = sorted(squad, key=lambda p: p.overall or 0, reverse=True)[:5]
    for p in top5:
        print(f"    {p.name} ({p.position}) - OVR: {p.overall}")

    # Set up human tactics (attacking possession style)
    human_setup = session.query(TacticalSetup).filter_by(club_id=human_id).first()
    if not human_setup:
        human_setup = TacticalSetup(club_id=human_id)
        session.add(human_setup)
    human_setup.formation = "4-3-3"
    human_setup.mentality = "positive"
    human_setup.pressing = "high"
    human_setup.tempo = "fast"
    human_setup.passing_style = "short"
    human_setup.width = "wide"
    human_setup.defensive_line = "high"
    human_setup.counter_attack = False
    human_setup.play_out_from_back = True
    human_setup.match_plan_winning = "hold_lead"
    human_setup.match_plan_losing = "push_forward"
    human_setup.match_plan_drawing = "push_forward"
    session.commit()

    # ── 2. Setup season ──
    season_mgr, season = setup_season(session, human_id)

    # Count fixtures
    total_fixtures = session.query(Fixture).filter_by(season=2024).count()
    prem_fixtures = session.query(Fixture).filter_by(
        season=2024, league_id=prem.id
    ).count()
    print(f"\n  Total fixtures generated: {total_fixtures}")
    print(f"  Premier League fixtures: {prem_fixtures}")

    # Collect diagnostics across matchdays
    all_goals = []
    all_shots = []
    all_poss = []
    human_results = []

    # ── 3. Simulate matchdays ──
    N_MATCHDAYS = 8
    print(f"\nSimulating {N_MATCHDAYS} matchdays with all systems active...")
    print("-" * 70)

    for md in range(N_MATCHDAYS):
        t0 = time.time()
        result = season_mgr.advance_matchday(human_club_id=human_id)
        elapsed = time.time() - t0

        md_num = result.get("matchday", md + 1)
        n_matches = result.get("matches", 0)
        human_result = result.get("human_result")
        human_fix = result.get("human_fixture")

        print(f"\n{'='*70}")
        print(f"  MATCHDAY {md_num}  ({n_matches} matches, {elapsed:.1f}s)")
        print(f"{'='*70}")

        # Get all fixtures for this matchday
        md_fixtures = session.query(Fixture).filter_by(
            season=2024, matchday=md_num, played=True
        ).all()

        # Print all PL results
        prem_fixtures_md = [f for f in md_fixtures if f.league_id == prem.id]
        print(f"\n  Premier League Results:")
        for f in prem_fixtures_md:
            print_fixture_details(session, f, human_id)

            hg = f.home_goals or 0
            ag = f.away_goals or 0
            all_goals.append(hg + ag)
            if f.home_shots:
                all_shots.append((f.home_shots or 0) + (f.away_shots or 0))
            if f.home_possession:
                all_poss.append(f.home_possession)

        # Track human results
        if human_fix:
            hg = human_fix.home_goals or 0
            ag = human_fix.away_goals or 0
            is_home = human_fix.home_club_id == human_id
            our_g = hg if is_home else ag
            their_g = ag if is_home else hg
            if our_g > their_g:
                human_results.append("W")
            elif our_g < their_g:
                human_results.append("L")
            else:
                human_results.append("D")

        # Print squad status for human team
        print_squad_status(session, human_id, human_club.name)
        print_finance_status(session, human_id, human_club.name)
        print_tactical_analysis(session, human_id, human_club.name)

        # Print other league results (just counts)
        other_fixtures = [f for f in md_fixtures if f.league_id != prem.id]
        if other_fixtures:
            leagues_played = Counter(f.league_id for f in other_fixtures)
            league_names = {}
            from fm.db.models import League as L
            for lid in leagues_played:
                lg = session.get(L, lid)
                if lg:
                    league_names[lid] = lg.name
            other_summary = ", ".join(
                f"{league_names.get(lid, f'L{lid}')}: {cnt} matches"
                for lid, cnt in leagues_played.items()
            )
            print(f"\n  Other leagues: {other_summary}")

        # Print cup results if any
        cup_results = result.get("cup_results", [])
        if cup_results:
            print(f"\n  --- Cup Matches ---")
            for cr in cup_results:
                cup_name = cr.get("cup_name", "Cup")
                rd = cr.get("round", "?")
                results_list = cr.get("results", [])
                print(f"  {cup_name} ({rd}): {len(results_list)} matches")
                for r in results_list[:5]:  # show up to 5 per cup
                    et = " (aet)" if r.get("extra_time") else ""
                    pens = f" [{r.get('penalty_home',0)}-{r.get('penalty_away',0)} pens]" if r.get("penalties") else ""
                    print(f"    {r['home']} {r['home_goals']}-{r['away_goals']} {r['away']}{et}{pens}")
                if len(results_list) > 5:
                    print(f"    ... and {len(results_list) - 5} more")

        session.commit()

    # ── 4. Final diagnostics ──
    print("\n" + "=" * 70)
    print("  FINAL DIAGNOSTICS")
    print("=" * 70)

    # League table
    print_league_table(session, prem.id, 2024)

    # Human team summary
    print(f"\n  Your results ({human_club.name}): {''.join(human_results)}")
    print(f"  Record: {human_results.count('W')}W "
          f"{human_results.count('D')}D {human_results.count('L')}L")

    # Match statistics
    if all_goals:
        print(f"\n  Match Statistics (PL, {len(all_goals)} matches):")
        print(f"    Avg goals/match:  {sum(all_goals)/len(all_goals):.2f}")
        print(f"    Goals range:      {min(all_goals)}-{max(all_goals)}")
        goals_dist = Counter(all_goals)
        print(f"    Distribution:     {dict(sorted(goals_dist.items()))}")
    if all_shots:
        print(f"    Avg shots/match:  {sum(all_shots)/len(all_shots):.1f}")
    if all_poss:
        print(f"    Avg possession:   {sum(all_poss)/len(all_poss):.1f}%")

    # Check tactical diversity (AI should be adapting)
    print(f"\n  Tactical Diversity Check:")
    all_formations = []
    all_mentalities = []
    prem_played = session.query(Fixture).filter(
        Fixture.league_id == prem.id,
        Fixture.played == True,
        Fixture.season == 2024,
    ).all()
    for f in prem_played:
        if f.home_formation:
            all_formations.append(f.home_formation)
        if f.away_formation:
            all_formations.append(f.away_formation)
        if f.home_mentality:
            all_mentalities.append(f.home_mentality)
        if f.away_mentality:
            all_mentalities.append(f.away_mentality)

    if all_formations:
        fm_dist = Counter(all_formations)
        print(f"    Formations used: {dict(fm_dist.most_common(8))}")
    if all_mentalities:
        ment_dist = Counter(all_mentalities)
        print(f"    Mentalities:     {dict(ment_dist.most_common(7))}")

    # Check morale spread
    from fm.db.models import Player as P
    prem_clubs = session.query(Club).filter_by(league_id=prem.id).all()
    all_morale = []
    all_fitness = []
    for c in prem_clubs:
        players = session.query(P).filter_by(club_id=c.id).all()
        for p in players:
            all_morale.append(p.morale or 65)
            all_fitness.append(p.fitness or 100)

    print(f"\n  Player Health (PL, {len(all_morale)} players):")
    print(f"    Morale:  avg={sum(all_morale)/len(all_morale):.1f}  "
          f"min={min(all_morale):.0f}  max={max(all_morale):.0f}")
    print(f"    Fitness: avg={sum(all_fitness)/len(all_fitness):.1f}  "
          f"min={min(all_fitness):.0f}  max={max(all_fitness):.0f}")

    # Check injuries
    injured = session.query(P).filter(
        P.injured_weeks > 0, P.club_id.in_([c.id for c in prem_clubs])
    ).count()
    print(f"    Injured players: {injured}")

    # Weather variety
    weathers = [f.weather for f in prem_played if f.weather]
    if weathers:
        print(f"\n  Weather variety: {dict(Counter(weathers))}")

    # Cup progress
    from fm.db.models import CupFixture
    cup_played = session.query(CupFixture).filter_by(played=True).count()
    cup_total = session.query(CupFixture).count()
    cup_names = [r[0] for r in session.query(CupFixture.cup_name).distinct().all()]
    if cup_names:
        print(f"\n  Cup Competitions:")
        for cn in cup_names:
            played = session.query(CupFixture).filter_by(cup_name=cn, played=True).count()
            total = session.query(CupFixture).filter_by(cup_name=cn).count()
            print(f"    {cn}: {played}/{total} matches played")

    # News generated
    from fm.db.models import NewsItem
    news_count = session.query(NewsItem).count()
    print(f"  News items generated: {news_count}")

    # Check finances changed
    for c in prem_clubs[:3]:
        print(f"    {c.name}: budget €{(c.budget or 0):.1f}M")

    print("\n" + "=" * 70)
    print("  INTEGRATION TEST COMPLETE")
    print("=" * 70)

    session.close()


if __name__ == "__main__":
    run_integration_test()
