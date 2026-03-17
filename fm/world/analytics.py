"""Match analytics, season analytics, player comparisons, and league stats.

Provides data-driven insights for the manager:
- MatchAnalytics: per-match player ratings, key moments, xG timeline
- SeasonAnalytics: form curves, performance trends, squad analysis
- PlayerComparison: radar chart data, head-to-head, similar players
- League stats leaders (top scorers, assisters, clean sheets, etc.)
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import func, desc, and_
from sqlalchemy.orm import Session as DBSession

from fm.db.models import (
    Player, Club, Fixture, MatchEvent, PlayerMatchStats,
    PlayerStats, LeagueStanding, League,
)


# ── Data classes ───────────────────────────────────────────────────────────


@dataclass
class PlayerRating:
    """Calculated match rating for a player."""
    player_id: int
    player_name: str
    position: str
    rating: float           # 1.0 - 10.0
    goals: int = 0
    assists: int = 0
    key_moments: list[str] = field(default_factory=list)


@dataclass
class MatchAnalyticsResult:
    """Full analytics breakdown for a single match."""
    fixture_id: int
    home_club: str
    away_club: str
    score: str
    home_xg: float
    away_xg: float
    home_possession: float
    home_ratings: list[PlayerRating] = field(default_factory=list)
    away_ratings: list[PlayerRating] = field(default_factory=list)
    home_motm: Optional[PlayerRating] = None
    away_motm: Optional[PlayerRating] = None
    xg_timeline: list[dict] = field(default_factory=list)
    key_moments: list[dict] = field(default_factory=list)


@dataclass
class FormPoint:
    """Single matchday form data point."""
    matchday: int
    result: str          # W, D, L
    goals_for: int
    goals_against: int
    points: int
    cumulative_points: int
    position: int


@dataclass
class SquadAnalysis:
    """Squad depth and balance analysis."""
    total_players: int
    avg_overall: float
    avg_age: float
    total_wage: float
    position_depth: dict[str, int] = field(default_factory=dict)
    position_avg_ovr: dict[str, float] = field(default_factory=dict)
    weakest_position: str = ""
    strongest_position: str = ""
    injury_count: int = 0
    avg_fitness: float = 0.0
    avg_morale: float = 0.0


@dataclass
class RadarChartData:
    """Radar/spider chart data for player comparison."""
    player_name: str
    categories: list[str] = field(default_factory=list)
    values: list[float] = field(default_factory=list)


@dataclass
class LeagueLeader:
    """A player in a league stats leader list."""
    player_id: int
    player_name: str
    club_name: str
    value: int         # goals, assists, etc.
    appearances: int


# ── Match Analytics ────────────────────────────────────────────────────────


class MatchAnalytics:
    """Analyze a played match: ratings, xG, key moments."""

    def __init__(self, session: DBSession):
        self.session = session

    def analyze_match(self, fixture_id: int) -> Optional[MatchAnalyticsResult]:
        """Generate full analytics for a played fixture."""
        fixture = self.session.get(Fixture, fixture_id)
        if not fixture or not fixture.played:
            return None

        home_club = self.session.get(Club, fixture.home_club_id)
        away_club = self.session.get(Club, fixture.away_club_id)

        result = MatchAnalyticsResult(
            fixture_id=fixture_id,
            home_club=home_club.name if home_club else "Unknown",
            away_club=away_club.name if away_club else "Unknown",
            score=f"{fixture.home_goals or 0}-{fixture.away_goals or 0}",
            home_xg=fixture.home_xg or 0.0,
            away_xg=fixture.away_xg or 0.0,
            home_possession=fixture.home_possession or 50.0,
        )

        # Player match stats
        pms_list = (
            self.session.query(PlayerMatchStats)
            .filter_by(fixture_id=fixture_id)
            .all()
        )

        for pms in pms_list:
            player = self.session.get(Player, pms.player_id)
            if not player:
                continue

            moments = self._get_player_key_moments(fixture_id, pms.player_id)

            pr = PlayerRating(
                player_id=pms.player_id,
                player_name=player.short_name or player.name,
                position=pms.position_played or player.position or "?",
                rating=round(pms.rating or 6.0, 1),
                goals=pms.goals or 0,
                assists=pms.assists or 0,
                key_moments=moments,
            )

            if player.club_id == fixture.home_club_id:
                result.home_ratings.append(pr)
            elif player.club_id == fixture.away_club_id:
                result.away_ratings.append(pr)

        # Sort by rating descending
        result.home_ratings.sort(key=lambda r: r.rating, reverse=True)
        result.away_ratings.sort(key=lambda r: r.rating, reverse=True)

        # Man of the match
        if result.home_ratings:
            result.home_motm = result.home_ratings[0]
        if result.away_ratings:
            result.away_motm = result.away_ratings[0]

        # Key moments from events
        result.key_moments = self._get_match_key_moments(fixture_id)

        # xG timeline
        result.xg_timeline = self._build_xg_timeline(fixture_id)

        return result

    def calculate_player_rating(
        self,
        player_id: int,
        fixture_id: int,
        events: list[MatchEvent] | None = None,
    ) -> float:
        """Calculate a 1-10 match rating for a player based on their events.

        Base rating: 6.0
        Modifiers:
        - Goal: +1.0
        - Assist: +0.5
        - Shot on target: +0.1
        - Tackle: +0.1
        - Interception: +0.1
        - Yellow card: -0.3
        - Red card: -1.5
        - Foul: -0.1
        - Own goal: -1.0
        - Save (GK): +0.3
        - Penalty scored: +0.7 (less than open play goal)
        """
        if events is None:
            events = (
                self.session.query(MatchEvent)
                .filter_by(fixture_id=fixture_id)
                .all()
            )

        rating = 6.0

        for ev in events:
            if ev.player_id == player_id:
                etype = ev.event_type
                if etype == "goal":
                    rating += 1.0
                elif etype == "shot_on_target":
                    rating += 0.1
                elif etype == "shot":
                    rating += 0.02
                elif etype == "tackle":
                    rating += 0.1
                elif etype == "interception":
                    rating += 0.1
                elif etype == "save":
                    rating += 0.3
                elif etype == "yellow_card":
                    rating -= 0.3
                elif etype == "red_card":
                    rating -= 1.5
                elif etype == "foul":
                    rating -= 0.1
                elif etype == "own_goal":
                    rating -= 1.0
                elif etype == "penalty":
                    # Penalty is recorded as scored
                    rating += 0.7
                elif etype == "corner":
                    rating += 0.02
                elif etype == "free_kick":
                    rating += 0.05

            if ev.assist_player_id == player_id:
                rating += 0.5

        return max(1.0, min(10.0, round(rating, 1)))

    def _get_player_key_moments(self, fixture_id: int, player_id: int) -> list[str]:
        """Get notable events for a player in a match."""
        events = (
            self.session.query(MatchEvent)
            .filter_by(fixture_id=fixture_id)
            .filter(
                (MatchEvent.player_id == player_id)
                | (MatchEvent.assist_player_id == player_id)
            )
            .order_by(MatchEvent.minute)
            .all()
        )

        moments = []
        for ev in events:
            if ev.event_type == "goal" and ev.player_id == player_id:
                moments.append(f"Goal ({ev.minute}')")
            elif ev.event_type == "goal" and ev.assist_player_id == player_id:
                moments.append(f"Assist ({ev.minute}')")
            elif ev.event_type == "yellow_card":
                moments.append(f"Yellow card ({ev.minute}')")
            elif ev.event_type == "red_card":
                moments.append(f"Red card ({ev.minute}')")
            elif ev.event_type == "penalty" and ev.player_id == player_id:
                moments.append(f"Penalty ({ev.minute}')")
            elif ev.event_type == "own_goal" and ev.player_id == player_id:
                moments.append(f"Own goal ({ev.minute}')")

        return moments

    def _get_match_key_moments(self, fixture_id: int) -> list[dict]:
        """Get all key moments in a match."""
        key_types = {"goal", "own_goal", "penalty", "red_card", "substitution"}
        events = (
            self.session.query(MatchEvent)
            .filter_by(fixture_id=fixture_id)
            .filter(MatchEvent.event_type.in_(key_types))
            .order_by(MatchEvent.minute)
            .all()
        )

        moments = []
        for ev in events:
            player = self.session.get(Player, ev.player_id) if ev.player_id else None
            pname = (player.short_name or player.name) if player else "Unknown"
            moments.append({
                "minute": ev.minute,
                "type": ev.event_type,
                "player": pname,
                "side": ev.team_side or "?",
                "description": ev.description or "",
            })
        return moments

    def _build_xg_timeline(self, fixture_id: int) -> list[dict]:
        """Build cumulative xG timeline from shot events."""
        shots = (
            self.session.query(MatchEvent)
            .filter_by(fixture_id=fixture_id)
            .filter(MatchEvent.event_type.in_(["shot", "shot_on_target", "goal"]))
            .order_by(MatchEvent.minute)
            .all()
        )

        home_xg = 0.0
        away_xg = 0.0
        timeline = [{"minute": 0, "home_xg": 0.0, "away_xg": 0.0}]

        for shot in shots:
            # Estimate xG per shot type
            if shot.event_type == "goal":
                xg_val = 0.35
            elif shot.event_type == "shot_on_target":
                xg_val = 0.15
            else:
                xg_val = 0.06

            if shot.team_side == "home":
                home_xg += xg_val
            else:
                away_xg += xg_val

            timeline.append({
                "minute": shot.minute,
                "home_xg": round(home_xg, 2),
                "away_xg": round(away_xg, 2),
            })

        return timeline


# ── Season Analytics ───────────────────────────────────────────────────────


class SeasonAnalytics:
    """Season-long analytics: form curves, trends, squad analysis."""

    def __init__(self, session: DBSession):
        self.session = session

    def get_form_curve(
        self, club_id: int, league_id: int, season: int,
    ) -> list[FormPoint]:
        """Calculate form data for every matchday played."""
        fixtures = (
            self.session.query(Fixture)
            .filter(
                Fixture.league_id == league_id,
                Fixture.season == season,
                Fixture.played == True,
                (Fixture.home_club_id == club_id) | (Fixture.away_club_id == club_id),
            )
            .order_by(Fixture.matchday)
            .all()
        )

        form_data = []
        cumulative_pts = 0

        for fix in fixtures:
            is_home = fix.home_club_id == club_id
            gf = (fix.home_goals or 0) if is_home else (fix.away_goals or 0)
            ga = (fix.away_goals or 0) if is_home else (fix.home_goals or 0)

            if gf > ga:
                result, pts = "W", 3
            elif gf == ga:
                result, pts = "D", 1
            else:
                result, pts = "L", 0

            cumulative_pts += pts

            # Position at this matchday (approximate from standings form)
            position = self._get_position_at_matchday(
                league_id, club_id, season, fix.matchday,
            )

            form_data.append(FormPoint(
                matchday=fix.matchday,
                result=result,
                goals_for=gf,
                goals_against=ga,
                points=pts,
                cumulative_points=cumulative_pts,
                position=position,
            ))

        return form_data

    def get_squad_analysis(self, club_id: int) -> SquadAnalysis:
        """Comprehensive squad analysis."""
        players = (
            self.session.query(Player)
            .filter_by(club_id=club_id)
            .all()
        )

        if not players:
            return SquadAnalysis(
                total_players=0, avg_overall=0.0, avg_age=0.0, total_wage=0.0,
            )

        overalls = [p.overall or 50 for p in players]
        ages = [p.age or 25 for p in players]
        wages = [p.wage or 0.0 for p in players]
        fitnesses = [p.fitness or 100.0 for p in players]
        morales = [p.morale or 65.0 for p in players]

        # Position depth
        pos_depth: dict[str, int] = {}
        pos_ovr_sum: dict[str, float] = {}
        for p in players:
            pos = p.position or "?"
            pos_depth[pos] = pos_depth.get(pos, 0) + 1
            pos_ovr_sum[pos] = pos_ovr_sum.get(pos, 0.0) + (p.overall or 50)

        pos_avg_ovr = {
            pos: round(pos_ovr_sum[pos] / pos_depth[pos], 1)
            for pos in pos_depth
        }

        weakest = min(pos_avg_ovr.items(), key=lambda x: x[1])[0] if pos_avg_ovr else ""
        strongest = max(pos_avg_ovr.items(), key=lambda x: x[1])[0] if pos_avg_ovr else ""

        injured = sum(1 for p in players if (p.injured_weeks or 0) > 0)

        return SquadAnalysis(
            total_players=len(players),
            avg_overall=round(sum(overalls) / len(overalls), 1),
            avg_age=round(sum(ages) / len(ages), 1),
            total_wage=round(sum(wages), 0),
            position_depth=pos_depth,
            position_avg_ovr=pos_avg_ovr,
            weakest_position=weakest,
            strongest_position=strongest,
            injury_count=injured,
            avg_fitness=round(sum(fitnesses) / len(fitnesses), 1),
            avg_morale=round(sum(morales) / len(morales), 1),
        )

    def get_performance_trends(
        self, club_id: int, league_id: int, season: int,
    ) -> dict:
        """Compute rolling averages for goals scored/conceded, possession, xG."""
        fixtures = (
            self.session.query(Fixture)
            .filter(
                Fixture.league_id == league_id,
                Fixture.season == season,
                Fixture.played == True,
                (Fixture.home_club_id == club_id) | (Fixture.away_club_id == club_id),
            )
            .order_by(Fixture.matchday)
            .all()
        )

        goals_for_list = []
        goals_against_list = []
        xg_for_list = []
        xg_against_list = []
        possession_list = []

        for fix in fixtures:
            is_home = fix.home_club_id == club_id
            gf = (fix.home_goals or 0) if is_home else (fix.away_goals or 0)
            ga = (fix.away_goals or 0) if is_home else (fix.home_goals or 0)
            xgf = (fix.home_xg or 0.0) if is_home else (fix.away_xg or 0.0)
            xga = (fix.away_xg or 0.0) if is_home else (fix.home_xg or 0.0)
            poss = (fix.home_possession or 50.0) if is_home else (100.0 - (fix.home_possession or 50.0))

            goals_for_list.append(gf)
            goals_against_list.append(ga)
            xg_for_list.append(xgf)
            xg_against_list.append(xga)
            possession_list.append(poss)

        window = 5

        def rolling_avg(data: list[float], w: int) -> list[float]:
            result = []
            for i in range(len(data)):
                start = max(0, i - w + 1)
                chunk = data[start:i + 1]
                result.append(round(sum(chunk) / len(chunk), 2))
            return result

        return {
            "matchdays": [f.matchday for f in fixtures],
            "goals_for": goals_for_list,
            "goals_against": goals_against_list,
            "goals_for_avg": rolling_avg([float(g) for g in goals_for_list], window),
            "goals_against_avg": rolling_avg([float(g) for g in goals_against_list], window),
            "xg_for": xg_for_list,
            "xg_against": xg_against_list,
            "xg_for_avg": rolling_avg(xg_for_list, window),
            "xg_against_avg": rolling_avg(xg_against_list, window),
            "possession": possession_list,
            "possession_avg": rolling_avg(possession_list, window),
        }

    def get_wage_efficiency(self, league_id: int, season: int) -> list[dict]:
        """Calculate points per million EUR wage for each club in a league."""
        standings = (
            self.session.query(LeagueStanding)
            .filter_by(league_id=league_id, season=season)
            .all()
        )

        results = []
        for s in standings:
            club = self.session.get(Club, s.club_id)
            if not club:
                continue
            total_wage = club.total_wages or 1.0
            weekly_to_annual = total_wage * 52.0 / 1_000_000.0  # in millions
            pts = s.points or 0
            efficiency = round(pts / max(weekly_to_annual, 0.01), 2)

            results.append({
                "club_id": club.id,
                "club_name": club.name,
                "points": pts,
                "annual_wage_m": round(weekly_to_annual, 2),
                "pts_per_million": efficiency,
            })

        results.sort(key=lambda x: x["pts_per_million"], reverse=True)
        return results

    def _get_position_at_matchday(
        self, league_id: int, club_id: int, season: int, matchday: int,
    ) -> int:
        """Approximate league position at a given matchday (from standings)."""
        standing = (
            self.session.query(LeagueStanding)
            .filter_by(league_id=league_id, club_id=club_id, season=season)
            .first()
        )
        if not standing:
            return 0

        # Count clubs with more points
        better = (
            self.session.query(LeagueStanding)
            .filter(
                LeagueStanding.league_id == league_id,
                LeagueStanding.season == season,
                LeagueStanding.points > standing.points,
            )
            .count()
        )
        return better + 1


# ── Player Comparison ──────────────────────────────────────────────────────


class PlayerComparison:
    """Compare players using radar charts and head-to-head stats."""

    def __init__(self, session: DBSession):
        self.session = session

    # Standard radar categories per position group
    _RADAR_CATEGORIES = {
        "outfield": [
            ("Pace", ["pace", "acceleration", "sprint_speed"]),
            ("Shooting", ["shooting", "finishing", "long_shots", "shot_power"]),
            ("Passing", ["passing", "vision", "short_passing", "long_passing"]),
            ("Dribbling", ["dribbling", "ball_control", "agility", "balance"]),
            ("Defending", ["defending", "marking", "standing_tackle", "interceptions"]),
            ("Physical", ["physical", "stamina", "strength", "jumping"]),
            ("Mental", ["composure", "reactions", "positioning"]),
        ],
        "gk": [
            ("Diving", ["gk_diving"]),
            ("Handling", ["gk_handling"]),
            ("Kicking", ["gk_kicking"]),
            ("Positioning", ["gk_positioning"]),
            ("Reflexes", ["gk_reflexes"]),
            ("Speed", ["gk_speed"]),
        ],
    }

    def get_radar_data(self, player_id: int) -> Optional[RadarChartData]:
        """Generate radar chart data for a player."""
        player = self.session.get(Player, player_id)
        if not player:
            return None

        pos_type = "gk" if player.position == "GK" else "outfield"
        categories = self._RADAR_CATEGORIES[pos_type]

        cat_names = []
        cat_values = []
        for cat_name, attrs in categories:
            vals = [getattr(player, a, 50) or 50 for a in attrs]
            avg = sum(vals) / len(vals) if vals else 50.0
            cat_names.append(cat_name)
            cat_values.append(round(avg, 1))

        return RadarChartData(
            player_name=player.short_name or player.name,
            categories=cat_names,
            values=cat_values,
        )

    def compare_players(
        self, player_a_id: int, player_b_id: int,
    ) -> Optional[dict]:
        """Head-to-head comparison of two players."""
        radar_a = self.get_radar_data(player_a_id)
        radar_b = self.get_radar_data(player_b_id)
        if not radar_a or not radar_b:
            return None

        pa = self.session.get(Player, player_a_id)
        pb = self.session.get(Player, player_b_id)

        # Per-category advantage
        advantages = []
        for i, cat in enumerate(radar_a.categories):
            va = radar_a.values[i]
            vb = radar_b.values[i] if i < len(radar_b.values) else 50.0
            diff = va - vb
            advantages.append({
                "category": cat,
                "player_a": va,
                "player_b": vb,
                "advantage": "A" if diff > 2 else ("B" if diff < -2 else "Even"),
            })

        return {
            "player_a": {
                "id": pa.id,
                "name": pa.short_name or pa.name,
                "position": pa.position,
                "age": pa.age,
                "overall": pa.overall,
                "radar": radar_a,
            },
            "player_b": {
                "id": pb.id,
                "name": pb.short_name or pb.name,
                "position": pb.position,
                "age": pb.age,
                "overall": pb.overall,
                "radar": radar_b,
            },
            "advantages": advantages,
        }

    def find_similar_players(
        self,
        player_id: int,
        max_results: int = 10,
    ) -> list[dict]:
        """Find players with similar attribute profiles.

        Uses Euclidean distance across radar categories.
        """
        source = self.get_radar_data(player_id)
        if not source:
            return []

        player = self.session.get(Player, player_id)
        if not player:
            return []

        # Get all players in similar position range
        pos = player.position or "CM"
        if pos == "GK":
            candidates = (
                self.session.query(Player)
                .filter(Player.position == "GK", Player.id != player_id)
                .all()
            )
        else:
            candidates = (
                self.session.query(Player)
                .filter(Player.position != "GK", Player.id != player_id)
                .all()
            )

        results = []
        for cand in candidates:
            cand_radar = self.get_radar_data(cand.id)
            if not cand_radar or len(cand_radar.values) != len(source.values):
                continue

            distance = math.sqrt(
                sum(
                    (a - b) ** 2
                    for a, b in zip(source.values, cand_radar.values)
                )
            )
            similarity = max(0.0, 100.0 - distance)

            results.append({
                "player_id": cand.id,
                "player_name": cand.short_name or cand.name,
                "position": cand.position,
                "age": cand.age,
                "overall": cand.overall,
                "similarity": round(similarity, 1),
            })

        results.sort(key=lambda x: x["similarity"], reverse=True)
        return results[:max_results]


# ── League Stats ───────────────────────────────────────────────────────────


class LeagueStats:
    """League-wide statistical leaders."""

    def __init__(self, session: DBSession):
        self.session = session

    def get_top_scorers(
        self, league_id: int, season: int, limit: int = 20,
    ) -> list[LeagueLeader]:
        """Top goal scorers in the league."""
        return self._get_leaders(league_id, season, "goals", limit)

    def get_top_assisters(
        self, league_id: int, season: int, limit: int = 20,
    ) -> list[LeagueLeader]:
        """Top assist providers in the league."""
        return self._get_leaders(league_id, season, "assists", limit)

    def get_top_rated(
        self, league_id: int, season: int, limit: int = 20,
    ) -> list[LeagueLeader]:
        """Highest average rated players (min 5 appearances)."""
        stats = (
            self.session.query(PlayerStats)
            .filter_by(season=season)
            .filter(PlayerStats.appearances >= 5)
            .order_by(desc(PlayerStats.avg_rating))
            .limit(limit * 2)
            .all()
        )

        leaders = []
        for s in stats:
            player = self.session.get(Player, s.player_id)
            if not player or not player.club_id:
                continue
            club = self.session.get(Club, player.club_id)
            if not club or club.league_id != league_id:
                continue

            leaders.append(LeagueLeader(
                player_id=player.id,
                player_name=player.short_name or player.name,
                club_name=club.short_name or club.name,
                value=int((s.avg_rating or 6.0) * 10),  # store as int * 10
                appearances=s.appearances or 0,
            ))
            if len(leaders) >= limit:
                break

        return leaders

    def get_clean_sheet_leaders(
        self, league_id: int, season: int, limit: int = 10,
    ) -> list[LeagueLeader]:
        """Top goalkeepers by clean sheets."""
        stats = (
            self.session.query(PlayerStats)
            .filter_by(season=season)
            .filter(PlayerStats.clean_sheets > 0)
            .order_by(desc(PlayerStats.clean_sheets))
            .limit(limit * 2)
            .all()
        )

        leaders = []
        for s in stats:
            player = self.session.get(Player, s.player_id)
            if not player or not player.club_id:
                continue
            if player.position != "GK":
                continue
            club = self.session.get(Club, player.club_id)
            if not club or club.league_id != league_id:
                continue

            leaders.append(LeagueLeader(
                player_id=player.id,
                player_name=player.short_name or player.name,
                club_name=club.short_name or club.name,
                value=s.clean_sheets or 0,
                appearances=s.appearances or 0,
            ))
            if len(leaders) >= limit:
                break

        return leaders

    def get_discipline_leaders(
        self, league_id: int, season: int, limit: int = 20,
    ) -> list[LeagueLeader]:
        """Most yellow/red cards (worst discipline)."""
        stats = (
            self.session.query(PlayerStats)
            .filter_by(season=season)
            .order_by(desc(PlayerStats.yellow_cards + PlayerStats.red_cards * 3))
            .limit(limit * 2)
            .all()
        )

        leaders = []
        for s in stats:
            player = self.session.get(Player, s.player_id)
            if not player or not player.club_id:
                continue
            club = self.session.get(Club, player.club_id)
            if not club or club.league_id != league_id:
                continue

            total_cards = (s.yellow_cards or 0) + (s.red_cards or 0) * 3
            if total_cards == 0:
                continue

            leaders.append(LeagueLeader(
                player_id=player.id,
                player_name=player.short_name or player.name,
                club_name=club.short_name or club.name,
                value=total_cards,
                appearances=s.appearances or 0,
            ))
            if len(leaders) >= limit:
                break

        return leaders

    def get_league_summary(self, league_id: int, season: int) -> dict:
        """Overall league stats summary."""
        fixtures = (
            self.session.query(Fixture)
            .filter_by(league_id=league_id, season=season, played=True)
            .all()
        )

        total_goals = 0
        total_matches = len(fixtures)
        home_wins = 0
        away_wins = 0
        draws = 0
        total_home_goals = 0
        total_away_goals = 0

        for f in fixtures:
            hg = f.home_goals or 0
            ag = f.away_goals or 0
            total_goals += hg + ag
            total_home_goals += hg
            total_away_goals += ag
            if hg > ag:
                home_wins += 1
            elif ag > hg:
                away_wins += 1
            else:
                draws += 1

        avg_goals = round(total_goals / max(total_matches, 1), 2)

        return {
            "total_matches": total_matches,
            "total_goals": total_goals,
            "avg_goals_per_match": avg_goals,
            "home_wins": home_wins,
            "away_wins": away_wins,
            "draws": draws,
            "home_win_pct": round(home_wins / max(total_matches, 1) * 100, 1),
            "away_win_pct": round(away_wins / max(total_matches, 1) * 100, 1),
            "draw_pct": round(draws / max(total_matches, 1) * 100, 1),
            "total_home_goals": total_home_goals,
            "total_away_goals": total_away_goals,
        }

    def _get_leaders(
        self, league_id: int, season: int, stat_name: str, limit: int,
    ) -> list[LeagueLeader]:
        """Generic leader query for a stat column."""
        col = getattr(PlayerStats, stat_name, None)
        if col is None:
            return []

        stats = (
            self.session.query(PlayerStats)
            .filter_by(season=season)
            .filter(col > 0)
            .order_by(desc(col))
            .limit(limit * 2)
            .all()
        )

        leaders = []
        for s in stats:
            player = self.session.get(Player, s.player_id)
            if not player or not player.club_id:
                continue
            club = self.session.get(Club, player.club_id)
            if not club or club.league_id != league_id:
                continue

            leaders.append(LeagueLeader(
                player_id=player.id,
                player_name=player.short_name or player.name,
                club_name=club.short_name or club.name,
                value=getattr(s, stat_name, 0) or 0,
                appearances=s.appearances or 0,
            ))
            if len(leaders) >= limit:
                break

        return leaders
