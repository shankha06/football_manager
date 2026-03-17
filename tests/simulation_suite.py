"""Simulation suite to validate game realism and tune parameters.

Runs full-season simulations for:
1. Premier League (20 teams, 38 matchdays)
2. FA Cup (Knockout)
3. Champions Cup (UEFA-style Continental Competition)
"""
import sys
import os
import random
from pathlib import Path
from sqlalchemy.orm import Session

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from fm.db.database import get_session, init_db
from fm.db.ingestion import ingest_all
from fm.db.models import Club, League, Fixture, TacticalSetup, Player
from fm.world.season import SeasonManager
from fm.world.continental import ContinentalManager, ContinentalCup
from fm.engine.cuda_batch import BatchMatchSimulator, BatchFixtureInput
from fm.engine.match_state import PlayerInMatch
from fm.engine.tactics import TacticalContext
from fm.engine.match_context import build_match_context

def _avg_attr(players: list, attr: str) -> float:
    if not players: return 50.0
    return sum(getattr(p, attr, 50) for p in players) / len(players)

def _avg_gk(players: list) -> float:
    gks = [p for p in players if p.position == "GK"]
    if not gks: return 10.0
    gk = gks[0]
    return (gk.gk_diving + gk.gk_handling + gk.gk_kicking + gk.gk_positioning + gk.gk_reflexes) / 5.0

def _select_squad(players_db: list, side: str) -> tuple[list[PlayerInMatch], list[PlayerInMatch]]:
    available = [p for p in players_db if (p.injured_weeks or 0) == 0 and (p.suspended_matches or 0) == 0]
    available.sort(key=lambda p: p.overall or 0, reverse=True)
    gks = [p for p in available if p.position == "GK"]
    outfield = [p for p in available if p.position != "GK"]
    xi = []
    if gks:
        xi.append(PlayerInMatch.from_db_player(gks[0], side))
        gks = gks[1:]
    if outfield:
        for p in outfield[:10]:
            xi.append(PlayerInMatch.from_db_player(p, side))
    remaining = gks + outfield[10:]
    subs = [PlayerInMatch.from_db_player(p, side) for p in remaining[:7]]
    for s in subs: s.is_on_pitch = False
    return xi, subs

def run_simulation():
    db_path = "simulation_test.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    
    print("--- Ingesting Data ---")
    stats = ingest_all(db_path=db_path, download=False)
    print(f"Ingested: {stats}")
    
    session = get_session()
    
    print("\n--- Running League Simulation (Matchday 1-2) ---")
    manager = SeasonManager(session)
    for md in range(1, 3):
        print(f"Matchday {md}...")
        results = manager.advance_matchday()
        print(f"Simulated {results['matches']} matches")
    
    print("\n--- Running UEFA-style Continental Cup Simulation ---")
    cont_manager = ContinentalManager(session)
    cup = cont_manager.initialize_season(2024)
    print(f"Initialized {cup.name} with {len(cup.teams)} teams")
    
    fixtures = cup.generate_group_fixtures()
    print(f"Generated {len(fixtures)} group stage fixtures")
    
    batch_sim = BatchMatchSimulator()
    batch_inputs = []
    
    # We only take a subset for quick validation
    test_fixtures = fixtures[:20]
    
    for home_club, away_club, _ in test_fixtures:
        h_players = session.query(Player).filter_by(club_id=home_club.id).all()
        a_players = session.query(Player).filter_by(club_id=away_club.id).all()
        
        h_xi, _ = _select_squad(h_players, "home")
        a_xi, _ = _select_squad(a_players, "away")
        
        h_tac_db = session.query(TacticalSetup).filter_by(club_id=home_club.id).first()
        a_tac_db = session.query(TacticalSetup).filter_by(club_id=away_club.id).first()
        
        h_tac = TacticalContext.from_db(h_tac_db) if h_tac_db else TacticalContext()
        a_tac = TacticalContext.from_db(a_tac_db) if a_tac_db else TacticalContext()
        
        # Build context for realism factors
        ctx = build_match_context(session, home_club, away_club, home_tactics=h_tac, away_tactics=a_tac)
        
        bi = BatchFixtureInput(
            fixture_id=random.randint(1000, 9999), # Dummy ID
            home_attack=_avg_attr(h_xi, "shooting"),
            home_midfield=_avg_attr(h_xi, "passing"),
            home_defense=_avg_attr(h_xi, "defending"),
            home_gk=_avg_gk(h_xi),
            away_attack=_avg_attr(a_xi, "shooting"),
            away_midfield=_avg_attr(a_xi, "passing"),
            away_defense=_avg_attr(a_xi, "defending"),
            away_gk=_avg_gk(a_xi),
            home_mentality=h_tac.risk_modifier,
            away_mentality=a_tac.risk_modifier,
            home_advantage=ctx.home_advantage,
            home_morale_mod=ctx.home_morale_mod,
            away_morale_mod=ctx.away_morale_mod,
            home_form_mod=ctx.home_form_mod,
            away_form_mod=ctx.away_form_mod,
            home_fitness=ctx.fatigue_home,
            away_fitness=ctx.fatigue_away,
            tactical_adv_home=ctx.tactical_advantage_home,
            tactical_adv_away=ctx.tactical_advantage_away,
        )
        batch_inputs.append(bi)
    
    results = batch_sim.simulate_batch(batch_inputs)
    
    print("\n--- UEFA Group Stage Sample Results ---")
    for bi, res in zip(batch_inputs, results):
        # We need club names for display
        print(f"Match {bi.fixture_id}: {res.home_goals} - {res.away_goals} (xG: {res.home_xg:.2f} - {res.away_xg:.2f})")

    # Analyze Stats
    print("\n--- Realism Metrics (Batch) ---")
    avg_goals = sum(r.home_goals + r.away_goals for r in results) / len(results)
    avg_xg = sum(r.home_xg + r.away_xg for r in results) / len(results)
    print(f"Avg Goals/Game: {avg_goals:.2f}")
    print(f"Avg xG/Game: {avg_xg:.2f}")
    
    session.close()

if __name__ == "__main__":
    run_simulation()
