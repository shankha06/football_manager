"""Domestic knockout cup competition system.

Single-elimination cups (FA Cup, Copa del Rey, DFB-Pokal, etc.)
with seeding, extra time, and penalty shootouts.
"""
from __future__ import annotations

import math
import random
from typing import Optional

from sqlalchemy.orm import Session

from fm.db.models import Club, League, CupFixture, Player, NewsItem
from fm.engine.cuda_batch import BatchMatchSimulator, BatchFixtureInput
from fm.engine.simulator import MatchSimulator
from fm.engine.match_engine import AdvancedMatchEngine
from fm.engine.match_state import PlayerInMatch, MatchResult
from fm.engine.match_context import build_match_context
from fm.engine.tactics import TacticalContext
from fm.config import USE_ADVANCED_ENGINE


# Round-name lookup keyed by number of remaining teams.
_ROUND_NAMES = {
    2: "Final",
    4: "Semi-Final",
    8: "Quarter-Final",
    16: "Round of 16",
    32: "Round of 32",
    64: "Round of 64",
    128: "Round of 128",
}


class DomesticCup:
    """Single-elimination knockout cup (like FA Cup / Copa del Rey)."""

    def __init__(self, session: Session, cup_name: str, country: str):
        self.session = session
        self.cup_name = cup_name
        self.country = country
        self.match_sim = AdvancedMatchEngine() if USE_ADVANCED_ENGINE else MatchSimulator()
        self.batch_sim = BatchMatchSimulator()

    # ── Draw generation ───────────────────────────────────────────────────

    def generate_draw(self, season: int) -> list[CupFixture]:
        """Create the cup draw from all clubs in the country's leagues.

        Seeds top-tier clubs to enter in later rounds by placing lower-tier
        clubs in the first round(s) and introducing top-tier clubs from round 2.
        """
        # Gather all clubs from this country's leagues
        leagues = (
            self.session.query(League)
            .filter_by(country=self.country)
            .order_by(League.tier)
            .all()
        )
        if not leagues:
            return []

        top_tier_clubs: list[Club] = []
        lower_tier_clubs: list[Club] = []

        for league in leagues:
            clubs = self.session.query(Club).filter_by(league_id=league.id).all()
            if league.tier == 1:
                top_tier_clubs.extend(clubs)
            else:
                lower_tier_clubs.extend(clubs)

        # Shuffle for randomised draw
        random.shuffle(top_tier_clubs)
        random.shuffle(lower_tier_clubs)

        all_clubs = lower_tier_clubs + top_tier_clubs
        # Trim to nearest power-of-two
        max_teams = 2 ** int(math.floor(math.log2(len(all_clubs)))) if all_clubs else 0
        if max_teams < 2:
            return []
        all_clubs = all_clubs[:max_teams]

        # Figure out which round top-tier clubs enter
        total_rounds = int(math.log2(max_teams))
        # Top-tier clubs enter from round 2 if there are enough lower-tier teams
        # to fill round 1 on their own; otherwise everyone starts in round 1.
        if len(lower_tier_clubs) >= max_teams // 2:
            top_tier_entry_round = 2
            # Round 1: lower-tier only
            r1_clubs = lower_tier_clubs[: max_teams // 2 * 2]
            random.shuffle(r1_clubs)
            # Trim to power-of-two pairs
            r1_count = 2 ** int(math.floor(math.log2(len(r1_clubs)))) if r1_clubs else 0
            r1_clubs = r1_clubs[:r1_count]
        else:
            top_tier_entry_round = 1
            r1_clubs = all_clubs
            random.shuffle(r1_clubs)

        # Create round-1 fixtures
        fixtures: list[CupFixture] = []
        for i in range(0, len(r1_clubs) - 1, 2):
            cf = CupFixture(
                cup_name=self.cup_name,
                season=season,
                round_number=1,
                home_club_id=r1_clubs[i].id,
                away_club_id=r1_clubs[i + 1].id,
            )
            self.session.add(cf)
            fixtures.append(cf)

        self.session.flush()

        # Store top-tier clubs as byes into round 2 (they'll be paired with
        # round-1 winners when simulate_round is called for round 2).
        # We don't create their fixtures yet; they are generated dynamically.
        self._top_tier_waiting = top_tier_clubs if top_tier_entry_round == 2 else []

        self.session.add(NewsItem(
            season=season,
            headline=f"{self.cup_name} draw announced!",
            body=f"The {self.cup_name} draw has been made with {max_teams} clubs.",
            category="cup",
        ))
        self.session.commit()
        return fixtures

    # ── Round simulation ──────────────────────────────────────────────────

    def simulate_round(self, human_club_id: int | None = None) -> dict:
        """Simulate one round of the cup. Human match uses full sim.

        Returns a dict with round info and results.
        """
        # Find the earliest unplayed round
        unplayed = (
            self.session.query(CupFixture)
            .filter_by(cup_name=self.cup_name, played=False)
            .order_by(CupFixture.round_number)
            .first()
        )
        if not unplayed:
            return {"round": None, "results": [], "complete": True}

        current_round = unplayed.round_number

        fixtures = (
            self.session.query(CupFixture)
            .filter_by(cup_name=self.cup_name, round_number=current_round, played=False)
            .all()
        )

        human_fixture: Optional[CupFixture] = None
        batch_fixtures: list[CupFixture] = []
        results: list[dict] = []

        for f in fixtures:
            if human_club_id and (
                f.home_club_id == human_club_id or f.away_club_id == human_club_id
            ):
                human_fixture = f
            else:
                batch_fixtures.append(f)

        # Batch-simulate AI matches
        if batch_fixtures:
            batch_inputs = []
            from fm.db.models import TacticalSetup, Season
            season = self.session.query(Season).order_by(Season.year.desc()).first()
            for f in batch_fixtures:
                home_club = self.session.query(Club).get(f.home_club_id)
                away_club = self.session.query(Club).get(f.away_club_id)

                h_players_db = self.session.query(Player).filter_by(club_id=f.home_club_id).all()
                a_players_db = self.session.query(Player).filter_by(club_id=f.away_club_id).all()

                h_xi, _ = _select_squad(h_players_db, "home")
                a_xi, _ = _select_squad(a_players_db, "away")

                h_tac_db = self.session.query(TacticalSetup).filter_by(club_id=f.home_club_id).first()
                a_tac_db = self.session.query(TacticalSetup).filter_by(club_id=f.away_club_id).first()

                h_tac = TacticalContext.from_db(h_tac_db) if h_tac_db else TacticalContext()
                a_tac = TacticalContext.from_db(a_tac_db) if a_tac_db else TacticalContext()

                ctx = build_match_context(
                    self.session, home_club, away_club,
                    home_tactics=h_tac, away_tactics=a_tac,
                    season=season,
                )

                bi = BatchFixtureInput(
                    fixture_id=f.id,
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

            batch_results = self.batch_sim.simulate_batch(batch_inputs)

            for br in batch_results:
                fix = next(f for f in batch_fixtures if f.id == br.fixture_id)
                fix.home_goals = br.home_goals
                fix.away_goals = br.away_goals
                fix.played = True

                # Handle draws — extra time then penalties
                if fix.home_goals == fix.away_goals:
                    self._resolve_draw(fix)
                else:
                    fix.winner_club_id = (
                        fix.home_club_id if fix.home_goals > fix.away_goals
                        else fix.away_club_id
                    )

                home_club = self.session.query(Club).get(fix.home_club_id)
                away_club = self.session.query(Club).get(fix.away_club_id)
                results.append({
                    "fixture_id": fix.id,
                    "home": home_club.name if home_club else "?",
                    "away": away_club.name if away_club else "?",
                    "home_goals": fix.home_goals,
                    "away_goals": fix.away_goals,
                    "extra_time": fix.extra_time,
                    "penalties": fix.penalties,
                    "winner_id": fix.winner_club_id,
                })

        # Full sim for human match
        human_result = None
        if human_fixture:
            human_result = self._simulate_full_cup_match(human_fixture)
            home_club = self.session.query(Club).get(human_fixture.home_club_id)
            away_club = self.session.query(Club).get(human_fixture.away_club_id)
            results.append({
                "fixture_id": human_fixture.id,
                "home": home_club.name if home_club else "?",
                "away": away_club.name if away_club else "?",
                "home_goals": human_fixture.home_goals,
                "away_goals": human_fixture.away_goals,
                "extra_time": human_fixture.extra_time,
                "penalties": human_fixture.penalties,
                "winner_id": human_fixture.winner_club_id,
            })

        # Generate next round fixtures from winners
        self._generate_next_round(current_round)

        self.session.commit()

        remaining_teams = len([
            f for f in self.session.query(CupFixture).filter_by(
                cup_name=self.cup_name, round_number=current_round
            ).all()
        ])

        return {
            "round": current_round,
            "round_name": self.get_current_round_name(),
            "results": results,
            "human_result": human_result,
            "complete": False,
        }

    def _resolve_draw(self, fixture: CupFixture):
        """Resolve a drawn cup match with extra time and penalties."""
        # Extra time: add 0-2 goals for each side
        et_home = random.choice([0, 0, 0, 1, 1, 2])
        et_away = random.choice([0, 0, 0, 1, 1, 2])
        fixture.home_goals += et_home
        fixture.away_goals += et_away
        fixture.extra_time = True

        if fixture.home_goals == fixture.away_goals:
            # Penalty shootout
            fixture.penalties = True
            h_pens, a_pens = _simulate_penalty_shootout()
            fixture.penalty_home = h_pens
            fixture.penalty_away = a_pens
            fixture.winner_club_id = (
                fixture.home_club_id if h_pens > a_pens
                else fixture.away_club_id
            )
        else:
            fixture.winner_club_id = (
                fixture.home_club_id if fixture.home_goals > fixture.away_goals
                else fixture.away_club_id
            )

    def _simulate_full_cup_match(self, fixture: CupFixture) -> MatchResult:
        """Fully simulate a cup match with detailed events."""
        from fm.db.models import TacticalSetup, Season

        home_club = self.session.query(Club).get(fixture.home_club_id)
        away_club = self.session.query(Club).get(fixture.away_club_id)

        h_players_db = self.session.query(Player).filter_by(
            club_id=fixture.home_club_id
        ).all()
        a_players_db = self.session.query(Player).filter_by(
            club_id=fixture.away_club_id
        ).all()

        h_xi, h_subs = _select_squad(h_players_db, "home")
        a_xi, a_subs = _select_squad(a_players_db, "away")

        h_tac_db = self.session.query(TacticalSetup).filter_by(
            club_id=fixture.home_club_id
        ).first()
        a_tac_db = self.session.query(TacticalSetup).filter_by(
            club_id=fixture.away_club_id
        ).first()

        h_tac = TacticalContext.from_db(h_tac_db) if h_tac_db else TacticalContext()
        a_tac = TacticalContext.from_db(a_tac_db) if a_tac_db else TacticalContext()

        # Build match context with all pre-match factors
        season = self.session.query(Season).order_by(Season.year.desc()).first()
        match_context = build_match_context(
            self.session, home_club, away_club,
            home_tactics=h_tac, away_tactics=a_tac,
            season=season,
        )

        result = self.match_sim.simulate(
            h_xi, a_xi, h_tac, a_tac,
            home_name=home_club.name if home_club else "Home",
            away_name=away_club.name if away_club else "Away",
            home_subs=h_subs, away_subs=a_subs,
            match_context=match_context,
        )

        fixture.home_goals = result.home_goals
        fixture.away_goals = result.away_goals
        fixture.played = True

        if fixture.home_goals == fixture.away_goals:
            self._resolve_draw(fixture)
        else:
            fixture.winner_club_id = (
                fixture.home_club_id if fixture.home_goals > fixture.away_goals
                else fixture.away_club_id
            )

        return result

    def _generate_next_round(self, completed_round: int):
        """Create fixtures for the next round from winners of the completed round."""
        winners_fixtures = (
            self.session.query(CupFixture)
            .filter_by(
                cup_name=self.cup_name,
                round_number=completed_round,
                played=True,
            )
            .all()
        )

        winner_ids = [f.winner_club_id for f in winners_fixtures if f.winner_club_id]

        if len(winner_ids) < 2:
            return  # Cup complete or not enough winners

        random.shuffle(winner_ids)
        next_round = completed_round + 1

        for i in range(0, len(winner_ids) - 1, 2):
            cf = CupFixture(
                cup_name=self.cup_name,
                season=winners_fixtures[0].season,
                round_number=next_round,
                home_club_id=winner_ids[i],
                away_club_id=winner_ids[i + 1],
            )
            self.session.add(cf)

        self.session.flush()

    # ── Round naming ──────────────────────────────────────────────────────

    def get_current_round_name(self) -> str:
        """Return 'Round of 64', 'Quarter-Final', 'Semi-Final', 'Final' etc."""
        unplayed = (
            self.session.query(CupFixture)
            .filter_by(cup_name=self.cup_name, played=False)
            .order_by(CupFixture.round_number)
            .first()
        )
        if not unplayed:
            # Check if there's a completed final
            last = (
                self.session.query(CupFixture)
                .filter_by(cup_name=self.cup_name)
                .order_by(CupFixture.round_number.desc())
                .first()
            )
            if last and last.played:
                return "Complete"
            return "Not Started"

        # Count fixtures in this round to determine the round name
        count = (
            self.session.query(CupFixture)
            .filter_by(
                cup_name=self.cup_name,
                round_number=unplayed.round_number,
            )
            .count()
        )
        total_teams = count * 2
        return _ROUND_NAMES.get(total_teams, f"Round of {total_teams}")


# ── Helper functions ──────────────────────────────────────────────────────

def _avg_attr(players: list, attr: str) -> float:
    if not players:
        return 50.0
    vals = [getattr(p, attr, 50) or 50 for p in players]
    return sum(vals) / len(vals)


def _avg_gk(players: list) -> float:
    gks = [p for p in players if p.position == "GK"]
    if not gks:
        return 50.0
    return max(
        (p.gk_reflexes + p.gk_diving + p.gk_positioning) / 3.0
        for p in gks
    )


def _select_squad(
    players_db: list, side: str
) -> tuple[list[PlayerInMatch], list[PlayerInMatch]]:
    """Select best XI and up to 7 subs from a squad."""
    available = [
        p for p in players_db
        if (p.injured_weeks or 0) == 0 and (p.suspended_matches or 0) == 0
    ]
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
    for s in subs:
        s.is_on_pitch = False

    return xi, subs


def _simulate_penalty_shootout() -> tuple[int, int]:
    """Simulate a penalty shootout. Returns (home_score, away_score)."""
    home_score = 0
    away_score = 0

    # Standard 5 penalties each
    for i in range(5):
        if random.random() < 0.75:  # ~75% conversion rate
            home_score += 1
        if random.random() < 0.75:
            away_score += 1

    # Sudden death if tied
    while home_score == away_score:
        h_scored = random.random() < 0.70
        a_scored = random.random() < 0.70
        if h_scored:
            home_score += 1
        if a_scored:
            away_score += 1

    return home_score, away_score
