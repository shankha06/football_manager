"""Season progression, calendar management, and game loop driver.

Drives the core game loop: advance matchdays, process weekly activities,
handle transfer windows, suspensions, awards, and end-of-season events.
"""
from __future__ import annotations

import random
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import func

from fm.db.models import (
    League, Club, Fixture, LeagueStanding, Season, NewsItem,
    SeasonPhase, Player, PlayerStats, Transfer, Manager,
)
from fm.config import STARTING_SEASON, USE_ADVANCED_ENGINE, USE_V3_ENGINE
from fm.engine.cuda_batch import BatchMatchSimulator, BatchFixtureInput
from fm.engine.simulator import MatchSimulator
from fm.engine.match_engine import AdvancedMatchEngine
from fm.engine.match_state import PlayerInMatch, MatchResult
from fm.engine.tactics import TacticalContext
from fm.engine.match_context import build_match_context
from fm.world.training import TrainingManager
from fm.world.morale import MoraleManager
from fm.world.player_development import process_weekly_injuries
from fm.world.finance import FinanceManager
from fm.world.cup import DomesticCup
from fm.world.continental import ContinentalManager
from fm.world.dynamics import DynamicsManager
from fm.world.news_engine import NarrativeEngine
from fm.core.consequence_engine import ConsequenceEngine


# ── Transfer window schedule (matchday ranges) ────────────────────────────

SUMMER_WINDOW_START = 0     # pre-season
SUMMER_WINDOW_END = 6       # closes after matchday 6
WINTER_WINDOW_START = 19    # mid-season
WINTER_WINDOW_END = 22      # closes after matchday 22

# ── Cup schedule: matchdays on which cup rounds are played ────────────────
# Spread across the season like real football (FA Cup etc.)
CUP_ROUND_MATCHDAYS = {3: 1, 7: 2, 12: 3, 18: 4, 24: 5, 30: 6, 35: 7}

# Domestic cup names per country
_DOMESTIC_CUPS = {
    "England": "FA Cup",
    "Spain": "Copa del Rey",
    "Germany": "DFB-Pokal",
    "Italy": "Coppa Italia",
    "France": "Coupe de France",
    "Portugal": "Taça de Portugal",
    "Netherlands": "KNVB Beker",
}

# Suspension thresholds
YELLOW_CARD_BAN_THRESHOLD_1 = 5   # 5 yellows = 1 match ban
YELLOW_CARD_BAN_THRESHOLD_2 = 10  # 10 yellows = 2 match ban
RED_CARD_BAN_STANDARD = 1         # standard red = 1 match
RED_CARD_BAN_VIOLENT = 3           # violent conduct = 3 matches


