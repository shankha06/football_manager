"""UEFA continental competition system: Champions League, Europa League,
Conference League.

32-team group stage (8 groups of 4) followed by knockout rounds.  Integrates
with the existing season calendar via ``ContinentalManager.process_matchday``.
"""
from __future__ import annotations

import random
from typing import Optional

from sqlalchemy.orm import Session

from fm.db.models import (
    Club, League, LeagueStanding, ContinentalGroup, ContinentalFixture,
    Player, NewsItem, Season, CupFixture,
)
from fm.engine.cuda_batch import BatchMatchSimulator, BatchFixtureInput
from fm.engine.match_engine import AdvancedMatchEngine
from fm.engine.simulator import MatchSimulator
from fm.engine.match_state import PlayerInMatch, MatchResult
from fm.engine.match_context import build_match_context
from fm.engine.tactics import TacticalContext
from fm.config import USE_ADVANCED_ENGINE


# ═══════════════════════════════════════════════════════════════════════════
#  Configuration tables
# ═══════════════════════════════════════════════════════════════════════════

# CL qualification slots by country (top-N from tier-1 league).
CL_SLOTS: dict[str, int] = {
    "England": 4,
    "Spain": 4,
    "Germany": 4,
    "Italy": 4,
    "France": 3,
    "Portugal": 2,
    "Netherlands": 2,
    "Scotland": 1,
    "Turkey": 1,
}

# EL: next N places after CL slots (+ domestic cup winners if not in CL).
EL_EXTRA_PLACES: dict[str, int] = {
    "England": 3,
    "Spain": 3,
    "Germany": 3,
    "Italy": 3,
    "France": 3,
    "Portugal": 2,
    "Netherlands": 2,
    "Scotland": 1,
    "Turkey": 2,
}

# ECL: next N places after EL slots.
ECL_EXTRA_PLACES: dict[str, int] = {
    "England": 1,
    "Spain": 1,
    "Germany": 1,
    "Italy": 1,
    "France": 1,
    "Portugal": 1,
    "Netherlands": 1,
    "Scotland": 1,
    "Turkey": 1,
}

# Prize money in millions EUR.
PRIZE_MONEY: dict[str, dict[str, float]] = {
    "Champions League": {
        "group": 15.0, "r16": 10.0, "qf": 10.0, "sf": 12.0,
        "winner": 20.0, "runner_up": 15.0,
    },
    "Europa League": {
        "group": 5.0, "r16": 3.0, "qf": 3.0, "sf": 5.0,
        "winner": 10.0, "runner_up": 5.0,
    },
    "Conference League": {
        "group": 3.0, "r16": 1.5, "qf": 2.0, "sf": 3.0,
        "winner": 5.0, "runner_up": 3.0,
    },
}

# Matchday mapping for continental rounds.
# CL on even matchdays, EL/ECL on odd matchdays around those dates.
CL_MATCHDAY_SCHEDULE: dict[int, str] = {
    # Group stage (6 matchdays)
    2: "group_md1",
    4: "group_md2",
    6: "group_md3",
    8: "group_md4",
    10: "group_md5",
    12: "group_md6",
    # Knockouts
    16: "r16_leg1",
    18: "r16_leg2",
    22: "qf_leg1",
    24: "qf_leg2",
    28: "sf_leg1",
    30: "sf_leg2",
    36: "final",
}

EL_MATCHDAY_SCHEDULE: dict[int, str] = {
    3: "group_md1",
    5: "group_md2",
    7: "group_md3",
    9: "group_md4",
    11: "group_md5",
    13: "group_md6",
    17: "r16_leg1",
    19: "r16_leg2",
    23: "qf_leg1",
    25: "qf_leg2",
    29: "sf_leg1",
    31: "sf_leg2",
    37: "final",
}

ECL_MATCHDAY_SCHEDULE: dict[int, str] = {
    3: "group_md1",
    5: "group_md2",
    7: "group_md3",
    9: "group_md4",
    11: "group_md5",
    13: "group_md6",
    17: "r16_leg1",
    19: "r16_leg2",
    23: "qf_leg1",
    25: "qf_leg2",
    29: "sf_leg1",
    31: "sf_leg2",
    37: "final",
}

# Flat lookup: matchday -> list of (competition_name, round_tag)
_ALL_SCHEDULES: dict[int, list[tuple[str, str]]] = {}
for _md, _tag in CL_MATCHDAY_SCHEDULE.items():
    _ALL_SCHEDULES.setdefault(_md, []).append(("Champions League", _tag))
for _md, _tag in EL_MATCHDAY_SCHEDULE.items():
    _ALL_SCHEDULES.setdefault(_md, []).append(("Europa League", _tag))
for _md, _tag in ECL_MATCHDAY_SCHEDULE.items():
    _ALL_SCHEDULES.setdefault(_md, []).append(("Conference League", _tag))


STAGE_DISPLAY_NAMES = {
    "group": "Group Stage",
    "r16": "Round of 16",
    "qf": "Quarter-Final",
    "sf": "Semi-Final",
    "final": "Final",
}


# ═══════════════════════════════════════════════════════════════════════════
#  ContinentalCompetition
# ═══════════════════════════════════════════════════════════════════════════

class ContinentalCompetition:
    """Manages a single continental tournament (CL / EL / ECL)."""

    def __init__(
        self,
        session: Session,
        competition_name: str,
        season_year: int,
    ):
        self.session = session
        self.name = competition_name
        self.season = season_year
        self.match_sim = (
            AdvancedMatchEngine() if USE_ADVANCED_ENGINE else MatchSimulator()
        )
        self.batch_sim = BatchMatchSimulator()

    # ── Qualification / seeding ───────────────────────────────────────────

    def _get_qualified_clubs(self) -> list[Club]:
        """Determine qualified clubs based on previous-season league standings.

        Falls back to reputation if no standings exist (first season).
        """
        if self.name == "Champions League":
            slots = CL_SLOTS
        elif self.name == "Europa League":
            slots = EL_EXTRA_PLACES
        else:
            slots = ECL_EXTRA_PLACES

        qualified: list[Club] = []
        used_club_ids: set[int] = set()

        # If EL or ECL, exclude clubs already in higher-tier competitions.
        cl_ids: set[int] = set()
        el_ids: set[int] = set()
        if self.name in ("Europa League", "Conference League"):
            cl_ids = self._ids_already_in("Champions League")
        if self.name == "Conference League":
            el_ids = self._ids_already_in("Europa League")

        exclude_ids = cl_ids | el_ids

        for country, n_spots in slots.items():
            league = (
                self.session.query(League)
                .filter_by(country=country, tier=1)
                .first()
            )
            if not league:
                continue

            # Try standings from previous season first.
            prev_season = self.season - 1
            standings = (
                self.session.query(LeagueStanding)
                .filter_by(league_id=league.id, season=prev_season)
                .order_by(
                    LeagueStanding.points.desc(),
                    LeagueStanding.goal_difference.desc(),
                )
                .all()
            )

            if standings:
                if self.name == "Champions League":
                    start = 0
                elif self.name == "Europa League":
                    start = CL_SLOTS.get(country, 0)
                else:
                    start = (
                        CL_SLOTS.get(country, 0)
                        + EL_EXTRA_PLACES.get(country, 0)
                    )

                picked = 0
                for st in standings[start:]:
                    if picked >= n_spots:
                        break
                    if st.club_id in exclude_ids or st.club_id in used_club_ids:
                        continue
                    club = self.session.get(Club, st.club_id)
                    if club:
                        qualified.append(club)
                        used_club_ids.add(club.id)
                        picked += 1
            else:
                # Fallback: use reputation ordering.
                clubs = (
                    self.session.query(Club)
                    .filter_by(league_id=league.id)
                    .order_by(Club.reputation.desc())
                    .all()
                )
                if self.name == "Champions League":
                    start = 0
                elif self.name == "Europa League":
                    start = CL_SLOTS.get(country, 0)
                else:
                    start = (
                        CL_SLOTS.get(country, 0)
                        + EL_EXTRA_PLACES.get(country, 0)
                    )

                picked = 0
                for c in clubs[start:]:
                    if picked >= n_spots:
                        break
                    if c.id in exclude_ids or c.id in used_club_ids:
                        continue
                    qualified.append(c)
                    used_club_ids.add(c.id)
                    picked += 1

        # For EL: also add domestic cup winners not already qualified.
        if self.name == "Europa League":
            cup_winners = self._get_domestic_cup_winners()
            for cw in cup_winners:
                if cw.id not in used_club_ids and cw.id not in exclude_ids:
                    qualified.append(cw)
                    used_club_ids.add(cw.id)

        return qualified

    def _ids_already_in(self, competition_name: str) -> set[int]:
        """Return club IDs already drawn into *competition_name* this season."""
        rows = (
            self.session.query(ContinentalGroup.club_id)
            .filter_by(competition_name=competition_name, season=self.season)
            .all()
        )
        return {r[0] for r in rows}

    def _get_domestic_cup_winners(self) -> list[Club]:
        """Return last season's domestic cup winners (if data exists)."""
        winners: list[Club] = []
        prev_season = self.season - 1
        cup_names = (
            self.session.query(CupFixture.cup_name)
            .filter_by(season=prev_season, played=True)
            .distinct()
            .all()
        )
        for (cup_name,) in cup_names:
            final = (
                self.session.query(CupFixture)
                .filter_by(
                    cup_name=cup_name, season=prev_season, played=True
                )
                .order_by(CupFixture.round_number.desc())
                .first()
            )
            if final and final.winner_club_id:
                club = self.session.get(Club, final.winner_club_id)
                if club:
                    winners.append(club)
        return winners

    # ── Group draw ────────────────────────────────────────────────────────

    def initialize_competition(self) -> bool:
        """Seed teams, create groups and group-stage fixtures.

        Returns True if competition was initialised, False if already done
        or not enough teams.
        """
        existing = (
            self.session.query(ContinentalGroup)
            .filter_by(competition_name=self.name, season=self.season)
            .count()
        )
        if existing > 0:
            return False  # already initialised

        clubs = self._get_qualified_clubs()
        if len(clubs) < 32:
            # Pad with highest-reputation clubs not yet in any competition.
            already = {c.id for c in clubs}
            all_continental = set()
            for comp_name in ("Champions League", "Europa League",
                              "Conference League"):
                all_continental |= self._ids_already_in(comp_name)
            already |= all_continental

            fillers = (
                self.session.query(Club)
                .filter(Club.league_id.isnot(None))
                .order_by(Club.reputation.desc())
                .all()
            )
            for f in fillers:
                if f.id not in already:
                    clubs.append(f)
                    already.add(f.id)
                if len(clubs) >= 32:
                    break

        if len(clubs) < 32:
            return False

        clubs = clubs[:32]
        groups = self.draw_groups(clubs)
        self._create_group_fixtures(groups)

        self.session.add(NewsItem(
            season=self.season,
            headline=f"{self.name} group stage draw!",
            body=self._format_draw_news(groups),
            category="continental",
        ))
        self.session.flush()
        return True

    def draw_groups(self, clubs: list[Club]) -> dict[str, list[Club]]:
        """Pot-based draw into 8 groups of 4.

        Pot 1 = clubs 1-8 by reputation, Pot 2 = 9-16, etc.
        No two clubs from the same country in one group.
        """
        clubs_sorted = sorted(
            clubs, key=lambda c: c.reputation or 0, reverse=True
        )
        pots = [clubs_sorted[i * 8:(i + 1) * 8] for i in range(4)]
        for pot in pots:
            random.shuffle(pot)

        group_letters = list("ABCDEFGH")
        groups: dict[str, list[Club]] = {g: [] for g in group_letters}

        # Place pot 1 first (one per group).
        for i, club in enumerate(pots[0]):
            groups[group_letters[i]].append(club)

        # Place remaining pots with country constraint.
        for pot in pots[1:]:
            remaining = list(pot)
            random.shuffle(remaining)

            for club in remaining:
                placed = False
                order = list(group_letters)
                random.shuffle(order)
                for g in order:
                    if len(groups[g]) >= 4:
                        continue
                    countries_in_group = {
                        self._club_country(c) for c in groups[g]
                    }
                    if self._club_country(club) in countries_in_group:
                        continue
                    groups[g].append(club)
                    placed = True
                    break

                if not placed:
                    # Fallback: ignore country constraint.
                    for g in group_letters:
                        if len(groups[g]) < 4:
                            groups[g].append(club)
                            break

        # Persist group standings.
        for g_letter, g_clubs in groups.items():
            for pot_idx, club in enumerate(g_clubs, start=1):
                self.session.add(ContinentalGroup(
                    competition_name=self.name,
                    season=self.season,
                    group_letter=g_letter,
                    club_id=club.id,
                    pot=pot_idx,
                ))

        self.session.flush()
        return groups

    def _club_country(self, club: Club) -> str:
        if club.league_id:
            league = self.session.get(League, club.league_id)
            if league:
                return league.country
        return ""

    def _create_group_fixtures(self, groups: dict[str, list[Club]]):
        """Create 6 matchdays of group-stage fixtures (home & away
        round-robin for 4 teams = 12 fixtures per group, 2 per matchday).
        """
        schedule = self._get_matchday_schedule()
        group_mds = sorted(
            md for md, tag in schedule.items() if tag.startswith("group_md")
        )

        for g_letter, g_clubs in groups.items():
            if len(g_clubs) != 4:
                continue

            pairings = _round_robin_4(g_clubs)

            for i, (home, away) in enumerate(pairings):
                # Map fixture index to matchday: every 2 fixtures share a
                # matchday (since there are 2 matches per group per MD).
                md_idx = i // 2
                md_idx = min(md_idx, len(group_mds) - 1)
                self.session.add(ContinentalFixture(
                    competition_name=self.name,
                    season=self.season,
                    stage="group",
                    group_letter=g_letter,
                    leg=1,
                    matchday=group_mds[md_idx],
                    home_club_id=home.id,
                    away_club_id=away.id,
                ))

        self.session.flush()

    def _get_matchday_schedule(self) -> dict[int, str]:
        if self.name == "Champions League":
            return CL_MATCHDAY_SCHEDULE
        elif self.name == "Europa League":
            return EL_MATCHDAY_SCHEDULE
        else:
            return ECL_MATCHDAY_SCHEDULE

    def _format_draw_news(self, groups: dict[str, list[Club]]) -> str:
        lines = []
        for g, clubs in sorted(groups.items()):
            names = ", ".join(c.name for c in clubs)
            lines.append(f"Group {g}: {names}")
        return "\n".join(lines)

    # ── Advancing rounds ──────────────────────────────────────────────────

    def advance_round(
        self, matchday: int, human_club_id: int | None = None
    ) -> dict | None:
        """Play the continental fixtures scheduled for *matchday*.

        Returns a results dict, or None if nothing to play.
        """
        schedule = self._get_matchday_schedule()
        tag = schedule.get(matchday)
        if tag is None:
            return None

        fixtures = (
            self.session.query(ContinentalFixture)
            .filter_by(
                competition_name=self.name,
                season=self.season,
                matchday=matchday,
                played=False,
            )
            .all()
        )
        if not fixtures:
            return None

        human_fixture: Optional[ContinentalFixture] = None
        batch_fixtures: list[ContinentalFixture] = []

        for f in fixtures:
            if human_club_id and (
                f.home_club_id == human_club_id
                or f.away_club_id == human_club_id
            ):
                human_fixture = f
            else:
                batch_fixtures.append(f)

        results: list[dict] = []

        # Batch sim for AI matches.
        if batch_fixtures:
            self._batch_simulate(batch_fixtures)
            for f in batch_fixtures:
                results.append(self._fixture_result_dict(f))

        # Full sim for human match.
        human_result = None
        if human_fixture:
            human_result = self._simulate_full_match(human_fixture)
            results.append(self._fixture_result_dict(human_fixture))

        # Post-round processing.
        if tag.startswith("group_md"):
            self._update_group_standings_batch(fixtures)
            md_num = int(tag.replace("group_md", ""))
            if md_num == 6:
                self._process_group_stage_end()

        if tag == "r16_leg2":
            self._process_knockout_leg2("r16", "qf")
        elif tag == "qf_leg2":
            self._process_knockout_leg2("qf", "sf")
        elif tag == "sf_leg2":
            self._process_knockout_leg2("sf", "final")
        elif tag == "final":
            self._process_final()

        self.session.flush()

        stage = tag.split("_")[0] if "_" in tag else tag
        stage_display = STAGE_DISPLAY_NAMES.get(stage, tag)

        return {
            "competition": self.name,
            "round": stage_display,
            "tag": tag,
            "results": results,
            "human_result": human_result,
        }

    # ── Group standings ───────────────────────────────────────────────────

    def get_standings(self) -> dict[str, list[dict]]:
        """Return group standings keyed by group letter."""
        groups_db = (
            self.session.query(ContinentalGroup)
            .filter_by(competition_name=self.name, season=self.season)
            .order_by(
                ContinentalGroup.group_letter,
                ContinentalGroup.points.desc(),
                ContinentalGroup.gd.desc(),
                ContinentalGroup.gf.desc(),
            )
            .all()
        )
        out: dict[str, list[dict]] = {}
        for g in groups_db:
            club = self.session.get(Club, g.club_id)
            entry = {
                "club_id": g.club_id,
                "club_name": club.name if club else "?",
                "played": g.played,
                "won": g.won,
                "drawn": g.drawn,
                "lost": g.lost,
                "gf": g.gf,
                "ga": g.ga,
                "gd": g.gd,
                "points": g.points,
            }
            out.setdefault(g.group_letter, []).append(entry)
        return out

    def _update_group_standings_batch(
        self, fixtures: list[ContinentalFixture]
    ):
        """Update group standings from a batch of just-played fixtures."""
        for f in fixtures:
            if f.stage != "group" or not f.played:
                continue
            hg = f.home_goals or 0
            ag = f.away_goals or 0

            home_g = self._get_group_row(f.group_letter, f.home_club_id)
            away_g = self._get_group_row(f.group_letter, f.away_club_id)
            if not home_g or not away_g:
                continue

            home_g.played += 1
            away_g.played += 1
            home_g.gf += hg
            home_g.ga += ag
            away_g.gf += ag
            away_g.ga += hg

            if hg > ag:
                home_g.won += 1
                home_g.points += 3
                away_g.lost += 1
            elif hg < ag:
                away_g.won += 1
                away_g.points += 3
                home_g.lost += 1
            else:
                home_g.drawn += 1
                away_g.drawn += 1
                home_g.points += 1
                away_g.points += 1

            home_g.gd = home_g.gf - home_g.ga
            away_g.gd = away_g.gf - away_g.ga

    def _get_group_row(
        self, group_letter: str | None, club_id: int
    ) -> ContinentalGroup | None:
        if not group_letter:
            return None
        return (
            self.session.query(ContinentalGroup)
            .filter_by(
                competition_name=self.name,
                season=self.season,
                group_letter=group_letter,
                club_id=club_id,
            )
            .first()
        )

    # ── Group -> knockout transition ─────────────────────────────────────

    def _process_group_stage_end(self):
        """Create R16 fixtures from group results: 1st vs 2nd cross-group."""
        group_winners: list[int] = []
        group_runners: list[int] = []

        for letter in "ABCDEFGH":
            rows = (
                self.session.query(ContinentalGroup)
                .filter_by(
                    competition_name=self.name,
                    season=self.season,
                    group_letter=letter,
                )
                .order_by(
                    ContinentalGroup.points.desc(),
                    ContinentalGroup.gd.desc(),
                    ContinentalGroup.gf.desc(),
                )
                .all()
            )
            if len(rows) >= 2:
                group_winners.append(rows[0].club_id)
                group_runners.append(rows[1].club_id)

                # Award prize money for group participation.
                prize = PRIZE_MONEY.get(self.name, {}).get("group", 0)
                for r in rows:
                    club = self.session.get(Club, r.club_id)
                    if club:
                        club.budget = (club.budget or 0) + prize

        if len(group_winners) != 8 or len(group_runners) != 8:
            return

        r16_pairs = self._draw_knockout_pairs(group_winners, group_runners)

        schedule = self._get_matchday_schedule()
        leg1_md = next(
            (md for md, t in schedule.items() if t == "r16_leg1"), None
        )
        leg2_md = next(
            (md for md, t in schedule.items() if t == "r16_leg2"), None
        )
        if leg1_md is None or leg2_md is None:
            return

        for winner_id, runner_id in r16_pairs:
            # Leg 1: runner-up at home.
            self.session.add(ContinentalFixture(
                competition_name=self.name,
                season=self.season,
                stage="r16",
                leg=1,
                matchday=leg1_md,
                home_club_id=runner_id,
                away_club_id=winner_id,
            ))
            # Leg 2: group winner at home.
            self.session.add(ContinentalFixture(
                competition_name=self.name,
                season=self.season,
                stage="r16",
                leg=2,
                matchday=leg2_md,
                home_club_id=winner_id,
                away_club_id=runner_id,
            ))

        self.session.flush()

        self.session.add(NewsItem(
            season=self.season,
            headline=f"{self.name} Round of 16 draw!",
            body=self._format_knockout_draw(r16_pairs, "Round of 16"),
            category="continental",
        ))

    def _draw_knockout_pairs(
        self,
        winners: list[int],
        runners: list[int],
    ) -> list[tuple[int, int]]:
        """Pair group winners with runners-up from different groups.

        Returns list of (winner_club_id, runner_up_club_id).
        """
        group_of: dict[int, str] = {}
        for row in (
            self.session.query(ContinentalGroup)
            .filter_by(competition_name=self.name, season=self.season)
            .all()
        ):
            group_of[row.club_id] = row.group_letter

        pairs: list[tuple[int, int]] = []
        used_runners: set[int] = set()
        shuffled_winners = list(winners)
        random.shuffle(shuffled_winners)

        for w in shuffled_winners:
            candidates = [
                r for r in runners
                if r not in used_runners
                and group_of.get(r) != group_of.get(w)
            ]
            if not candidates:
                candidates = [r for r in runners if r not in used_runners]
            if not candidates:
                continue
            chosen = random.choice(candidates)
            pairs.append((w, chosen))
            used_runners.add(chosen)

        return pairs

    def _format_knockout_draw(
        self, pairs: list[tuple[int, int]], round_name: str
    ) -> str:
        lines = [f"{self.name} {round_name}:"]
        for w_id, r_id in pairs:
            w = self.session.get(Club, w_id)
            r = self.session.get(Club, r_id)
            w_name = w.name if w else "?"
            r_name = r.name if r else "?"
            lines.append(f"  {r_name} vs {w_name}")
        return "\n".join(lines)

    # ── Knockout processing ──────────────────────────────────────────────

    def _process_knockout_leg2(self, stage: str, next_stage: str):
        """After leg 2, determine tie winners and create next-round fixtures.

        Uses away-goals rule, then extra time + penalties if still level.
        """
        leg1_fixtures = (
            self.session.query(ContinentalFixture)
            .filter_by(
                competition_name=self.name,
                season=self.season,
                stage=stage,
                leg=1,
                played=True,
            )
            .all()
        )
        leg2_fixtures = (
            self.session.query(ContinentalFixture)
            .filter_by(
                competition_name=self.name,
                season=self.season,
                stage=stage,
                leg=2,
                played=True,
            )
            .all()
        )

        # Build lookup: tie key = frozenset of two club IDs.
        leg1_lookup: dict[frozenset, ContinentalFixture] = {}
        for f in leg1_fixtures:
            key = frozenset([f.home_club_id, f.away_club_id])
            leg1_lookup[key] = f

        advancing: list[int] = []

        for f2 in leg2_fixtures:
            key = frozenset([f2.home_club_id, f2.away_club_id])
            f1 = leg1_lookup.get(key)
            if not f1:
                continue

            # team_a = leg1 home, team_b = leg1 away.
            team_a = f1.home_club_id
            team_b = f1.away_club_id

            a_goals_leg1 = f1.home_goals or 0
            b_goals_leg1 = f1.away_goals or 0

            if f2.home_club_id == team_b:
                b_goals_leg2 = f2.home_goals or 0
                a_goals_leg2 = f2.away_goals or 0
            else:
                a_goals_leg2 = f2.home_goals or 0
                b_goals_leg2 = f2.away_goals or 0

            agg_a = a_goals_leg1 + a_goals_leg2
            agg_b = b_goals_leg1 + b_goals_leg2

            # Store aggregate on the leg-2 fixture for reference.
            if f2.home_club_id == team_b:
                f2.aggregate_home = b_goals_leg1 + b_goals_leg2
                f2.aggregate_away = a_goals_leg1 + a_goals_leg2
            else:
                f2.aggregate_home = a_goals_leg1 + a_goals_leg2
                f2.aggregate_away = b_goals_leg1 + b_goals_leg2

            winner_id: int | None = None

            if agg_a > agg_b:
                winner_id = team_a
            elif agg_b > agg_a:
                winner_id = team_b
            else:
                # Away goals rule.
                a_away = a_goals_leg2  # team A's away goals (scored in leg 1 venue)
                b_away = b_goals_leg1  # team B's away goals (scored in leg 1 venue)
                if a_away > b_away:
                    winner_id = team_a
                elif b_away > a_away:
                    winner_id = team_b
                else:
                    winner_id = self._resolve_extra_time_penalties(
                        f2, team_a, team_b
                    )

            f2.winner_club_id = winner_id
            if winner_id:
                advancing.append(winner_id)

                prize = PRIZE_MONEY.get(self.name, {}).get(stage, 0)
                club = self.session.get(Club, winner_id)
                if club:
                    club.budget = (club.budget or 0) + prize

        # Create next-round fixtures.
        if next_stage == "final":
            self._create_final(advancing)
        else:
            self._create_next_knockout_fixtures(advancing, next_stage)

    def _resolve_extra_time_penalties(
        self,
        fixture: ContinentalFixture,
        team_a: int,
        team_b: int,
    ) -> int:
        """Resolve a tied knockout tie with extra time then penalties."""
        fixture.extra_time = True
        et_home = random.choice([0, 0, 0, 1, 1, 2])
        et_away = random.choice([0, 0, 0, 1, 1, 2])
        fixture.home_goals = (fixture.home_goals or 0) + et_home
        fixture.away_goals = (fixture.away_goals or 0) + et_away

        if et_home != et_away:
            return (
                fixture.home_club_id if et_home > et_away
                else fixture.away_club_id
            )

        # Penalties.
        fixture.penalties = True
        h_pens, a_pens = _simulate_penalty_shootout()
        fixture.penalty_home = h_pens
        fixture.penalty_away = a_pens
        return (
            fixture.home_club_id if h_pens > a_pens
            else fixture.away_club_id
        )

    def _create_next_knockout_fixtures(
        self, advancing: list[int], next_stage: str
    ):
        """Create two-leg fixtures for the next knockout round."""
        random.shuffle(advancing)
        schedule = self._get_matchday_schedule()

        leg1_tag = f"{next_stage}_leg1"
        leg2_tag = f"{next_stage}_leg2"
        leg1_md = next(
            (md for md, t in schedule.items() if t == leg1_tag), None
        )
        leg2_md = next(
            (md for md, t in schedule.items() if t == leg2_tag), None
        )

        if leg1_md is None or leg2_md is None:
            return

        for i in range(0, len(advancing) - 1, 2):
            a, b = advancing[i], advancing[i + 1]
            self.session.add(ContinentalFixture(
                competition_name=self.name,
                season=self.season,
                stage=next_stage,
                leg=1,
                matchday=leg1_md,
                home_club_id=a,
                away_club_id=b,
            ))
            self.session.add(ContinentalFixture(
                competition_name=self.name,
                season=self.season,
                stage=next_stage,
                leg=2,
                matchday=leg2_md,
                home_club_id=b,
                away_club_id=a,
            ))

        self.session.flush()

    def _create_final(self, advancing: list[int]):
        """Create a single-leg final at neutral venue."""
        if len(advancing) < 2:
            return

        schedule = self._get_matchday_schedule()
        final_md = next(
            (md for md, t in schedule.items() if t == "final"), None
        )
        if final_md is None:
            return

        a, b = advancing[0], advancing[1]
        self.session.add(ContinentalFixture(
            competition_name=self.name,
            season=self.season,
            stage="final",
            leg=1,
            matchday=final_md,
            home_club_id=a,
            away_club_id=b,
        ))
        self.session.flush()

    def _process_final(self):
        """Process the final: determine winner, award prizes."""
        final = (
            self.session.query(ContinentalFixture)
            .filter_by(
                competition_name=self.name,
                season=self.season,
                stage="final",
                played=True,
            )
            .first()
        )
        if not final:
            return

        hg = final.home_goals or 0
        ag = final.away_goals or 0

        if hg > ag:
            final.winner_club_id = final.home_club_id
        elif ag > hg:
            final.winner_club_id = final.away_club_id
        else:
            # Extra time + penalties.
            final.extra_time = True
            et_home = random.choice([0, 0, 0, 1, 1, 2])
            et_away = random.choice([0, 0, 0, 1, 1, 2])
            final.home_goals = hg + et_home
            final.away_goals = ag + et_away

            if final.home_goals != final.away_goals:
                final.winner_club_id = (
                    final.home_club_id
                    if final.home_goals > final.away_goals
                    else final.away_club_id
                )
            else:
                final.penalties = True
                h_pens, a_pens = _simulate_penalty_shootout()
                final.penalty_home = h_pens
                final.penalty_away = a_pens
                final.winner_club_id = (
                    final.home_club_id if h_pens > a_pens
                    else final.away_club_id
                )

        # Prize money.
        prizes = PRIZE_MONEY.get(self.name, {})
        winner_id = final.winner_club_id
        loser_id = (
            final.away_club_id
            if winner_id == final.home_club_id
            else final.home_club_id
        )

        winner_club = (
            self.session.get(Club, winner_id) if winner_id else None
        )
        loser_club = (
            self.session.get(Club, loser_id) if loser_id else None
        )

        if winner_club:
            winner_club.budget = (
                (winner_club.budget or 0) + prizes.get("winner", 0)
            )
        if loser_club:
            loser_club.budget = (
                (loser_club.budget or 0) + prizes.get("runner_up", 0)
            )

        # News.
        w_name = winner_club.name if winner_club else "?"
        l_name = loser_club.name if loser_club else "?"
        score = f"{final.home_goals}-{final.away_goals}"
        pens = ""
        if final.penalties:
            pens = f" ({final.penalty_home}-{final.penalty_away} pens)"
        et = " (a.e.t.)" if final.extra_time and not final.penalties else ""

        self.session.add(NewsItem(
            season=self.season,
            headline=f"{w_name} win the {self.name}!",
            body=(
                f"{w_name} defeated {l_name} {score}{et}{pens} in the "
                f"{self.name} Final to lift the trophy!"
            ),
            category="continental",
        ))

    # ── Match simulation ─────────────────────────────────────────────────

    def _batch_simulate(self, fixtures: list[ContinentalFixture]):
        """Batch-simulate a list of continental fixtures."""
        from fm.db.models import TacticalSetup

        season_obj = (
            self.session.query(Season).order_by(Season.year.desc()).first()
        )
        batch_inputs: list[BatchFixtureInput] = []

        for f in fixtures:
            home_club = self.session.get(Club, f.home_club_id)
            away_club = self.session.get(Club, f.away_club_id)

            h_players_db = (
                self.session.query(Player)
                .filter_by(club_id=f.home_club_id)
                .all()
            )
            a_players_db = (
                self.session.query(Player)
                .filter_by(club_id=f.away_club_id)
                .all()
            )

            h_xi, _ = _select_squad(h_players_db, "home")
            a_xi, _ = _select_squad(a_players_db, "away")

            h_tac_db = (
                self.session.query(TacticalSetup)
                .filter_by(club_id=f.home_club_id)
                .first()
            )
            a_tac_db = (
                self.session.query(TacticalSetup)
                .filter_by(club_id=f.away_club_id)
                .first()
            )

            h_tac = (
                TacticalContext.from_db(h_tac_db)
                if h_tac_db else TacticalContext()
            )
            a_tac = (
                TacticalContext.from_db(a_tac_db)
                if a_tac_db else TacticalContext()
            )

            ctx = build_match_context(
                self.session, home_club, away_club,
                home_tactics=h_tac, away_tactics=a_tac,
                season=season_obj,
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
                # Reduced home advantage for continental away legs.
                home_advantage=ctx.home_advantage * 0.7,
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

        if batch_inputs:
            batch_results = self.batch_sim.simulate_batch(batch_inputs)
            for br in batch_results:
                fix = next(f for f in fixtures if f.id == br.fixture_id)
                fix.home_goals = br.home_goals
                fix.away_goals = br.away_goals
                fix.played = True

    def _simulate_full_match(
        self, fixture: ContinentalFixture
    ) -> MatchResult:
        """Full detailed simulation for a human continental match."""
        from fm.db.models import TacticalSetup

        home_club = self.session.get(Club, fixture.home_club_id)
        away_club = self.session.get(Club, fixture.away_club_id)

        h_players_db = (
            self.session.query(Player)
            .filter_by(club_id=fixture.home_club_id)
            .all()
        )
        a_players_db = (
            self.session.query(Player)
            .filter_by(club_id=fixture.away_club_id)
            .all()
        )

        h_xi, h_subs = _select_squad(h_players_db, "home")
        a_xi, a_subs = _select_squad(a_players_db, "away")

        h_tac_db = (
            self.session.query(TacticalSetup)
            .filter_by(club_id=fixture.home_club_id)
            .first()
        )
        a_tac_db = (
            self.session.query(TacticalSetup)
            .filter_by(club_id=fixture.away_club_id)
            .first()
        )

        h_tac = (
            TacticalContext.from_db(h_tac_db)
            if h_tac_db else TacticalContext()
        )
        a_tac = (
            TacticalContext.from_db(a_tac_db)
            if a_tac_db else TacticalContext()
        )

        season_obj = (
            self.session.query(Season).order_by(Season.year.desc()).first()
        )
        match_context = build_match_context(
            self.session, home_club, away_club,
            home_tactics=h_tac, away_tactics=a_tac,
            season=season_obj,
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

        return result

    def _fixture_result_dict(self, f: ContinentalFixture) -> dict:
        """Build a display-friendly result dict for a continental fixture."""
        home_club = self.session.get(Club, f.home_club_id)
        away_club = self.session.get(Club, f.away_club_id)
        return {
            "fixture_id": f.id,
            "home": home_club.name if home_club else "?",
            "away": away_club.name if away_club else "?",
            "home_goals": f.home_goals,
            "away_goals": f.away_goals,
            "extra_time": f.extra_time,
            "penalties": f.penalties,
            "penalty_home": f.penalty_home,
            "penalty_away": f.penalty_away,
            "stage": f.stage,
            "group": f.group_letter,
            "leg": f.leg,
            "aggregate_home": f.aggregate_home,
            "aggregate_away": f.aggregate_away,
            "winner_id": f.winner_club_id,
        }


# ═══════════════════════════════════════════════════════════════════════════
#  ContinentalManager — orchestrates all three competitions
# ═══════════════════════════════════════════════════════════════════════════

class ContinentalManager:
    """Top-level manager for all UEFA continental competitions.

    Used by SeasonManager to initialise and advance continental rounds.
    """

    COMPETITIONS = ["Champions League", "Europa League", "Conference League"]

    def __init__(self, session: Session):
        self.session = session
        self._comps: dict[str, ContinentalCompetition] = {}
        self._initialized = False

    def initialize(self, season_year: int):
        """Initialise all three competitions for the season."""
        if self._initialized:
            return
        # Initialise in order so that CL clubs are excluded from EL, etc.
        for name in self.COMPETITIONS:
            comp = ContinentalCompetition(self.session, name, season_year)
            comp.initialize_competition()
            self._comps[name] = comp
        self._initialized = True

    def process_matchday(
        self, matchday: int, human_club_id: int | None = None
    ) -> list[dict]:
        """Process any continental fixtures scheduled for this matchday.

        Returns a list of result dicts (one per competition that played).
        """
        scheduled = _ALL_SCHEDULES.get(matchday, [])
        if not scheduled:
            return []

        results: list[dict] = []
        for comp_name, tag in scheduled:
            comp = self._comps.get(comp_name)
            if not comp:
                season = (
                    self.session.query(Season)
                    .order_by(Season.year.desc())
                    .first()
                )
                if season:
                    comp = ContinentalCompetition(
                        self.session, comp_name, season.year
                    )
                    self._comps[comp_name] = comp
            if comp:
                result = comp.advance_round(matchday, human_club_id)
                if result:
                    results.append(result)
        return results

    def get_standings(self, competition_name: str) -> dict[str, list[dict]]:
        """Return group standings for a specific competition."""
        comp = self._comps.get(competition_name)
        if comp:
            return comp.get_standings()
        return {}

    def is_club_in_competition(
        self, club_id: int, competition_name: str | None = None
    ) -> bool:
        """Check if a club is participating in any/specific competition."""
        query = self.session.query(ContinentalGroup).filter_by(
            club_id=club_id
        )
        if competition_name:
            query = query.filter_by(competition_name=competition_name)
        return query.count() > 0

    def get_club_competition(self, club_id: int) -> str | None:
        """Return the competition name a club is in, or None."""
        row = (
            self.session.query(ContinentalGroup.competition_name)
            .filter_by(club_id=club_id)
            .first()
        )
        return row[0] if row else None


# ═══════════════════════════════════════════════════════════════════════════
#  Helper functions
# ═══════════════════════════════════════════════════════════════════════════

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
        if (p.injured_weeks or 0) == 0
        and (p.suspended_matches or 0) == 0
    ]
    available.sort(key=lambda p: p.overall or 0, reverse=True)

    gks = [p for p in available if p.position == "GK"]
    outfield = [p for p in available if p.position != "GK"]

    xi: list[PlayerInMatch] = []
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

    for _ in range(5):
        if random.random() < 0.75:
            home_score += 1
        if random.random() < 0.75:
            away_score += 1

    while home_score == away_score:
        h_scored = random.random() < 0.70
        a_scored = random.random() < 0.70
        if h_scored:
            home_score += 1
        if a_scored:
            away_score += 1

    return home_score, away_score


def _round_robin_4(clubs: list[Club]) -> list[tuple[Club, Club]]:
    """Generate 12 fixtures (home & away) for a group of 4 teams.

    Produces 6 matchdays with 2 matches each, returned as a flat list of
    12 (home, away) pairs.  Pairs at indices (0,1), (2,3), ... share a
    matchday.
    """
    a, b, c, d = clubs[0], clubs[1], clubs[2], clubs[3]
    return [
        # MD 1
        (a, b), (c, d),
        # MD 2
        (a, c), (d, b),
        # MD 3
        (a, d), (b, c),
        # MD 4 (reverse of MD 1)
        (b, a), (d, c),
        # MD 5 (reverse of MD 2)
        (c, a), (b, d),
        # MD 6 (reverse of MD 3)
        (d, a), (c, b),
    ]