class SeasonManager:
    """Manages season progression, matchday simulation, and season-end events."""

    def __init__(self, session: Session):
        self.session = session
        if USE_V3_ENGINE:
            from fm.engine.possession_chain import MarkovPossessionChain
            from fm.engine.transition_calculator import TransitionCalculator
            self.match_sim = MarkovPossessionChain(TransitionCalculator())
        elif USE_ADVANCED_ENGINE:
            self.match_sim = AdvancedMatchEngine()
        else:
            self.match_sim = MatchSimulator()
        self.batch_sim = BatchMatchSimulator()
        self._cups_initialized = False
        self._cups: dict[str, DomesticCup] = {}
        self._continental: ContinentalManager | None = None
        self._continental_initialized = False

    # ── Season / Calendar queries ──────────────────────────────────────────

    def get_current_season(self) -> Season:
        return self.session.query(Season).order_by(Season.year.desc()).first()

    def get_next_matchday(self, league_id: int | None = None) -> int:
        season = self.get_current_season()
        return season.current_matchday + 1

    def get_total_matchdays(self, league_id: int | None = None) -> int:
        """Return the total number of matchdays in the season for a league."""
        season = self.get_current_season()
        if league_id:
            count = (
                self.session.query(func.max(Fixture.matchday))
                .filter_by(season=season.year, league_id=league_id)
                .scalar()
            )
            return count or 38
        count = (
            self.session.query(func.max(Fixture.matchday))
            .filter_by(season=season.year)
            .scalar()
        )
        return count or 38

    def is_in_transfer_window(self) -> bool:
        """Check if the current matchday falls within a transfer window."""
        season = self.get_current_season()
        md = season.current_matchday
        return (
            SUMMER_WINDOW_START <= md <= SUMMER_WINDOW_END
            or WINTER_WINDOW_START <= md <= WINTER_WINDOW_END
        )

    def get_transfer_window_type(self) -> Optional[str]:
        """Return 'summer', 'winter', or None."""
        season = self.get_current_season()
        md = season.current_matchday
        if SUMMER_WINDOW_START <= md <= SUMMER_WINDOW_END:
            return "summer"
        elif WINTER_WINDOW_START <= md <= WINTER_WINDOW_END:
            return "winter"
        return None

    def get_transfer_deadline(self) -> int:
        """Return the matchday number of the next transfer deadline."""
        season = self.get_current_season()
        md = season.current_matchday
        if md <= SUMMER_WINDOW_END:
            return SUMMER_WINDOW_END
        elif md <= WINTER_WINDOW_END:
            return WINTER_WINDOW_END
        return -1  # no active window

    def get_season_calendar(self) -> list[dict]:
        """Return a calendar of key events for the current season."""
        season = self.get_current_season()
        total_md = self.get_total_matchdays()

        calendar = []
        for md in range(1, total_md + 1):
            entry = {"matchday": md, "events": []}

            # Transfer windows
            if md == SUMMER_WINDOW_START:
                entry["events"].append("Summer transfer window opens")
            if md == SUMMER_WINDOW_END:
                entry["events"].append("Summer transfer window closes")
            if md == WINTER_WINDOW_START:
                entry["events"].append("Winter transfer window opens")
            if md == WINTER_WINDOW_END:
                entry["events"].append("Winter transfer window closes")

            # International breaks (approximate: every 8-10 matchdays)
            if md in (8, 12, 24, 30):
                entry["events"].append("International break")

            # Season milestones
            if md == total_md:
                entry["events"].append("Final day of the season")
            elif md == total_md // 2:
                entry["events"].append("Halfway point of the season")

            if entry["events"]:
                calendar.append(entry)

        return calendar

    # ── Cup management ────────────────────────────────────────────────────

    def initialize_cups(self, season: int):
        """Generate cup draws for all domestic cups at the start of the season."""
        if self._cups_initialized:
            return

        countries = self.session.query(League.country).distinct().all()
        for (country,) in countries:
            cup_name = _DOMESTIC_CUPS.get(country)
            if not cup_name:
                continue
            cup = DomesticCup(self.session, cup_name, country)
            cup.generate_draw(season)
            self._cups[country] = cup

        self._cups_initialized = True

    def _process_cup_round(self, matchday: int, human_club_id: int | None) -> list[dict]:
        """If a cup round is scheduled for this matchday, simulate it."""
        cup_round = CUP_ROUND_MATCHDAYS.get(matchday)
        if cup_round is None:
            return []

        cup_results = []
        for country, cup in self._cups.items():
            result = cup.simulate_round(human_club_id)
            if result.get("results"):
                cup_results.append({
                    "cup_name": cup.cup_name,
                    "round": result.get("round_name", f"Round {cup_round}"),
                    "results": result["results"],
                    "human_result": result.get("human_result"),
                })
        return cup_results

    # ── Continental competitions ──────────────────────────────────────────

    def initialize_continental(self, season: int):
        """Initialise Champions League, Europa League and Conference League."""
        if self._continental_initialized:
            return
        self._continental = ContinentalManager(self.session)
        self._continental.initialize(season)
        self._continental_initialized = True

    def _process_continental_round(
        self, matchday: int, human_club_id: int | None
    ) -> list[dict]:
        """If continental fixtures are scheduled for this matchday, play them.

        Returns a list of result dicts (one per competition that played),
        in the same shape as cup_results.
        """
        if not self._continental:
            return []
        return self._continental.process_matchday(matchday, human_club_id)

    def get_continental_standings(
        self, competition_name: str
    ) -> dict[str, list[dict]]:
        """Return group standings for a continental competition."""
        if self._continental:
            return self._continental.get_standings(competition_name)
        return {}

    def get_club_continental_competition(
        self, club_id: int
    ) -> str | None:
        """Return which continental competition a club is in, or None."""
        if self._continental:
            return self._continental.get_club_competition(club_id)
        return None

    # ── Matchday ───────────────────────────────────────────────────────────

    def advance_matchday(self, human_club_id: int | None = None) -> dict:
        """Simulate one matchday across all leagues.

        Full processing pipeline:
        1. Weekly processing (training, injuries, finances, morale, etc.)
        2. Suspension processing
        3. Transfer window activity (if open)
        4. Simulate background matches (batch)
        5. Simulate human match (full detail)
        6. Post-match processing for all matches
        7. Generate news

        The human player's match (if any) is simulated with full detail.
        All other matches use the batch simulator.

        Returns summary dict.
        """
        season = self.get_current_season()
        next_md = season.current_matchday + 1

        all_fixtures = self.session.query(Fixture).filter_by(
            season=season.year, matchday=next_md, played=False
        ).all()

        # If next_md is already fully played (e.g. from batch sim or cups),
        # skip forward to the first matchday that still has unplayed fixtures.
        if not all_fixtures:
            next_unplayed = (
                self.session.query(Fixture)
                .filter(
                    Fixture.season == season.year,
                    Fixture.matchday > season.current_matchday,
                    Fixture.played == False,
                )
                .order_by(Fixture.matchday.asc())
                .first()
            )
            if next_unplayed:
                # Advance matchday counter to catch up, then process that matchday
                next_md = next_unplayed.matchday
                # Bump past any fully-played matchdays
                season.current_matchday = next_md - 1
                self.session.flush()
                all_fixtures = self.session.query(Fixture).filter_by(
                    season=season.year, matchday=next_md, played=False
                ).all()
            else:
                # Season is truly over — no unplayed fixtures remain
                return {"matchday": next_md, "matches": 0, "human_result": None}

        # ── 1. Weekly processing (between matchdays) ──────────────────────
        self._process_weekly(season, human_club_id)

        # ── 2. Suspension processing ─────────────────────────────────────
        self._process_active_suspensions()

        # ── 3. Transfer window activity ──────────────────────────────────
        if self.is_in_transfer_window():
            self._process_transfer_window_activity(season, human_club_id)

        human_result = None
        human_fixture = None
        full_sim_fixtures = []   # non-human matches that deserve full depth
        batch_fixtures = []

        # Identify upcoming opponents for depth simulation
        # (teams the human will face in the next ~8 matchdays)
        rival_club_ids = set()
        if human_club_id:
            human_league = self.session.query(Club).get(human_club_id)
            if human_league and human_league.league_id:
                upcoming = (
                    self.session.query(Fixture)
                    .filter(
                        Fixture.season == season.year,
                        Fixture.matchday.between(next_md + 1, next_md + 8),
                        Fixture.played == False,
                        (Fixture.home_club_id == human_club_id) |
                        (Fixture.away_club_id == human_club_id),
                    )
                    .all()
                )
                for uf in upcoming:
                    rival_club_ids.add(uf.home_club_id)
                    rival_club_ids.add(uf.away_club_id)
                rival_club_ids.discard(human_club_id)

        for f in all_fixtures:
            if human_club_id and (f.home_club_id == human_club_id
                                  or f.away_club_id == human_club_id):
                human_fixture = f
            elif rival_club_ids and (
                f.home_club_id in rival_club_ids or f.away_club_id in rival_club_ids
            ):
                # Matches involving upcoming opponents get full-depth sim
                full_sim_fixtures.append(f)
            else:
                batch_fixtures.append(f)

        # ── 4a. Full-depth sim for rival fixtures (upcoming opponents) ──
        for f in full_sim_fixtures:
            result_rival = self._simulate_full_match(f)
            self._generate_match_news(f, result_rival)

        # ── 4b. Batch-simulate remaining background matches ─────────────
        if batch_fixtures:
            batch_inputs = []
            from fm.db.models import TacticalSetup
            for f in batch_fixtures:
                home_club = self.session.query(Club).get(f.home_club_id)
                away_club = self.session.query(Club).get(f.away_club_id)

                h_players_db = self.session.query(Player).filter_by(
                    club_id=f.home_club_id).all()
                a_players_db = self.session.query(Player).filter_by(
                    club_id=f.away_club_id).all()

                h_xi, _ = _select_squad(h_players_db, "home")
                a_xi, _ = _select_squad(a_players_db, "away")

                h_tac_db = self.session.query(TacticalSetup).filter_by(
                    club_id=f.home_club_id).first()
                a_tac_db = self.session.query(TacticalSetup).filter_by(
                    club_id=f.away_club_id).first()

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

            # Build a lookup of tactics per fixture for batch history saving
            _batch_tactics = {}
            for f in batch_fixtures:
                h_tac_db = self.session.query(TacticalSetup).filter_by(
                    club_id=f.home_club_id).first()
                a_tac_db = self.session.query(TacticalSetup).filter_by(
                    club_id=f.away_club_id).first()
                _batch_tactics[f.id] = (
                    TacticalContext.from_db(h_tac_db) if h_tac_db else TacticalContext(),
                    TacticalContext.from_db(a_tac_db) if a_tac_db else TacticalContext(),
                )

            for br in batch_results:
                fix = next(f for f in batch_fixtures if f.id == br.fixture_id)
                fix.home_goals = br.home_goals
                fix.away_goals = br.away_goals
                fix.home_possession = br.home_possession
                fix.home_shots = br.home_shots
                fix.away_shots = br.away_shots
                fix.home_xg = br.home_xg
                fix.away_xg = br.away_xg
                fix.played = True

                # Save tactical history for batch matches too
                bt_h, bt_a = _batch_tactics.get(fix.id, (TacticalContext(), TacticalContext()))
                fix.home_formation = bt_h.formation
                fix.home_mentality = bt_h.mentality
                fix.home_pressing = bt_h.pressing
                fix.home_tempo = bt_h.tempo
                fix.home_passing_style = bt_h.passing_style
                fix.home_width = bt_h.width
                fix.home_defensive_line = bt_h.defensive_line
                fix.away_formation = bt_a.formation
                fix.away_mentality = bt_a.mentality
                fix.away_pressing = bt_a.pressing
                fix.away_tempo = bt_a.tempo
                fix.away_passing_style = bt_a.passing_style
                fix.away_width = bt_a.width
                fix.away_defensive_line = bt_a.defensive_line

                self._update_standings(fix)
                self._process_post_match(fix)
                self._generate_match_news(fix)

        # ── 5. Full simulation for human match ────────────────────────────
        if human_fixture:
            human_result = self._simulate_full_match(human_fixture)
            self._generate_match_news(human_fixture, human_result)

        # ── 6. Process matchday income for home teams ──────────────────
        fin = FinanceManager(self.session)
        for f in all_fixtures:
            fin.process_matchday_income(f.home_club_id)

        # ── 7. Periodic sponsorship drip (every 4 matchdays ≈ monthly) ──
        if next_md % 4 == 0:
            fin.process_monthly_finances(season.year, next_md // 4)

        # ── 8. Cup rounds (if scheduled for this matchday) ──────────────
        if not self._cups_initialized:
            self.initialize_cups(season.year)
        cup_results = self._process_cup_round(next_md, human_club_id)

        # ── 9. Continental competitions (CL, EL, ECL) ────────────────
        if not self._continental_initialized:
            self.initialize_continental(season.year)
        continental_results = self._process_continental_round(
            next_md, human_club_id
        )

        season.current_matchday = next_md
        if season.phase == SeasonPhase.PRE_SEASON.value:
            season.phase = SeasonPhase.IN_SEASON.value

        # ── 10. Dynamic Narratives (Sagas) ───────────────────────────
        narrative_mgr = NarrativeEngine(self.session)
        narrative_mgr.process_matchday_entities(season.year, next_md)

        self.session.commit()

        return {
            "matchday": next_md,
            "matches": len(all_fixtures),
            "human_result": human_result,
            "human_fixture": human_fixture,
            "cup_results": cup_results,
            "continental_results": continental_results,
        }

    def _simulate_full_match(self, fixture: Fixture) -> MatchResult:
        """Fully simulate one match with detailed events."""
        home_club = self.session.query(Club).get(fixture.home_club_id)
        away_club = self.session.query(Club).get(fixture.away_club_id)

        h_players_db = self.session.query(Player).filter_by(
            club_id=fixture.home_club_id
        ).all()
        a_players_db = self.session.query(Player).filter_by(
            club_id=fixture.away_club_id
        ).all()

        # Select best XI + subs
        h_xi, h_subs = _select_squad(h_players_db, "home")
        a_xi, a_subs = _select_squad(a_players_db, "away")

        # Get tactics
        from fm.db.models import TacticalSetup
        h_tac_db = self.session.query(TacticalSetup).filter_by(
            club_id=fixture.home_club_id).first()
        a_tac_db = self.session.query(TacticalSetup).filter_by(
            club_id=fixture.away_club_id).first()

        h_tac = TacticalContext.from_db(h_tac_db) if h_tac_db else TacticalContext()
        a_tac = TacticalContext.from_db(a_tac_db) if a_tac_db else TacticalContext()

        # Build match context with all pre-match factors
        season = self.get_current_season()
        next_md = season.current_matchday + 1
        match_context = build_match_context(
            self.session, home_club, away_club,
            home_tactics=h_tac, away_tactics=a_tac,
            season=season,
            matchday=next_md,
        )

        result = self.match_sim.simulate(
            h_xi, a_xi, h_tac, a_tac,
            home_name=home_club.name, away_name=away_club.name,
            home_subs=h_subs, away_subs=a_subs,
            match_context=match_context,
        )

        # Update fixture with enhanced stats
        fixture.home_goals = result.home_goals
        fixture.away_goals = result.away_goals
        fixture.home_possession = result.home_possession
        fixture.home_shots = result.home_stats.shots
        fixture.away_shots = result.away_stats.shots
        fixture.home_shots_on_target = result.home_stats.shots_on_target
        fixture.away_shots_on_target = result.away_stats.shots_on_target
        fixture.home_xg = result.home_xg
        fixture.away_xg = result.away_xg
        # Extended match stats
        fixture.home_passes = result.home_stats.passes
        fixture.home_passes_completed = result.home_stats.passes_completed
        fixture.away_passes = result.away_stats.passes
        fixture.away_passes_completed = result.away_stats.passes_completed
        fixture.home_tackles = result.home_stats.tackles
        fixture.home_tackles_won = result.home_stats.tackles_won
        fixture.away_tackles = result.away_stats.tackles
        fixture.away_tackles_won = result.away_stats.tackles_won
        fixture.home_interceptions = result.home_stats.interceptions
        fixture.away_interceptions = result.away_stats.interceptions
        fixture.home_corners = result.home_stats.corners
        fixture.away_corners = result.away_stats.corners
        fixture.home_fouls = result.home_stats.fouls
        fixture.away_fouls = result.away_stats.fouls
        fixture.home_offsides = result.home_stats.offsides
        fixture.away_offsides = result.away_stats.offsides
        fixture.home_yellow_cards = result.home_stats.yellow_cards
        fixture.away_yellow_cards = result.away_stats.yellow_cards
        fixture.home_red_cards = result.home_stats.red_cards
        fixture.away_red_cards = result.away_stats.red_cards
        fixture.home_saves = result.home_stats.saves
        fixture.away_saves = result.away_stats.saves
        fixture.home_clearances = result.home_stats.clearances
        fixture.away_clearances = result.away_stats.clearances
        fixture.home_crosses = result.home_stats.crosses
        fixture.away_crosses = result.away_stats.crosses
        fixture.home_dribbles_completed = result.home_stats.dribbles_completed
        fixture.away_dribbles_completed = result.away_stats.dribbles_completed
        fixture.home_aerials_won = result.home_stats.aerials_won
        fixture.away_aerials_won = result.away_stats.aerials_won
        fixture.home_big_chances = result.home_stats.big_chances
        fixture.away_big_chances = result.away_stats.big_chances
        fixture.home_key_passes = result.home_stats.key_passes
        fixture.away_key_passes = result.away_stats.key_passes
        fixture.played = True

        # Save tactical history
        fixture.home_formation = h_tac.formation
        fixture.home_mentality = h_tac.mentality
        fixture.home_pressing = h_tac.pressing
        fixture.home_tempo = h_tac.tempo
        fixture.home_passing_style = h_tac.passing_style
        fixture.home_width = h_tac.width
        fixture.home_defensive_line = h_tac.defensive_line
        fixture.away_formation = a_tac.formation
        fixture.away_mentality = a_tac.mentality
        fixture.away_pressing = a_tac.pressing
        fixture.away_tempo = a_tac.tempo
        fixture.away_passing_style = a_tac.passing_style
        fixture.away_width = a_tac.width
        fixture.away_defensive_line = a_tac.defensive_line

        self._update_standings(fixture)

        # Update player stats
        for p in result.home_lineup + result.away_lineup:
            self._update_player_stats(p, season.year)

        # Full post-match processing
        self._process_post_match(fixture, result)

        return result

    # ── Post-match processing ─────────────────────────────────────────────

    def _process_post_match(self, fixture: Fixture, result: MatchResult | None = None):
        """Comprehensive post-match processing for a completed fixture.

        Handles: morale, player development, suspensions, match sharpness,
        fitness costs, and injury generation.
        """
        hg = fixture.home_goals or 0
        ag = fixture.away_goals or 0

        # 1. Morale updates
        self._update_post_match_morale(fixture)

        # 2. Player match sharpness and fitness (for all players at both clubs)
        self._update_match_fitness(fixture)

        # 3. Suspension processing from match cards
        self._process_match_suspensions(fixture, result)

        # 4. Player development from match experience
        self._award_match_experience(fixture, result)

        # 5. Update form strings (already done in _update_standings, but
        #    we also want per-player form updates)
        self._update_player_form(fixture, result)

        # 6. Cascading consequences (form spiral, narratives, sacking check)
        ce = ConsequenceEngine(self.session)
        season_obj = self.get_current_season()
        next_md = season_obj.current_matchday + 1
        for club_id, my_g, their_g in [
            (fixture.home_club_id, hg, ag),
            (fixture.away_club_id, ag, hg),
        ]:
            if my_g > their_g:
                res_char = "W"
            elif my_g < their_g:
                res_char = "L"
            else:
                res_char = "D"
            human_season = self.session.query(Season).filter(
                Season.year == season_obj.year
            ).first()
            is_human = (
                human_season is not None
                and human_season.human_club_id == club_id
            )
            ce.process_post_match(
                club_id, res_char, season_obj.year,
                next_md,
                is_human=is_human,
            )

        # 7. Goal drought detection for strikers
        from fm.core.match_situations import MatchSituationEngine
        for club_id, my_g in [(fixture.home_club_id, hg), (fixture.away_club_id, ag)]:
            if my_g == 0:
                # Check recent fixtures for this club
                recent = self.session.query(Fixture).filter(
                    Fixture.season == season_obj.year,
                    Fixture.played == True,
                    (Fixture.home_club_id == club_id) | (Fixture.away_club_id == club_id),
                ).order_by(Fixture.matchday.desc()).limit(6).all()
                scoreless_run = 0
                for rf in recent:
                    g = rf.home_goals if rf.home_club_id == club_id else rf.away_goals
                    if (g or 0) == 0:
                        scoreless_run += 1
                    else:
                        break
                if scoreless_run >= 5:
                    # Find the top striker
                    strikers = self.session.query(Player).filter(
                        Player.club_id == club_id,
                        Player.position.in_(["ST", "CF", "LW", "RW"]),
                    ).order_by(Player.overall.desc()).first()
                    if strikers:
                        MatchSituationEngine.handle_goal_drought(
                            session=self.session, club_id=club_id,
                            player_id=strikers.id,
                            matches_without_goal=scoreless_run,
                            season=season_obj.year, matchday=next_md,
                        )

    def _update_post_match_morale(self, fixture: Fixture):
        """Adjust player morale based on match result using MoraleManager."""
        hg = fixture.home_goals or 0
        ag = fixture.away_goals or 0

        morale_mgr = MoraleManager(self.session)

        home_club = self.session.query(Club).get(fixture.home_club_id)
        away_club = self.session.query(Club).get(fixture.away_club_id)

        if home_club and away_club:
            morale_mgr.process_match_result(
                fixture.home_club_id, hg, ag,
                was_home=True,
                opponent_reputation=away_club.reputation or 50,
            )
            morale_mgr.process_match_result(
                fixture.away_club_id, ag, hg,
                was_home=False,
                opponent_reputation=home_club.reputation or 50,
            )

    def _update_match_fitness(self, fixture: Fixture):
        """Deduct fitness from players who played in the match."""
        for club_id in (fixture.home_club_id, fixture.away_club_id):
            players = self.session.query(Player).filter_by(club_id=club_id).all()
            # Starting XI lose fitness, bench players less so
            available = [p for p in players
                         if (p.injured_weeks or 0) == 0
                         and (p.suspended_matches or 0) == 0]
            available.sort(key=lambda p: p.overall or 0, reverse=True)

            for i, p in enumerate(available):
                if i < 11:
                    # Starters lose 8-15 fitness based on stamina
                    stamina_factor = (p.stamina or 50) / 100.0
                    loss = random.uniform(8, 15) * (1.0 - stamina_factor * 0.4)
                    p.fitness = max(0.0, (p.fitness or 100.0) - loss)
                elif i < 18:
                    # Subs who might come on lose less
                    p.fitness = max(0.0, (p.fitness or 100.0) - random.uniform(1, 3))

    def _process_match_suspensions(
        self, fixture: Fixture, result: MatchResult | None = None
    ):
        """Process yellow and red cards from a match for suspension tracking.

        For detailed (human) matches we use the MatchResult.
        For batch matches we generate random cards based on averages.
        """
        season = self.get_current_season()

        if result:
            # Detailed match: use actual card data from PlayerInMatch
            all_players = result.home_lineup + result.away_lineup
            for pim in all_players:
                db_player = self.session.get(Player, pim.player_id)
                if not db_player:
                    continue

                if pim.yellow_cards > 0:
                    db_player.yellow_cards_season = (
                        (db_player.yellow_cards_season or 0) + pim.yellow_cards
                    )
                    # Check suspension thresholds
                    yc = db_player.yellow_cards_season or 0
                    if yc == YELLOW_CARD_BAN_THRESHOLD_2:
                        db_player.suspended_matches = (
                            (db_player.suspended_matches or 0) + 2
                        )
                        self._generate_suspension_news(
                            db_player, season, 2,
                            f"accumulated {YELLOW_CARD_BAN_THRESHOLD_2} yellow cards"
                        )
                    elif yc == YELLOW_CARD_BAN_THRESHOLD_1:
                        db_player.suspended_matches = (
                            (db_player.suspended_matches or 0) + 1
                        )
                        self._generate_suspension_news(
                            db_player, season, 1,
                            f"accumulated {YELLOW_CARD_BAN_THRESHOLD_1} yellow cards"
                        )

                if pim.red_card:
                    db_player.red_cards_season = (
                        (db_player.red_cards_season or 0) + 1
                    )
                    # Red card: 1-3 match ban
                    ban = RED_CARD_BAN_STANDARD
                    # Violent conduct check (second yellow vs straight red)
                    if pim.yellow_cards >= 2:
                        ban = RED_CARD_BAN_STANDARD  # second yellow = 1 match
                    elif random.random() < 0.2:
                        ban = RED_CARD_BAN_VIOLENT  # violent conduct
                    else:
                        ban = RED_CARD_BAN_STANDARD + random.randint(0, 1)

                    db_player.suspended_matches = (
                        (db_player.suspended_matches or 0) + ban
                    )
                    self._generate_suspension_news(
                        db_player, season, ban, "a red card"
                    )
        else:
            # Batch match: simulate random card generation for both clubs
            for club_id in (fixture.home_club_id, fixture.away_club_id):
                players = self.session.query(Player).filter_by(club_id=club_id).all()
                if not players:
                    continue
                available = [
                    p for p in players
                    if (p.injured_weeks or 0) == 0
                    and (p.suspended_matches or 0) == 0
                ]
                if not available:
                    continue

                # Average ~2 yellows and ~0.05 reds per team per match
                num_yellows = max(0, int(random.gauss(2.0, 1.2)))
                has_red = random.random() < 0.05

                carded = random.sample(available, min(num_yellows, len(available)))
                for p in carded:
                    p.yellow_cards_season = (p.yellow_cards_season or 0) + 1
                    yc = p.yellow_cards_season
                    if yc == YELLOW_CARD_BAN_THRESHOLD_2:
                        p.suspended_matches = (p.suspended_matches or 0) + 2
                        self._generate_suspension_news(
                            p, season, 2,
                            f"accumulated {YELLOW_CARD_BAN_THRESHOLD_2} yellow cards"
                        )
                    elif yc == YELLOW_CARD_BAN_THRESHOLD_1:
                        p.suspended_matches = (p.suspended_matches or 0) + 1
                        self._generate_suspension_news(
                            p, season, 1,
                            f"accumulated {YELLOW_CARD_BAN_THRESHOLD_1} yellow cards"
                        )

                if has_red and available:
                    red_player = random.choice(available)
                    red_player.red_cards_season = (red_player.red_cards_season or 0) + 1
                    ban = RED_CARD_BAN_STANDARD + random.randint(0, 1)
                    red_player.suspended_matches = (
                        (red_player.suspended_matches or 0) + ban
                    )
                    self._generate_suspension_news(
                        red_player, season, ban, "a red card"
                    )

    def _award_match_experience(
        self, fixture: Fixture, result: MatchResult | None = None
    ):
        """Award experience/development to players who participated in a match.

        Young players (< 24) develop faster from match experience.
        """
        for club_id in (fixture.home_club_id, fixture.away_club_id):
            players = self.session.query(Player).filter_by(club_id=club_id).all()
            available = [
                p for p in players
                if (p.injured_weeks or 0) == 0
                and (p.suspended_matches or 0) == 0
            ]
            available.sort(key=lambda p: p.overall or 0, reverse=True)

            for i, p in enumerate(available[:11]):  # starters only
                if (p.age or 25) <= 23:
                    potential_gap = (p.potential or 50) - (p.overall or 50)
                    if potential_gap > 0:
                        # Small chance of growth from match experience
                        if random.random() < 0.08:
                            growth = 1
                            p.overall = min(99, (p.overall or 50) + growth)
                            # Boost a random relevant attribute
                            attrs = [
                                "passing", "shooting", "defending",
                                "dribbling", "physical", "pace",
                            ]
                            attr = random.choice(attrs)
                            current = getattr(p, attr, 50) or 50
                            setattr(p, attr, min(99, current + 1))

    def _update_player_form(
        self, fixture: Fixture, result: MatchResult | None = None
    ):
        """Update individual player form based on match performance.

        Uses match rating if available, otherwise estimates from result.
        """
        if result:
            for pim in result.home_lineup + result.away_lineup:
                db_player = self.session.get(Player, pim.player_id)
                if not db_player:
                    continue
                # Blend current form with match rating
                rating = pim.avg_rating or 6.0
                # Convert 1-10 rating to 0-100 form scale
                match_form = (rating - 1) * (100 / 9)
                current_form = db_player.form or 65.0
                # Weighted average: 70% old form, 30% this match
                db_player.form = max(0.0, min(100.0,
                    current_form * 0.7 + match_form * 0.3
                ))

    def _generate_suspension_news(
        self, player: Player, season: Season, ban_length: int, reason: str
    ):
        """Generate a news item about a player suspension."""
        club = self.session.get(Club, player.club_id) if player.club_id else None
        club_name = club.name if club else "their club"
        name = player.short_name or player.name

        self.session.add(NewsItem(
            season=season.year,
            matchday=season.current_matchday,
            headline=f"{name} suspended for {ban_length} match(es)",
            body=(
                f"{name} ({club_name}) has been banned for {ban_length} match(es) "
                f"after {reason}."
            ),
            category="general",
        ))

    def _process_active_suspensions(self):
        """Decrement suspension counters for all suspended players.

        Called once per matchday BEFORE matches are played, so
        a 1-match ban means missing exactly one matchday.
        """
        suspended = self.session.query(Player).filter(
            Player.suspended_matches > 0
        ).all()
        for p in suspended:
            p.suspended_matches = max(0, (p.suspended_matches or 0) - 1)

    # ── Standings ─────────────────────────────────────────────────────────

    def _update_standings(self, fixture: Fixture):
        """Update league standings after a completed fixture."""
        season = self.get_current_season()
        home_st = self.session.query(LeagueStanding).filter_by(
            league_id=fixture.league_id, club_id=fixture.home_club_id,
            season=season.year
        ).first()
        away_st = self.session.query(LeagueStanding).filter_by(
            league_id=fixture.league_id, club_id=fixture.away_club_id,
            season=season.year
        ).first()

        if not home_st or not away_st:
            return

        home_st.played += 1
        away_st.played += 1
        home_st.goals_for += fixture.home_goals or 0
        home_st.goals_against += fixture.away_goals or 0
        away_st.goals_for += fixture.away_goals or 0
        away_st.goals_against += fixture.home_goals or 0

        if fixture.home_goals > fixture.away_goals:
            home_st.won += 1
            home_st.points += 3
            away_st.lost += 1
            h_result, a_result = "W", "L"
        elif fixture.home_goals < fixture.away_goals:
            away_st.won += 1
            away_st.points += 3
            home_st.lost += 1
            h_result, a_result = "L", "W"
        else:
            home_st.drawn += 1
            away_st.drawn += 1
            home_st.points += 1
            away_st.points += 1
            h_result, a_result = "D", "D"

        home_st.goal_difference = home_st.goals_for - home_st.goals_against
        away_st.goal_difference = away_st.goals_for - away_st.goals_against

        # Update form string (last 5)
        home_st.form = (home_st.form or "")[-4:] + h_result
        away_st.form = (away_st.form or "")[-4:] + a_result

    def _update_player_stats(self, pim: PlayerInMatch, season_year: int):
        """Update PlayerStats record for a player after a match."""
        ps = self.session.query(PlayerStats).filter_by(
            player_id=pim.player_id, season=season_year
        ).first()
        if not ps:
            ps = PlayerStats(
                player_id=pim.player_id,
                season=season_year,
                appearances=0,
                goals=0,
                assists=0,
                clean_sheets=0,
                yellow_cards=0,
                red_cards=0,
                minutes_played=0,
                avg_rating=6.0
            )
            self.session.add(ps)

        ps.appearances = (ps.appearances or 0) + 1
        ps.goals = (ps.goals or 0) + pim.goals
        ps.assists = (ps.assists or 0) + pim.assists
        if pim.is_gk and pim.saves > 0:
            pass
        ps.yellow_cards = (ps.yellow_cards or 0) + pim.yellow_cards
        if pim.red_card:
            ps.red_cards = (ps.red_cards or 0) + 1
        ps.minutes_played = (ps.minutes_played or 0) + 90
        # Rolling average rating
        ps.avg_rating = (
            ((ps.avg_rating or 6.0) * (ps.appearances - 1) + pim.avg_rating)
            / ps.appearances
        )

    # ── Weekly processing ─────────────────────────────────────────────────

    def _process_weekly(self, season: Season, human_club_id: int | None = None):
        """Process all between-matchday activities for all clubs.

        Comprehensive pipeline:
        1. Training
        2. Fitness recovery
        3. Injury processing
        4. Wages / finances
        5. Morale triggers and weekly morale processing
        6. Player dynamics (happiness, complaints)
        7. Board evaluation
        8. AI manager decisions
        9. Scouting processing
        10. Youth academy development
        11. News generation
        """
        clubs = self.session.query(Club).all()
        training_mgr = TrainingManager(self.session)
        morale_mgr = MoraleManager(self.session)
        dynamics_mgr = DynamicsManager(self.session)

        for club in clubs:
            # Player Dynamics - Morale Contagion
            dynamics_mgr.update_morale_contagion(club.id)

            # 1. Training
            training_mgr.process_weekly_training(club.id)

            # 2. Fitness recovery & Contract anxiety
            players = self.session.query(Player).filter_by(club_id=club.id).all()
            for p in players:
                # Fitness
                if (p.injured_weeks or 0) == 0:
                    recovery = 5.0
                    p.fitness = min(100.0, (p.fitness or 100.0) + recovery)
                
                # Contract anxiety (Players near contract expiry get anxious)
                if (p.contract_expiry or 2026) <= season.year + 1:
                    p_morale = p.morale or 65.0
                    if p_morale > 30:
                        p.morale = max(0.0, p_morale - random.uniform(0.5, 1.5))

            # 5. Morale triggers + weekly morale processing
            morale_events = morale_mgr.process_weekly_morale(
                club.id, season.year, season.current_matchday
            )
            # Generate news from morale events
            for event_desc in morale_events:
                if random.random() < 0.5:  # don't spam every event
                    self.session.add(NewsItem(
                        season=season.year,
                        matchday=season.current_matchday,
                        headline=event_desc[:100],
                        body=event_desc,
                        category="general",
                    ))

            # 7. Board evaluation (periodic)
            if season.current_matchday > 0 and season.current_matchday % 5 == 0:
                self._process_board_evaluation(club, season)

            # 8. AI manager decisions (not for human club)
            if human_club_id and club.id != human_club_id:
                self._process_ai_decisions(club, season)

            # 10. Youth academy development (periodic)
            if season.current_matchday > 0 and season.current_matchday % 8 == 0:
                self._process_youth_development(club, season)

            # Annual Youth Intake (Matchday 28)
            if season.current_matchday == 28:
                from fm.world.youth_academy import YouthAcademyManager
                ya = YouthAcademyManager(self.session)
                ya.generate_youth_intake(club.id, season.year, matchday=season.current_matchday)

        # 3. Injury recovery (reduce injury weeks by 1)
        process_weekly_injuries(self.session)

        # 4. Wages (deducted as fraction of weekly)
        fin = FinanceManager(self.session)
        fin.process_weekly_wages()

        # 11. Injury news generation
        injured_this_week = self.session.query(Player).filter(
            Player.injured_weeks > 0, Player.club_id.isnot(None)
        ).all()
        for p in injured_this_week:
            if p.injured_weeks == (p.injured_weeks or 0):
                club = self.session.query(Club).get(p.club_id)
                if club and random.random() < 0.3:
                    self.session.add(NewsItem(
                        season=season.year,
                        matchday=season.current_matchday,
                        headline=f"{p.short_name or p.name} out injured",
                        body=f"{p.name} ({club.name}) has picked up an injury "
                             f"and will be out for {p.injured_weeks} week(s).",
                        category="injury",
                    ))

        # 12. Cascading weekly consequences (dressing room, finances, etc.)
        cascade_engine = ConsequenceEngine(self.session)
        for club in clubs:
            cascade_engine.process_weekly(
                club.id, season.year, season.current_matchday,
            )

        self.session.flush()


    def _process_board_evaluation(self, club: Club, season: Season):
        """Board evaluates the manager's performance periodically.

        Generates news if the club is significantly underperforming.
        """
        if not club.league_id:
            return

        standing = self.session.query(LeagueStanding).filter_by(
            league_id=club.league_id, club_id=club.id, season=season.year
        ).first()
        if not standing or (standing.played or 0) < 5:
            return

        # Get current position
        all_standings = (
            self.session.query(LeagueStanding)
            .filter_by(league_id=club.league_id, season=season.year)
            .order_by(LeagueStanding.points.desc(),
                      LeagueStanding.goal_difference.desc())
            .all()
        )
        position = None
        total = len(all_standings)
        for i, st in enumerate(all_standings):
            if st.club_id == club.id:
                position = i + 1
                break

        if position is None:
            return

        # Expected position based on reputation
        club_rep = club.reputation or 50
        all_reps = []
        for st in all_standings:
            c = self.session.get(Club, st.club_id)
            all_reps.append((st.club_id, c.reputation or 50 if c else 50))
        all_reps.sort(key=lambda x: x[1], reverse=True)

        expected_pos = None
        for i, (cid, rep) in enumerate(all_reps):
            if cid == club.id:
                expected_pos = i + 1
                break

        if expected_pos is None:
            return

        underperformance = position - expected_pos

        # Board pressure news
        if underperformance >= 6 and random.random() < 0.15:
            self.session.add(NewsItem(
                season=season.year,
                matchday=season.current_matchday,
                headline=f"{club.name} board growing impatient",
                body=(
                    f"The board at {club.name} are concerned about the team's "
                    f"league position ({_ordinal(position)}). They expected a "
                    f"finish around {_ordinal(expected_pos)}."
                ),
                category="general",
            ))

    def _process_ai_decisions(self, club: Club, season: Season):
        """Process AI manager decisions for non-human clubs.

        Includes tactical adaptation and squad selection before each matchday.
        """
        try:
            from fm.world.ai_manager import AIManager
            ai = AIManager(self.session)

            # Adapt tactics for upcoming opponent
            next_md = season.current_matchday + 1
            upcoming = (
                self.session.query(Fixture)
                .filter(
                    Fixture.season == season.year,
                    Fixture.matchday == next_md,
                    Fixture.played == False,
                    (Fixture.home_club_id == club.id) |
                    (Fixture.away_club_id == club.id),
                )
                .first()
            )
            if upcoming:
                opp_id = (
                    upcoming.away_club_id
                    if upcoming.home_club_id == club.id
                    else upcoming.home_club_id
                )
                ai.adapt_tactics(club.id, opp_id)

            # Squad selection every 3 matchdays
            if season.current_matchday % 3 == 0:
                ai.select_squad(club.id)
        except Exception:
            pass  # graceful fallback if AI module has issues

    def _process_youth_development(self, club: Club, season: Season):
        """Process youth academy: develop candidates and occasional first-team growth."""
        # 1. Develop youth candidates in the academy
        from fm.world.youth_academy import YouthAcademyManager
        ya = YouthAcademyManager(self.session)
        ya.process_monthly_development(club.id)

        # 2. Existing first-team youth development
        players = self.session.query(Player).filter_by(club_id=club.id).all()
        facilities = club.facilities_level or 5  # 1-10

        for p in players:
            age = p.age or 25
            if age > 23:
                continue

            potential_gap = (p.potential or 50) - (p.overall or 50)
            if potential_gap <= 0:
                continue

            # Better facilities = better youth development
            dev_chance = 0.15 + (facilities / 10.0) * 0.15  # 0.15 to 0.30
            if random.random() < dev_chance:
                growth = random.randint(1, min(potential_gap, 2))
                p.overall = min(99, (p.overall or 50) + growth)

                # --- ADVANCED BIAS: Physical attributes grow faster for 15-18 year olds ---
                attr_options = ["pace", "shooting", "passing", "dribbling", "defending", "physical"]
                weights = [1.0] * len(attr_options)
                if 15 <= age <= 18:
                    # Double weight for physical/pace
                    weights[0] = 2.0  # pace
                    weights[5] = 2.0  # physical

                chosen_attr = random.choices(attr_options, weights=weights, k=1)[0]
                curr_val = getattr(p, chosen_attr, 50) or 50
                setattr(p, chosen_attr, min(99, curr_val + 1))

            # --- PERSONALITY SHIFT: Small chance to improve/decline traits ---
            if random.random() < 0.05:  # 5% chance per development cycle
                manager = self.session.query(Manager).filter_by(club_id=club.id).first()
                man_quality = (manager.youth_development / 100.0) if manager else 0.5
                shift_chance = 0.4 + (man_quality * 0.2) + (facilities / 20.0)  # ~0.5 to 0.7 chance of improvement

                trait = random.choice(["determination", "professionalism", "ambition"])
                curr_trait = getattr(p, trait, 50) or 50
                if random.random() < shift_chance:
                    setattr(p, trait, min(99, curr_trait + 1))
                else:
                    setattr(p, trait, max(1, curr_trait - 1))

    # Removed _generate_youth_intake as it is now handled by YouthAcademyManager

    # ── Transfer window processing ────────────────────────────────────────

    def _process_transfer_window_activity(
        self, season: Season, human_club_id: int | None = None
    ):
        """Process transfer activity during open windows.

        AI clubs make transfers, contracts are renewed, loans recalled.
        """
        window_type = self.get_transfer_window_type()
        if not window_type:
            return

        # AI clubs: chance of making a transfer each matchday during window
        clubs = self.session.query(Club).all()
        for club in clubs:
            if human_club_id and club.id == human_club_id:
                continue  # human handles their own transfers

            # Transfer activity probability
            if window_type == "summer":
                activity_chance = 0.06  # higher in summer
            else:
                activity_chance = 0.03  # lower in winter

            if random.random() > activity_chance:
                continue

            self._ai_transfer_attempt(club, season, window_type)

        # Contract renewals for AI clubs
        if season.current_matchday % 4 == 0:
            self._process_contract_renewals(season, human_club_id)

    def _ai_transfer_attempt(self, club: Club, season: Season, window_type: str):
        """Attempt an AI transfer for a club."""
        try:
            from fm.world.transfer_market import TransferMarket
            tm = TransferMarket(self.session)

            # Simple logic: buy if budget allows and squad is thin
            players = self.session.query(Player).filter_by(club_id=club.id).all()
            squad_size = len(players)

            if squad_size < 20 and (club.budget or 0) > 1.0:
                # Try to find a free agent or cheap player
                free_agents = (
                    self.session.query(Player)
                    .filter(Player.club_id.is_(None))
                    .filter(Player.overall >= max(40, (club.reputation or 50) - 20))
                    .order_by(Player.overall.desc())
                    .limit(10)
                    .all()
                )
                if free_agents:
                    target = random.choice(free_agents[:5])
                    target.club_id = club.id
                    target.contract_expiry = season.year + random.randint(1, 3)
                    target.wage = (target.market_value or 0.1) * 0.01

                    self.session.add(Transfer(
                        player_id=target.id,
                        from_club_id=None,
                        to_club_id=club.id,
                        fee=0.0,
                        wage=target.wage,
                        season=season.year,
                    ))

                    name = target.short_name or target.name
                    self.session.add(NewsItem(
                        season=season.year,
                        matchday=season.current_matchday,
                        headline=f"{club.name} sign free agent {name}",
                        body=(
                            f"{club.name} have signed {name} on a free transfer. "
                            f"The {target.position} joins on a deal until "
                            f"{target.contract_expiry}."
                        ),
                        category="transfer",
                    ))
        except Exception:
            pass  # graceful fallback

    def _process_contract_renewals(
        self, season: Season, human_club_id: int | None = None
    ):
        """AI clubs renew contracts for key players nearing expiry."""
        clubs = self.session.query(Club).all()

        for club in clubs:
            if human_club_id and club.id == human_club_id:
                continue

            players = self.session.query(Player).filter_by(club_id=club.id).all()
            for p in players:
                if (p.contract_expiry or 2026) > season.year + 1:
                    continue  # not near expiry

                # Key player? Renew if morale is OK
                if (p.overall or 50) >= 65 and (p.morale or 65.0) >= 40:
                    if random.random() < 0.6:
                        p.contract_expiry = season.year + random.randint(2, 4)
                        # Slight wage increase
                        p.wage = (p.wage or 0) * random.uniform(1.05, 1.20)

    def _check_transfer_window_events(self, season: Season, matchday: int):
        """Generate news when transfer windows open or close."""
        if matchday == SUMMER_WINDOW_START:
            self.session.add(NewsItem(
                season=season.year, matchday=matchday,
                headline="Summer transfer window is open!",
                body="Clubs can now register new signings. The window closes "
                     f"after matchday {SUMMER_WINDOW_END}.",
                category="transfer",
            ))
        elif matchday == SUMMER_WINDOW_END + 1:
            self.session.add(NewsItem(
                season=season.year, matchday=matchday,
                headline="Summer transfer window has closed",
                body="No more signings until the winter window.",
                category="transfer",
            ))
        elif matchday == WINTER_WINDOW_START:
            self.session.add(NewsItem(
                season=season.year, matchday=matchday,
                headline="Winter transfer window is open!",
                body="The January window is open for business. Closes after "
                     f"matchday {WINTER_WINDOW_END}.",
                category="transfer",
            ))
        elif matchday == WINTER_WINDOW_END + 1:
            self.session.add(NewsItem(
                season=season.year, matchday=matchday,
                headline="Winter transfer window has closed",
                body="The January window is shut. No more signings until the summer.",
                category="transfer",
            ))

    # ── International break ───────────────────────────────────────────────

    def process_international_break(self):
        """Process an international break between matchdays.

        Some players may get injured on international duty.
        Players miss club training and may return tired.
        """
        season = self.get_current_season()

        # Select players who would go on international duty (high overall)
        international_players = (
            self.session.query(Player)
            .filter(Player.club_id.isnot(None))
            .filter(Player.overall >= 72)
            .filter(Player.injured_weeks == 0)
            .all()
        )

        for p in international_players:
            # 5% chance of injury on international duty
            if random.random() < 0.05:
                p.injured_weeks = random.randint(1, 4)
                club = self.session.get(Club, p.club_id) if p.club_id else None
                club_name = club.name if club else "their club"
                name = p.short_name or p.name

                self.session.add(NewsItem(
                    season=season.year,
                    matchday=season.current_matchday,
                    headline=f"{name} injured on international duty!",
                    body=(
                        f"Bad news for {club_name} - {name} has returned from "
                        f"international duty with an injury. Out for "
                        f"{p.injured_weeks} week(s)."
                    ),
                    category="injury",
                ))
            else:
                # Return slightly fatigued
                p.fitness = max(60.0, (p.fitness or 100.0) - random.uniform(3, 8))

        self.session.flush()

    # ── News generation ───────────────────────────────────────────────────

    def _generate_match_news(self, fixture: Fixture, result=None):
        """Generate news items from match results."""
        season = self.get_current_season()
        hc = self.session.query(Club).get(fixture.home_club_id)
        ac = self.session.query(Club).get(fixture.away_club_id)
        if not hc or not ac:
            return

        hg = fixture.home_goals or 0
        ag = fixture.away_goals or 0
        diff = abs(hg - ag)

        # Big result news
        if diff >= 4:
            winner = hc.name if hg > ag else ac.name
            loser = ac.name if hg > ag else hc.name
            self.session.add(NewsItem(
                season=season.year,
                matchday=season.current_matchday,
                headline=f"{winner} thrash {loser} {max(hg,ag)}-{min(hg,ag)}!",
                body=f"A dominant display saw {winner} run riot against {loser}.",
                category="match",
            ))
        # Upset news (weaker team wins by 2+)
        elif diff >= 2:
            h_rep = hc.reputation or 50
            a_rep = ac.reputation or 50
            if hg > ag and h_rep < a_rep - 15:
                self.session.add(NewsItem(
                    season=season.year,
                    matchday=season.current_matchday,
                    headline=f"Shock! {hc.name} stun {ac.name}",
                    body=f"Underdogs {hc.name} pulled off a surprise {hg}-{ag} win.",
                    category="match",
                ))
            elif ag > hg and a_rep < h_rep - 15:
                self.session.add(NewsItem(
                    season=season.year,
                    matchday=season.current_matchday,
                    headline=f"Shock! {ac.name} stun {hc.name}",
                    body=f"Underdogs {ac.name} pulled off a surprise {ag}-{hg} away win.",
                    category="match",
                ))

        # High-scoring draw
        if hg == ag and hg >= 3:
            self.session.add(NewsItem(
                season=season.year,
                matchday=season.current_matchday,
                headline=f"Thriller! {hc.name} {hg}-{ag} {ac.name}",
                body=f"An incredible {hg}-{ag} draw between {hc.name} and {ac.name}.",
                category="match",
            ))

        # Clean sheet by underdog
        if (hg == 0 or ag == 0) and diff >= 1:
            h_rep = hc.reputation or 50
            a_rep = ac.reputation or 50
            if ag == 0 and hg > 0 and h_rep < a_rep - 10:
                self.session.add(NewsItem(
                    season=season.year,
                    matchday=season.current_matchday,
                    headline=f"{hc.name} shut out {ac.name}",
                    body=(
                        f"{hc.name} kept a clean sheet in an impressive "
                        f"{hg}-0 home victory over {ac.name}."
                    ),
                    category="match",
                ))

    # ── End of season ────────────────────────────────────────────────────

    def is_season_complete(self) -> bool:
        """Check if all fixtures for the current season are played."""
        season = self.get_current_season()
        remaining = self.session.query(Fixture).filter_by(
            season=season.year, played=False
        ).count()
        return remaining == 0

    def end_season(self):
        """Comprehensive end-of-season processing.

        1. Final standings
        2. Awards
        3. Promotion/relegation
        4. Player development (age all)
        5. Contract expirations (free agents)
        6. Financial end of year
        7. Board review (expectations)
        8. Youth intake (promoted at new season start)
        9. Reset seasonal counters
        """
        season = self.get_current_season()
        season.phase = SeasonPhase.END_OF_SEASON.value

        leagues = self.session.query(League).all()

        # 1 & 3. Standings and promotion/relegation
        for league in leagues:
            self._process_promotion_relegation(league, season.year)

        # 2. Awards
        for league in leagues:
            awards = self.process_end_of_season_awards(league.id, season.year)
            for award in awards:
                self.session.add(NewsItem(
                    season=season.year,
                    headline=award["headline"],
                    body=award["body"],
                    category="award",
                ))

        # 4. (aging happens at start_new_season)

        # 5. Contract expirations
        self._process_contract_expirations(season)

        # 6. Financial end of year
        self._process_end_of_year_finances(season)

        # 9. Reset seasonal card counters
        all_players = self.session.query(Player).all()
        for p in all_players:
            p.yellow_cards_season = 0
            p.red_cards_season = 0
            p.suspended_matches = 0

        self.session.commit()

    def generate_season_summary(self, club_id: int) -> dict:
        """Generate a comprehensive end-of-season report for a club."""
        season = self.get_current_season()

        # League position
        club = self.session.get(Club, club_id)
        standing = self.session.query(LeagueStanding).filter_by(
            club_id=club_id, season=season.year
        ).first()

        position = None
        if standing and club and club.league_id:
            all_standings = (
                self.session.query(LeagueStanding)
                .filter_by(league_id=club.league_id, season=season.year)
                .order_by(LeagueStanding.points.desc(),
                          LeagueStanding.goal_difference.desc())
                .all()
            )
            for i, st in enumerate(all_standings):
                if st.club_id == club_id:
                    position = i + 1
                    break

        # Player stats
        player_stats = (
            self.session.query(PlayerStats)
            .filter_by(season=season.year)
            .all()
        )
        player_ids = {
            p.id for p in self.session.query(Player).filter_by(club_id=club_id).all()
        }
        club_stats = [ps for ps in player_stats if ps.player_id in player_ids]

        # Top scorer
        top_scorer = None
        top_goals = 0
        for ps in club_stats:
            if (ps.goals or 0) > top_goals:
                top_goals = ps.goals
                p = self.session.get(Player, ps.player_id)
                top_scorer = p.short_name or p.name if p else "Unknown"

        # Top assists
        top_assister = None
        top_assists = 0
        for ps in club_stats:
            if (ps.assists or 0) > top_assists:
                top_assists = ps.assists
                p = self.session.get(Player, ps.player_id)
                top_assister = p.short_name or p.name if p else "Unknown"

        # Best average rating
        best_rated = None
        best_rating = 0.0
        for ps in club_stats:
            if (ps.appearances or 0) >= 5 and (ps.avg_rating or 0) > best_rating:
                best_rating = ps.avg_rating
                p = self.session.get(Player, ps.player_id)
                best_rated = p.short_name or p.name if p else "Unknown"

        # Most improved (largest overall growth - approximated by young + high form)
        most_improved = None
        players = self.session.query(Player).filter_by(club_id=club_id).all()
        best_form = 0.0
        for p in players:
            if (p.age or 25) <= 23 and (p.form or 0) > best_form:
                best_form = p.form or 0
                most_improved = p.short_name or p.name

        return {
            "season": season.year,
            "league_position": position,
            "points": standing.points if standing else 0,
            "played": standing.played if standing else 0,
            "won": standing.won if standing else 0,
            "drawn": standing.drawn if standing else 0,
            "lost": standing.lost if standing else 0,
            "goals_for": standing.goals_for if standing else 0,
            "goals_against": standing.goals_against if standing else 0,
            "top_scorer": top_scorer,
            "top_scorer_goals": top_goals,
            "top_assister": top_assister,
            "top_assists": top_assists,
            "best_rated_player": best_rated,
            "best_rating": round(best_rating, 2),
            "most_improved": most_improved,
            "budget": round(club.budget or 0, 2) if club else 0,
        }

    def process_end_of_season_awards(
        self, league_id: int, season_year: int
    ) -> list[dict]:
        """Generate award winners for a league.

        Awards: Player of the Year, Young Player, Golden Boot,
        Golden Glove, Manager of the Year, Team of the Year.
        """
        awards: list[dict] = []

        league = self.session.get(League, league_id)
        if not league:
            return awards

        # Get all clubs in this league
        clubs = self.session.query(Club).filter_by(league_id=league_id).all()
        club_ids = {c.id for c in clubs}

        # Get all player stats for this season
        all_stats = self.session.query(PlayerStats).filter_by(season=season_year).all()
        league_stats = []
        for ps in all_stats:
            player = self.session.get(Player, ps.player_id)
            if player and player.club_id in club_ids:
                league_stats.append((ps, player))

        if not league_stats:
            return awards

        # --- Golden Boot (top scorer) ---
        top_scorer_ps, top_scorer_p = max(
            league_stats, key=lambda x: x[0].goals or 0
        )
        if (top_scorer_ps.goals or 0) > 0:
            name = top_scorer_p.short_name or top_scorer_p.name
            awards.append({
                "award": "Golden Boot",
                "player_id": top_scorer_p.id,
                "headline": f"{name} wins the {league.name} Golden Boot!",
                "body": (
                    f"{name} finished as the top scorer in {league.name} "
                    f"with {top_scorer_ps.goals} goals."
                ),
            })

        # --- Golden Glove (fewest goals conceded by team whose GK played most) ---
        # Simplified: best avg rating among GKs
        gk_stats = [
            (ps, p) for ps, p in league_stats
            if p.position == "GK" and (ps.appearances or 0) >= 10
        ]
        if gk_stats:
            best_gk_ps, best_gk_p = max(
                gk_stats, key=lambda x: x[0].avg_rating or 0
            )
            name = best_gk_p.short_name or best_gk_p.name
            awards.append({
                "award": "Golden Glove",
                "player_id": best_gk_p.id,
                "headline": f"{name} wins the {league.name} Golden Glove!",
                "body": (
                    f"Goalkeeper {name} had an outstanding season with an "
                    f"average rating of {best_gk_ps.avg_rating:.1f}."
                ),
            })

        # --- Player of the Year (best avg rating with min 15 appearances) ---
        qualified = [
            (ps, p) for ps, p in league_stats
            if (ps.appearances or 0) >= 15
        ]
        if qualified:
            poty_ps, poty_p = max(
                qualified, key=lambda x: x[0].avg_rating or 0
            )
            name = poty_p.short_name or poty_p.name
            awards.append({
                "award": "Player of the Year",
                "player_id": poty_p.id,
                "headline": f"{name} named {league.name} Player of the Year!",
                "body": (
                    f"{name} is the standout performer of the {league.name} "
                    f"season with an average rating of {poty_ps.avg_rating:.1f}, "
                    f"{poty_ps.goals or 0} goals and {poty_ps.assists or 0} assists."
                ),
            })

        # --- Young Player of the Year (age <= 23) ---
        young_qualified = [
            (ps, p) for ps, p in league_stats
            if (p.age or 25) <= 23 and (ps.appearances or 0) >= 10
        ]
        if young_qualified:
            ypoty_ps, ypoty_p = max(
                young_qualified, key=lambda x: x[0].avg_rating or 0
            )
            name = ypoty_p.short_name or ypoty_p.name
            awards.append({
                "award": "Young Player of the Year",
                "player_id": ypoty_p.id,
                "headline": f"{name} named {league.name} Young Player of the Year!",
                "body": (
                    f"At just {ypoty_p.age}, {name} has been exceptional "
                    f"with {ypoty_ps.goals or 0} goals and {ypoty_ps.assists or 0} "
                    f"assists in {ypoty_ps.appearances or 0} appearances."
                ),
            })

        # --- Manager of the Year (club that most outperformed expectations) ---
        standings = (
            self.session.query(LeagueStanding)
            .filter_by(league_id=league_id, season=season_year)
            .order_by(LeagueStanding.points.desc(),
                      LeagueStanding.goal_difference.desc())
            .all()
        )
        if standings:
            # Compare actual position vs expected (by reputation)
            rep_sorted = sorted(
                [(st, self.session.get(Club, st.club_id)) for st in standings],
                key=lambda x: x[1].reputation if x[1] else 0,
                reverse=True,
            )

            best_overperformance = -999
            best_club = None
            for actual_pos, st in enumerate(standings):
                club = self.session.get(Club, st.club_id)
                if not club:
                    continue
                expected_pos = next(
                    (i for i, (_, c) in enumerate(rep_sorted) if c and c.id == club.id),
                    actual_pos,
                )
                overperf = expected_pos - actual_pos
                if overperf > best_overperformance:
                    best_overperformance = overperf
                    best_club = club

            if best_club and best_overperformance > 0:
                mgr = best_club.manager
                mgr_name = mgr.name if mgr else f"{best_club.name} manager"
                awards.append({
                    "award": "Manager of the Year",
                    "headline": f"{mgr_name} wins {league.name} Manager of the Year!",
                    "body": (
                        f"{mgr_name}'s work at {best_club.name} has been "
                        f"recognised after a remarkable season."
                    ),
                })

        # --- Team of the Year (best XI by avg rating) ---
        if len(qualified) >= 11:
            # Pick best player per position group
            toty_names = []
            for pos_group, count in [
                (["GK"], 1),
                (["CB", "LB", "RB", "LWB", "RWB"], 4),
                (["CDM", "CM", "CAM", "LM", "RM"], 3),
                (["LW", "RW", "CF", "ST"], 3),
            ]:
                candidates = [
                    (ps, p) for ps, p in qualified if p.position in pos_group
                ]
                candidates.sort(key=lambda x: x[0].avg_rating or 0, reverse=True)
                for ps, p in candidates[:count]:
                    toty_names.append(p.short_name or p.name)

            if toty_names:
                awards.append({
                    "award": "Team of the Year",
                    "headline": f"{league.name} Team of the Year announced!",
                    "body": f"Team of the Year: {', '.join(toty_names)}.",
                })

        return awards

    def _process_contract_expirations(self, season: Season):
        """Players whose contracts expire become free agents."""
        expiring = self.session.query(Player).filter(
            Player.contract_expiry <= season.year,
            Player.club_id.isnot(None),
        ).all()

        for p in expiring:
            club = self.session.get(Club, p.club_id) if p.club_id else None
            club_name = club.name if club else "their club"
            name = p.short_name or p.name

            # Higher-profile players get news
            if (p.overall or 0) >= 65:
                self.session.add(NewsItem(
                    season=season.year,
                    headline=f"{name} leaves {club_name} as contract expires",
                    body=(
                        f"{name} has left {club_name} after their contract expired. "
                        f"The {p.position} is now a free agent."
                    ),
                    category="transfer",
                ))

            p.club_id = None
            p.morale = 50.0

    def _process_end_of_year_finances(self, season: Season):
        """Process end-of-year financial events: TV money, sponsorship."""
        fin = FinanceManager(self.session)

        leagues = self.session.query(League).all()
        for league in leagues:
            fin.process_season_tv_money(league.id, season.year)

        # Sponsorship income (proportional to reputation)
        clubs = self.session.query(Club).all()
        for club in clubs:
            rep = club.reputation or 50
            sponsor_income = rep * 0.02 + random.uniform(0, 1.0)  # 0-3M approx
            club.budget = (club.budget or 0) + sponsor_income

    def _process_promotion_relegation(self, league: League, season_year: int):
        """Handle promotion and relegation between tiers."""
        standings = self.session.query(LeagueStanding).filter_by(
            league_id=league.id, season=season_year
        ).order_by(LeagueStanding.points.desc(),
                   LeagueStanding.goal_difference.desc()).all()

        if not standings:
            return

        # Find paired league (same country, adjacent tier)
        if league.tier == 1:
            paired = self.session.query(League).filter_by(
                country=league.country, tier=2
            ).first()
        elif league.tier == 2:
            paired = self.session.query(League).filter_by(
                country=league.country, tier=1
            ).first()
        else:
            return

        if not paired:
            return

        paired_standings = self.session.query(LeagueStanding).filter_by(
            league_id=paired.id, season=season_year
        ).order_by(LeagueStanding.points.desc(),
                   LeagueStanding.goal_difference.desc()).all()

        if league.tier == 1 and league.relegation_spots > 0:
            relegated = standings[-league.relegation_spots:]
            promoted = paired_standings[:paired.promotion_spots]

            for st in relegated:
                club = self.session.query(Club).get(st.club_id)
                if club:
                    club.league_id = paired.id
                    # Relegation morale hit
                    players = self.session.query(Player).filter_by(
                        club_id=club.id
                    ).all()
                    for p in players:
                        p.morale = max(0.0, (p.morale or 65.0) - 15.0)
                    self.session.add(NewsItem(
                        season=season_year, headline=f"{club.name} relegated!",
                        body=(
                            f"{club.name} have been relegated to {paired.name}. "
                            f"A devastating end to a difficult season."
                        ),
                        category="general",
                    ))

            for st in promoted:
                club = self.session.query(Club).get(st.club_id)
                if club:
                    club.league_id = league.id
                    # Promotion morale boost
                    players = self.session.query(Player).filter_by(
                        club_id=club.id
                    ).all()
                    for p in players:
                        p.morale = min(100.0, (p.morale or 65.0) + 20.0)
                    self.session.add(NewsItem(
                        season=season_year, headline=f"{club.name} promoted!",
                        body=(
                            f"{club.name} have been promoted to {league.name}! "
                            f"Celebrations all round after a fantastic campaign."
                        ),
                        category="general",
                    ))

    def start_new_season(self):
        """Start a new season: reset standings, generate fixtures, age players."""
        from fm.world.player_development import age_all_players
        from fm.db.ingestion import _generate_all_fixtures, _init_standings
        from fm.world.youth_academy import YouthAcademyManager

        old_season = self.get_current_season()
        new_year = old_season.year + 1

        # Age players
        age_all_players(self.session)

        # Age youth candidates and process end-of-season youth tasks
        ya = YouthAcademyManager(self.session)
        ya.process_end_of_loan_returns(new_year)
        all_clubs = self.session.query(Club).all()
        for club in all_clubs:
            ya.age_candidates(club.id)
            ya.auto_promote_for_ai(club.id, new_year)
            ya.update_squad_roles(club.id)

        # Create new season
        new_season = Season(
            year=new_year,
            current_matchday=0,
            phase=SeasonPhase.PRE_SEASON.value,
            human_club_id=old_season.human_club_id,
        )
        self.session.add(new_season)
        self.session.flush()

        # Generate new fixtures and standings
        leagues = self.session.query(League).all()
        _generate_all_fixtures(self.session, leagues)
        _init_standings(self.session, leagues)

        # Reset player seasonal counters
        all_players = self.session.query(Player).all()
        for p in all_players:
            p.yellow_cards_season = 0
            p.red_cards_season = 0
            p.suspended_matches = 0

        # Pre-season morale boost (fresh start)
        for p in all_players:
            if p.club_id:
                current = p.morale or 65.0
                p.morale = min(100.0, current + random.uniform(3, 8))

        # Reset continental and cup state so they re-initialise next season.
        self._cups_initialized = False
        self._cups = {}
        self._continental_initialized = False
        self._continental = None

        self.session.commit()

    # ── Suspension system ─────────────────────────────────────────────────

    def process_suspensions(self):
        """Handle yellow card accumulation and suspensions.

        Called explicitly if needed outside normal matchday flow.
        5 yellow cards = 1 match ban
        10 yellow cards = 2 match ban
        Red card = varies (1-3 match ban)
        Violent conduct = 3+ matches
        """
        players = self.session.query(Player).filter(
            Player.yellow_cards_season > 0
        ).all()

        for p in players:
            yc = p.yellow_cards_season or 0
            if yc == YELLOW_CARD_BAN_THRESHOLD_1 and (p.suspended_matches or 0) == 0:
                p.suspended_matches = 1
            elif yc == YELLOW_CARD_BAN_THRESHOLD_2 and (p.suspended_matches or 0) == 0:
                p.suspended_matches = 2

        self.session.flush()


# ── Helpers ────────────────────────────────────────────────────────────────

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
    available = [p for p in players_db if (p.injured_weeks or 0) == 0
                 and (p.suspended_matches or 0) == 0]
    available.sort(key=lambda p: p.overall or 0, reverse=True)

    # Need 1 GK + 10 outfield
    gks = [p for p in available if p.position == "GK"]
    outfield = [p for p in available if p.position != "GK"]

    xi = []
    if gks:
        xi.append(PlayerInMatch.from_db_player(gks[0], side))
        gks = gks[1:]
    if outfield:
        for p in outfield[:10]:
            xi.append(PlayerInMatch.from_db_player(p, side))

    # Subs
    remaining = gks + outfield[10:]
    subs = [PlayerInMatch.from_db_player(p, side) for p in remaining[:7]]
    for s in subs:
        s.is_on_pitch = False

    return xi, subs


def _ordinal(n: int) -> str:
    """Convert integer to ordinal string (1st, 2nd, 3rd, etc.)."""
    if 11 <= (n % 100) <= 13:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"
