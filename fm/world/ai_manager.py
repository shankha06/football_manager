"""AI manager decision engine.

Handles squad selection, tactical adaptation, transfer activity, team talks,
and all weekly/matchday/seasonal decisions for non-human-controlled clubs.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy.orm import Session

from fm.db.models import (
    Club, Player, Manager, TacticalSetup, League,
    LeagueStanding, Fixture, Transfer, NewsItem, PlayerStats,
)
from fm.config import AI_STYLES, MENTALITY_LEVELS
from fm.engine.tactics import FORMATIONS


# ---------------------------------------------------------------------------
# Position utilities
# ---------------------------------------------------------------------------

# Canonical position groups used for squad-building logic
_DEFENDERS = {"CB", "LB", "RB", "LWB", "RWB"}
_MIDFIELDERS = {"CDM", "CM", "CAM", "LM", "RM"}
_WINGERS = {"LW", "RW", "LM", "RM"}
_FORWARDS = {"ST", "CF", "LW", "RW"}
_ATTACKERS = {"ST", "CF"}

# Formation → required position counts (defenders, midfielders, forwards)
_FORMATION_POS_NEEDS: dict[str, dict[str, int]] = {
    "4-4-2": {"GK": 1, "CB": 2, "LB": 1, "RB": 1, "CM": 2, "LM": 1, "RM": 1, "ST": 2},
    "4-3-3": {"GK": 1, "CB": 2, "LB": 1, "RB": 1, "CM": 3, "LW": 1, "ST": 1, "RW": 1},
    "4-2-3-1": {"GK": 1, "CB": 2, "LB": 1, "RB": 1, "CDM": 2, "CAM": 1, "LW": 1, "RW": 1, "ST": 1},
    "3-5-2": {"GK": 1, "CB": 3, "LWB": 1, "RWB": 1, "CM": 3, "ST": 2},
    "5-3-2": {"GK": 1, "CB": 3, "LWB": 1, "RWB": 1, "CM": 3, "ST": 2},
    "4-1-4-1": {"GK": 1, "CB": 2, "LB": 1, "RB": 1, "CDM": 1, "CM": 2, "LM": 1, "RM": 1, "ST": 1},
    "3-4-3": {"GK": 1, "CB": 3, "LM": 1, "CM": 2, "RM": 1, "LW": 1, "ST": 1, "RW": 1},
    "4-5-1": {"GK": 1, "CB": 2, "LB": 1, "RB": 1, "CM": 3, "LM": 1, "RM": 1, "ST": 1},
}

# Position compatibility: what positions can cover for another
_POS_COMPATIBILITY: dict[str, list[str]] = {
    "GK": [],
    "CB": ["CDM"],
    "LB": ["LWB", "LM"],
    "RB": ["RWB", "RM"],
    "LWB": ["LB", "LM"],
    "RWB": ["RB", "RM"],
    "CDM": ["CM", "CB"],
    "CM": ["CDM", "CAM"],
    "CAM": ["CM", "CF"],
    "LM": ["LW", "LB"],
    "RM": ["RW", "RB"],
    "LW": ["LM", "ST"],
    "RW": ["RM", "ST"],
    "CF": ["ST", "CAM"],
    "ST": ["CF", "LW", "RW"],
}

# Penalty for playing out of position
_OOP_PENALTY = 5  # overall points deducted for unfamiliar position


def _can_play(player: Player, target_pos: str) -> bool:
    """Check if a player can play a given position (primary or secondary)."""
    if player.position == target_pos:
        return True
    secondaries = (player.secondary_positions or "").split(",")
    secondaries = [s.strip() for s in secondaries if s.strip()]
    if target_pos in secondaries:
        return True
    # Check compatibility
    return target_pos in _POS_COMPATIBILITY.get(player.position, [])


def _effective_overall(player: Player, target_pos: str) -> float:
    """Estimate effective overall when played in target_pos."""
    base = player.overall or 50
    if player.position == target_pos:
        return base
    secondaries = (player.secondary_positions or "").split(",")
    secondaries = [s.strip() for s in secondaries if s.strip()]
    if target_pos in secondaries:
        return base - 2  # small penalty for secondary
    if target_pos in _POS_COMPATIBILITY.get(player.position, []):
        return base - _OOP_PENALTY
    return base - _OOP_PENALTY * 2  # very unfamiliar


def _player_score(player: Player, context: dict | None = None) -> float:
    """Score a player considering fitness, form, morale, and overall."""
    base = player.overall or 50
    fitness = player.fitness or 100.0
    form = player.form or 65.0
    morale = player.morale or 65.0

    # Fitness below 70 is a big penalty
    fitness_mod = 0.0
    if fitness < 70:
        fitness_mod = (70 - fitness) * -0.3
    elif fitness < 85:
        fitness_mod = (85 - fitness) * -0.1

    # Form bonus/penalty
    form_mod = (form - 65.0) * 0.1

    # Morale bonus/penalty
    morale_mod = (morale - 65.0) * 0.05

    score = base + fitness_mod + form_mod + morale_mod

    if context:
        # Match importance multiplier for big-match players
        importance = context.get("importance", 0.5)
        big_match = (player.big_match or 65) / 100.0
        if importance > 0.7:
            score += (big_match - 0.5) * 5

    return score


# ---------------------------------------------------------------------------
# AI Squad Selector
# ---------------------------------------------------------------------------

class AISquadSelector:
    """Intelligent squad selection considering many factors."""

    def __init__(self, session: Session):
        self.session = session

    def select_match_squad(
        self,
        club_id: int,
        opponent_id: int | None = None,
        fixture_type: str = "league",
    ) -> dict:
        """Return {"starting_xi": [player_ids], "subs": [player_ids],
                   "formation": str}.
        """
        club = self.session.get(Club, club_id)
        mgr = self.session.query(Manager).filter_by(club_id=club_id).first()
        setup = self.session.query(TacticalSetup).filter_by(
            club_id=club_id
        ).first()

        formation = (setup.formation if setup else None) or (
            mgr.preferred_formation if mgr else "4-4-2"
        )

        players = self.session.query(Player).filter_by(club_id=club_id).all()

        # Filter available players
        available = [
            p for p in players
            if (p.injured_weeks or 0) == 0
            and (p.suspended_matches or 0) == 0
        ]

        # Determine match importance (affects selection)
        importance = self._assess_importance(
            club_id, opponent_id, fixture_type
        )
        context = {"importance": importance}

        # Determine if we should rotate
        rotate = self._should_rotate(club_id, importance)

        # Fill formation slots
        pos_needs = _FORMATION_POS_NEEDS.get(
            formation, _FORMATION_POS_NEEDS["4-4-2"]
        )

        xi_ids = self._fill_formation(
            available, pos_needs, context, rotate, importance
        )
        selected_set = set(xi_ids)

        # Subs: pick best remaining, ensuring positional coverage
        remaining = [p for p in available if p.id not in selected_set]
        sub_ids = self._pick_subs(remaining, formation)

        return {
            "starting_xi": xi_ids,
            "subs": sub_ids,
            "formation": formation,
        }

    def _fill_formation(
        self,
        available: list[Player],
        pos_needs: dict[str, int],
        context: dict,
        rotate: bool,
        importance: float,
    ) -> list[int]:
        """Fill each position slot with the best available player."""
        selected: list[int] = []
        used_ids: set[int] = set()

        # Sort positions: GK first, then defenders, midfielders, forwards
        order = ["GK"] + sorted(
            [p for p in pos_needs if p != "GK"],
            key=lambda p: (
                0 if p in _DEFENDERS else 1 if p in _MIDFIELDERS else 2
            ),
        )

        for pos in order:
            count = pos_needs.get(pos, 0)
            for _ in range(count):
                best = self._find_best_for_position(
                    available, pos, used_ids, context, rotate, importance
                )
                if best:
                    selected.append(best.id)
                    used_ids.add(best.id)

        # If we couldn't fill all 11 slots, fill with best remaining
        remaining = [p for p in available if p.id not in used_ids]
        remaining.sort(key=lambda p: _player_score(p, context), reverse=True)
        while len(selected) < 11 and remaining:
            p = remaining.pop(0)
            selected.append(p.id)
            used_ids.add(p.id)

        return selected

    def _find_best_for_position(
        self,
        available: list[Player],
        position: str,
        used_ids: set[int],
        context: dict,
        rotate: bool,
        importance: float,
    ) -> Player | None:
        """Find the best available player for a given position."""
        candidates = []
        for p in available:
            if p.id in used_ids:
                continue
            if not _can_play(p, position):
                continue

            # Skip unfit players
            if (p.fitness or 100) < 60:
                continue

            score = _effective_overall(p, position)
            # Factor in dynamic state
            score += (((p.form or 65) - 65) * 0.1)
            score += (((p.morale or 65) - 65) * 0.05)

            # Fitness penalty
            fit = p.fitness or 100
            if fit < 75:
                score -= (75 - fit) * 0.2

            # Rotation: penalize players with low fitness in less
            # important games
            if rotate and fit < 90:
                score -= (90 - fit) * 0.15

            # Unhappy player wanting to leave gets a small penalty
            if (p.morale or 65) < 40:
                score -= 3

            # Youth development in easy games
            if importance < 0.3 and (p.age or 25) <= 21:
                score += 4  # give youngsters a chance

            candidates.append((score, p))

        if not candidates:
            return None

        # Add slight randomness to avoid perfectly deterministic selection
        candidates.sort(key=lambda x: x[0], reverse=True)

        # If rotating, randomly pick from top 3 instead of always top 1
        if rotate and len(candidates) >= 3:
            pick = random.choice(candidates[:3])
            return pick[1]

        return candidates[0][1]

    def _pick_subs(
        self, remaining: list[Player], formation: str,
    ) -> list[int]:
        """Select up to 7 substitutes with good positional coverage."""
        subs: list[int] = []
        used: set[int] = set()

        # Ensure at least 1 GK on the bench
        gks = [p for p in remaining if p.position == "GK"]
        if gks:
            gks.sort(key=lambda p: p.overall or 0, reverse=True)
            subs.append(gks[0].id)
            used.add(gks[0].id)

        # Ensure at least 1 defender, 1 midfielder, 1 attacker
        for group in [_DEFENDERS, _MIDFIELDERS, _ATTACKERS]:
            candidates = [
                p for p in remaining
                if p.position in group and p.id not in used
            ]
            if candidates:
                candidates.sort(
                    key=lambda p: p.overall or 0, reverse=True
                )
                subs.append(candidates[0].id)
                used.add(candidates[0].id)

        # Fill remaining sub slots with best available
        leftover = [
            p for p in remaining if p.id not in used
        ]
        leftover.sort(key=lambda p: p.overall or 0, reverse=True)
        for p in leftover:
            if len(subs) >= 7:
                break
            subs.append(p.id)

        return subs

    def _assess_importance(
        self,
        club_id: int,
        opponent_id: int | None,
        fixture_type: str,
    ) -> float:
        """Rate match importance 0.0 (dead rubber) to 1.0 (cup final)."""
        if fixture_type == "cup_final":
            return 1.0
        if fixture_type == "cup":
            return 0.75

        # League: importance depends on standings proximity
        club = self.session.get(Club, club_id)
        if not club or not club.league_id:
            return 0.5

        standing = (
            self.session.query(LeagueStanding)
            .filter_by(club_id=club_id, league_id=club.league_id)
            .first()
        )
        if not standing:
            return 0.5

        played = standing.played or 0
        if played < 5:
            return 0.5  # too early to judge

        # Late-season games are more important
        season_progress = min(played / 34.0, 1.0)
        base = 0.4 + season_progress * 0.3

        # Rivalry / proximity in table raises importance
        if opponent_id:
            opp_standing = (
                self.session.query(LeagueStanding)
                .filter_by(
                    club_id=opponent_id, league_id=club.league_id,
                )
                .first()
            )
            if opp_standing:
                pts_diff = abs(
                    (standing.points or 0) - (opp_standing.points or 0)
                )
                if pts_diff <= 6:
                    base += 0.15  # close battle

        return min(base, 1.0)

    def _should_rotate(self, club_id: int, importance: float) -> bool:
        """Decide whether to rotate the squad."""
        if importance >= 0.7:
            return False  # important match, play best XI

        # Check squad fitness — if many players are tired, rotate
        players = self.session.query(Player).filter_by(club_id=club_id).all()
        tired = sum(
            1 for p in players
            if (p.fitness or 100) < 85
            and (p.injured_weeks or 0) == 0
        )
        total_avail = sum(
            1 for p in players
            if (p.injured_weeks or 0) == 0
            and (p.suspended_matches or 0) == 0
        )
        if total_avail > 0 and tired / total_avail > 0.4:
            return True

        # Low importance games: rotate with some probability
        if importance < 0.4:
            return random.random() < 0.6

        return random.random() < 0.25


# ---------------------------------------------------------------------------
# AI Tactical Manager
# ---------------------------------------------------------------------------

class AITacticalManager:
    """AI tactical decision-making before and during matches.

    Key features:
    - Scouts opponent's recent tactical patterns from fixture history
    - Applies rock-paper-scissors counter-tactics
    - Evolves over time: teams that keep losing with one approach change
    - Manager style influences willingness to adapt
    """

    # Counter-tactic lookup: given opponent's dominant style, what counters it?
    _COUNTER_TACTICS = {
        # opponent_trait → our counter adjustments
        "high_press": {
            "passing_style": "direct",       # bypass their press
            "tempo": "fast",                  # quick transitions
            "defensive_line": "deep",         # don't get caught high
        },
        "possession": {
            "pressing": "high",               # press them off the ball
            "tempo": "fast",                  # don't let them settle
            "width": "narrow",                # compact to block passing lanes
            "defensive_line": "normal",
        },
        "direct": {
            "defensive_line": "deep",         # don't get caught behind
            "pressing": "standard",           # don't overcommit
            "mentality": "cautious",
        },
        "counter": {
            "tempo": "slow",                  # slow down, don't give them transitions
            "mentality": "cautious",          # don't overcommit forward
            "pressing": "standard",           # don't leave gaps
            "width": "narrow",                # compact shape
        },
        "wide_play": {
            "width": "wide",                  # match their width
            "defensive_line": "normal",
            "formation_hint": "4-4-2",        # flat back four covers flanks
        },
        "attacking": {
            "mentality": "cautious",          # absorb and counter
            "pressing": "standard",
            "defensive_line": "deep",
            "passing_style": "direct",        # exploit space behind
        },
        "deep_block": {
            "passing_style": "short",         # patience to break them down
            "tempo": "slow",
            "width": "wide",                  # stretch their block
            "mentality": "positive",
        },
    }

    def __init__(self, session: Session):
        self.session = session

    def scout_opponent_tactics(
        self, opponent_id: int, n_matches: int = 6,
    ) -> dict:
        """Analyze opponent's recent tactical patterns from fixture history.

        Returns dict of dominant tactical traits with confidence scores.
        """
        from fm.db.models import Fixture

        # Get last N played fixtures for this opponent
        fixtures = (
            self.session.query(Fixture)
            .filter(
                Fixture.played == True,
                (Fixture.home_club_id == opponent_id) |
                (Fixture.away_club_id == opponent_id),
            )
            .order_by(Fixture.matchday.desc())
            .limit(n_matches)
            .all()
        )

        if not fixtures:
            return {}

        # Collect tactical choices
        formations = []
        mentalities = []
        pressings = []
        tempos = []
        passing_styles = []
        widths = []
        def_lines = []

        for f in fixtures:
            if f.home_club_id == opponent_id:
                if f.home_formation:
                    formations.append(f.home_formation)
                if f.home_mentality:
                    mentalities.append(f.home_mentality)
                if f.home_pressing:
                    pressings.append(f.home_pressing)
                if f.home_tempo:
                    tempos.append(f.home_tempo)
                if f.home_passing_style:
                    passing_styles.append(f.home_passing_style)
                if f.home_width:
                    widths.append(f.home_width)
                if f.home_defensive_line:
                    def_lines.append(f.home_defensive_line)
            else:
                if f.away_formation:
                    formations.append(f.away_formation)
                if f.away_mentality:
                    mentalities.append(f.away_mentality)
                if f.away_pressing:
                    pressings.append(f.away_pressing)
                if f.away_tempo:
                    tempos.append(f.away_tempo)
                if f.away_passing_style:
                    passing_styles.append(f.away_passing_style)
                if f.away_width:
                    widths.append(f.away_width)
                if f.away_defensive_line:
                    def_lines.append(f.away_defensive_line)

        def _most_common(lst):
            if not lst:
                return None
            from collections import Counter
            return Counter(lst).most_common(1)[0][0]

        def _frequency(lst, value):
            if not lst:
                return 0.0
            return lst.count(value) / len(lst)

        # Derive dominant style tags
        dominant_traits = set()
        primary_formation = _most_common(formations)
        primary_pressing = _most_common(pressings)
        primary_passing = _most_common(passing_styles)
        primary_mentality = _most_common(mentalities)
        primary_tempo = _most_common(tempos)
        primary_width = _most_common(widths)
        primary_def_line = _most_common(def_lines)

        if primary_pressing in ("high", "very_high"):
            dominant_traits.add("high_press")
        if primary_passing in ("short", "very_short"):
            dominant_traits.add("possession")
        if primary_passing in ("direct", "very_direct"):
            dominant_traits.add("direct")
        if primary_mentality in ("attacking", "very_attacking"):
            dominant_traits.add("attacking")
        if primary_mentality in ("defensive", "very_defensive"):
            dominant_traits.add("deep_block")
        if primary_width in ("wide", "very_wide"):
            dominant_traits.add("wide_play")
        if primary_tempo in ("fast", "very_fast") and primary_mentality in (
            "cautious", "defensive", "very_defensive"
        ):
            dominant_traits.add("counter")

        return {
            "dominant_traits": dominant_traits,
            "formation": primary_formation,
            "mentality": primary_mentality,
            "pressing": primary_pressing,
            "tempo": primary_tempo,
            "passing_style": primary_passing,
            "width": primary_width,
            "defensive_line": primary_def_line,
            "n_matches_scouted": len(fixtures),
            # How predictable is this team? (consistency score)
            "predictability": (
                _frequency(formations, primary_formation) * 0.3
                + _frequency(mentalities, primary_mentality) * 0.2
                + _frequency(pressings, primary_pressing) * 0.2
                + _frequency(passing_styles, primary_passing) * 0.15
                + _frequency(widths, primary_width) * 0.15
            ) if fixtures else 0.0,
        }

    def _evaluate_own_tactical_performance(
        self, club_id: int, n_matches: int = 8,
    ) -> dict:
        """Check how our recent tactical choices have been performing.

        Returns dict with winning/losing formation-mentality combos.
        """
        from fm.db.models import Fixture

        fixtures = (
            self.session.query(Fixture)
            .filter(
                Fixture.played == True,
                (Fixture.home_club_id == club_id) |
                (Fixture.away_club_id == club_id),
            )
            .order_by(Fixture.matchday.desc())
            .limit(n_matches)
            .all()
        )

        results_by_formation = {}  # formation → [+1 win, 0 draw, -1 loss]
        results_by_mentality = {}

        for f in fixtures:
            is_home = f.home_club_id == club_id
            hg, ag = f.home_goals or 0, f.away_goals or 0
            result_val = (1 if hg > ag else (-1 if hg < ag else 0)) * (1 if is_home else -1)

            formation = f.home_formation if is_home else f.away_formation
            mentality = f.home_mentality if is_home else f.away_mentality

            if formation:
                results_by_formation.setdefault(formation, []).append(result_val)
            if mentality:
                results_by_mentality.setdefault(mentality, []).append(result_val)

        def _win_rate(results):
            if not results:
                return 0.5
            return sum(1 for r in results if r > 0) / len(results)

        return {
            "formation_performance": {
                f: {"win_rate": _win_rate(r), "n": len(r)}
                for f, r in results_by_formation.items()
            },
            "mentality_performance": {
                m: {"win_rate": _win_rate(r), "n": len(r)}
                for m, r in results_by_mentality.items()
            },
            "overall_recent_wins": sum(
                1 for f in fixtures
                for is_home in [f.home_club_id == club_id]
                if ((f.home_goals or 0) > (f.away_goals or 0)) == is_home
            ),
            "n_matches": len(fixtures),
        }

    def decide_pre_match_tactics(
        self,
        club_id: int,
        opponent_id: int,
    ) -> dict:
        """Analyze opponent's tactical patterns and set up to counter them.

        This is the core tactical adaptation engine. It:
        1. Scouts opponent's recent tactical patterns
        2. Evaluates own recent tactical performance
        3. Applies counter-tactics weighted by manager style
        4. Falls back to base style preferences if no data available

        Returns dict of tactical settings applied.
        """
        club = self.session.get(Club, club_id)
        opponent = self.session.get(Club, opponent_id)
        mgr = self.session.query(Manager).filter_by(club_id=club_id).first()
        setup = self.session.query(TacticalSetup).filter_by(
            club_id=club_id
        ).first()

        if not club or not opponent or not setup:
            return {}

        style = (mgr.tactical_style if mgr else "balanced") or "balanced"
        club_rep = club.reputation or 50
        opp_rep = opponent.reputation or 50
        strength_diff = club_rep - opp_rep

        # Analyze own squad strengths
        squad = self.session.query(Player).filter_by(club_id=club_id).all()
        squad_profile = self._analyze_squad(squad)

        # --- Scout the opponent ---
        opp_intel = self.scout_opponent_tactics(opponent_id)
        own_perf = self._evaluate_own_tactical_performance(club_id)

        # --- Base tactics from manager style (as before) ---
        formation = self._choose_formation(style, squad_profile, strength_diff)
        mentality = self._choose_mentality(style, strength_diff, club_id)
        pressing = self._choose_pressing(style, strength_diff)
        tempo = self._choose_tempo(style, squad_profile)
        passing_style = self._choose_passing(style, squad_profile)
        width = self._choose_width(style, squad_profile, formation)
        def_line = self._choose_def_line(style, strength_diff, squad_profile)

        # --- Apply counter-tactics based on scouting ---
        if opp_intel and opp_intel.get("dominant_traits"):
            predictability = opp_intel.get("predictability", 0.0)
            # More predictable opponents → stronger counter adjustments
            # Manager adaptability: pragmatic/balanced adapt more, others less
            adaptability = {
                "pragmatic": 0.9, "balanced": 0.7, "possession": 0.5,
                "attacking": 0.4, "defensive": 0.5, "counter_attack": 0.6,
            }.get(style, 0.5)
            counter_weight = predictability * adaptability

            for trait in opp_intel["dominant_traits"]:
                counters = self._COUNTER_TACTICS.get(trait, {})
                for tactic_key, counter_value in counters.items():
                    if tactic_key == "formation_hint":
                        # Only apply formation hint if counter_weight is high
                        # and squad can support it
                        if counter_weight > 0.5 and random.random() < counter_weight:
                            formation = counter_value
                        continue

                    # Apply counter with probability = counter_weight
                    if random.random() < counter_weight:
                        if tactic_key == "mentality":
                            mentality = counter_value
                        elif tactic_key == "pressing":
                            pressing = counter_value
                        elif tactic_key == "tempo":
                            tempo = counter_value
                        elif tactic_key == "passing_style":
                            passing_style = counter_value
                        elif tactic_key == "width":
                            width = counter_value
                        elif tactic_key == "defensive_line":
                            def_line = counter_value

        # --- Self-correction: if losing a lot with current approach, change ---
        if own_perf.get("n_matches", 0) >= 4:
            recent_win_rate = own_perf.get("overall_recent_wins", 0) / max(own_perf["n_matches"], 1)
            if recent_win_rate < 0.25:
                # Losing badly — shake things up
                # Try a different formation from what's been failing
                bad_formations = [
                    f for f, data in own_perf.get("formation_performance", {}).items()
                    if data["win_rate"] < 0.2 and data["n"] >= 2
                ]
                available = list(FORMATIONS.keys())
                good_options = [f for f in available if f not in bad_formations]
                if good_options:
                    formation = random.choice(good_options)

                # If attacking mentality has been failing, go more cautious
                bad_mentalities = [
                    m for m, data in own_perf.get("mentality_performance", {}).items()
                    if data["win_rate"] < 0.2 and data["n"] >= 2
                ]
                if mentality in bad_mentalities:
                    # Flip approach
                    if mentality in ("attacking", "very_attacking", "positive"):
                        mentality = "cautious"
                    elif mentality in ("defensive", "very_defensive"):
                        mentality = "positive"

        # --- Apply all decisions ---
        setup.formation = formation
        setup.mentality = mentality
        setup.pressing = pressing
        setup.tempo = tempo
        setup.passing_style = passing_style
        setup.width = width
        setup.defensive_line = def_line

        return {
            "formation": formation,
            "mentality": mentality,
            "pressing": pressing,
            "tempo": tempo,
            "passing_style": passing_style,
            "width": width,
            "defensive_line": def_line,
            "scouted_opponent": bool(opp_intel.get("dominant_traits")),
        }

    def decide_in_match_changes(
        self,
        score_diff: int,
        minute: int,
        our_players: list[dict],
        subs_remaining: int,
        current_mentality: str,
        our_red_cards: int = 0,
    ) -> list[dict]:
        """Return a list of tactical changes to make.

        Each change: {"type": "mentality"|"pressing"|..., "value": str}
        """
        changes = []

        if minute < 30:
            return changes  # too early for major changes

        # Half-time adjustments (around minute 45)
        if 43 <= minute <= 47:
            if score_diff < 0:
                # Losing at half-time: push forward
                changes.append(
                    {"type": "mentality", "value": "attacking"}
                )
                changes.append(
                    {"type": "pressing", "value": "high"}
                )
            elif score_diff >= 3:
                # Winning big: calm down
                changes.append(
                    {"type": "mentality", "value": "cautious"}
                )
                changes.append(
                    {"type": "pressing", "value": "standard"}
                )

        # Red card: drop deeper
        if our_red_cards > 0:
            if current_mentality in ("attacking", "very_attacking", "positive"):
                changes.append(
                    {"type": "mentality", "value": "balanced"}
                )

        # Late game adjustments
        if minute >= 75:
            if score_diff < 0:
                changes.append(
                    {"type": "mentality", "value": "very_attacking"}
                )
            elif score_diff == 1:
                # Protecting a slim lead
                changes.append(
                    {"type": "mentality", "value": "defensive"}
                )
                changes.append(
                    {"type": "tempo", "value": "slow"}
                )

        return changes

    def decide_substitutions(
        self,
        minute: int,
        score_diff: int,
        players_on_pitch: list[dict],
        subs_available: list[dict],
        subs_used: int,
        max_subs: int = 5,
    ) -> list[dict]:
        """Choose substitutions based on match state.

        players_on_pitch: [{"id": int, "position": str, "fitness": float,
                           "rating": float, "yellow": bool}]
        subs_available: [{"id": int, "position": str, "overall": int}]

        Returns: [{"off_id": int, "on_id": int, "reason": str}]
        """
        if subs_used >= max_subs or not subs_available:
            return []

        substitutions = []
        remaining_subs = max_subs - subs_used
        used_sub_ids = set()

        # Don't sub before 55' unless injury/red card
        if minute < 55:
            return []

        on_pitch = list(players_on_pitch)  # copy

        # 1. Replace most tired player (fitness < 50)
        tired = [
            p for p in on_pitch
            if (p.get("fitness", 100) < 50 and p.get("position") != "GK")
        ]
        tired.sort(key=lambda p: p.get("fitness", 100))

        for t in tired:
            if remaining_subs <= 0:
                break
            sub = self._find_replacement(
                t, subs_available, used_sub_ids
            )
            if sub:
                substitutions.append({
                    "off_id": t["id"],
                    "on_id": sub["id"],
                    "reason": "fatigue",
                })
                used_sub_ids.add(sub["id"])
                remaining_subs -= 1

        # 2. Player on yellow in physical battle: protect from red
        if remaining_subs > 0 and minute >= 60:
            yellow_risks = [
                p for p in on_pitch
                if p.get("yellow")
                and p.get("position") in _DEFENDERS | _MIDFIELDERS
                and p["id"] not in {s["off_id"] for s in substitutions}
            ]
            for yr in yellow_risks[:1]:  # at most 1 protective sub
                if remaining_subs <= 0:
                    break
                sub = self._find_replacement(
                    yr, subs_available, used_sub_ids
                )
                if sub:
                    substitutions.append({
                        "off_id": yr["id"],
                        "on_id": sub["id"],
                        "reason": "yellow_card_protection",
                    })
                    used_sub_ids.add(sub["id"])
                    remaining_subs -= 1

        # 3. Tactical subs based on score
        if remaining_subs > 0 and minute >= 65:
            already_off = {s["off_id"] for s in substitutions}
            if score_diff < 0:
                # Losing: bring on attackers
                defenders_on = [
                    p for p in on_pitch
                    if p.get("position") in _DEFENDERS
                    and p["id"] not in already_off
                    and p.get("position") != "CB"  # don't remove CBs
                ]
                atk_subs = [
                    s for s in subs_available
                    if s.get("position") in _FORWARDS | _WINGERS
                    and s["id"] not in used_sub_ids
                ]
                if defenders_on and atk_subs and remaining_subs > 0:
                    off = min(
                        defenders_on,
                        key=lambda p: p.get("rating", 6.0),
                    )
                    on = max(
                        atk_subs,
                        key=lambda s: s.get("overall", 50),
                    )
                    substitutions.append({
                        "off_id": off["id"],
                        "on_id": on["id"],
                        "reason": "chasing_game",
                    })
                    used_sub_ids.add(on["id"])
                    remaining_subs -= 1

            elif score_diff > 0 and minute >= 75:
                # Winning: bring on fresh defenders / holding midfielders
                attackers_on = [
                    p for p in on_pitch
                    if p.get("position") in _FORWARDS
                    and p["id"] not in already_off
                ]
                def_subs = [
                    s for s in subs_available
                    if s.get("position") in _DEFENDERS | {"CDM", "CM"}
                    and s["id"] not in used_sub_ids
                ]
                if attackers_on and def_subs and remaining_subs > 0:
                    off = min(
                        attackers_on,
                        key=lambda p: p.get("fitness", 100),
                    )
                    on = max(
                        def_subs, key=lambda s: s.get("overall", 50),
                    )
                    substitutions.append({
                        "off_id": off["id"],
                        "on_id": on["id"],
                        "reason": "protecting_lead",
                    })
                    used_sub_ids.add(on["id"])
                    remaining_subs -= 1

        # 4. Use remaining subs for freshness after 75'
        if remaining_subs > 0 and minute >= 78:
            already_off = {s["off_id"] for s in substitutions}
            on_pitch_avail = [
                p for p in on_pitch
                if p["id"] not in already_off
                and p.get("position") != "GK"
            ]
            on_pitch_avail.sort(key=lambda p: p.get("fitness", 100))

            for tired_p in on_pitch_avail:
                if remaining_subs <= 0:
                    break
                sub = self._find_replacement(
                    tired_p, subs_available, used_sub_ids
                )
                if sub:
                    substitutions.append({
                        "off_id": tired_p["id"],
                        "on_id": sub["id"],
                        "reason": "freshness",
                    })
                    used_sub_ids.add(sub["id"])
                    remaining_subs -= 1

        return substitutions

    def _find_replacement(
        self,
        player: dict,
        subs: list[dict],
        used_ids: set[int],
    ) -> dict | None:
        """Find the best replacement sub for a given player."""
        pos = player.get("position", "CM")
        candidates = [
            s for s in subs
            if s["id"] not in used_ids
        ]
        if not candidates:
            return None

        # Prefer same position, then compatible
        def score(s):
            if s.get("position") == pos:
                return s.get("overall", 50) + 10
            compat = _POS_COMPATIBILITY.get(pos, [])
            if s.get("position") in compat:
                return s.get("overall", 50) + 3
            return s.get("overall", 50) - 5

        candidates.sort(key=score, reverse=True)
        return candidates[0]

    # ── Tactical analysis helpers ──────────────────────────────────────────

    def _analyze_squad(self, players: list[Player]) -> dict:
        """Analyze squad characteristics for tactical decisions."""
        if not players:
            return {
                "avg_pace": 50, "avg_passing": 50, "avg_defending": 50,
                "avg_shooting": 50, "avg_physical": 50,
                "has_fast_forwards": False, "has_tall_defenders": False,
                "creative_midfield": False, "strong_wings": False,
            }

        avg = lambda attr: sum(
            getattr(p, attr, 50) or 50 for p in players
        ) / max(len(players), 1)

        forwards = [p for p in players if p.position in _FORWARDS]
        defenders = [p for p in players if p.position in _DEFENDERS]
        midfielders = [p for p in players if p.position in _MIDFIELDERS]
        wingers = [p for p in players if p.position in _WINGERS]

        fast_fwds = any(
            (p.pace or 50) >= 80 for p in forwards
        ) if forwards else False

        tall_defs = any(
            (p.heading_accuracy or 50) >= 75 and (p.jumping or 50) >= 75
            for p in defenders
        ) if defenders else False

        creative = (
            sum((p.vision or 50) for p in midfielders) / max(len(midfielders), 1)
        ) >= 70 if midfielders else False

        strong_wings = len(wingers) >= 3 and (
            sum((p.crossing or 50) for p in wingers) / max(len(wingers), 1)
        ) >= 70 if wingers else False

        return {
            "avg_pace": avg("pace"),
            "avg_passing": avg("passing"),
            "avg_defending": avg("defending"),
            "avg_shooting": avg("shooting"),
            "avg_physical": avg("physical"),
            "has_fast_forwards": fast_fwds,
            "has_tall_defenders": tall_defs,
            "creative_midfield": creative,
            "strong_wings": strong_wings,
        }

    def _choose_formation(
        self,
        style: str,
        profile: dict,
        strength_diff: float,
    ) -> str:
        """Pick a formation matching the manager style and squad profile."""
        if style == "attacking":
            if profile.get("strong_wings"):
                return random.choice(["4-3-3", "3-4-3"])
            return random.choice(["4-3-3", "4-2-3-1"])
        elif style == "defensive":
            if strength_diff < -10:
                return random.choice(["5-3-2", "4-5-1"])
            return random.choice(["4-1-4-1", "4-5-1"])
        elif style == "counter_attack":
            if profile.get("has_fast_forwards"):
                return random.choice(["4-4-2", "4-2-3-1"])
            return "4-1-4-1"
        elif style == "possession":
            if profile.get("creative_midfield"):
                return random.choice(["4-3-3", "4-2-3-1"])
            return random.choice(["4-3-3", "4-1-4-1"])
        else:
            # Balanced / pragmatic
            if strength_diff > 15:
                return random.choice(["4-3-3", "4-2-3-1"])
            elif strength_diff < -15:
                return random.choice(["4-5-1", "4-1-4-1", "5-3-2"])
            return random.choice(["4-4-2", "4-2-3-1", "4-3-3"])

    def _choose_mentality(
        self, style: str, strength_diff: float, club_id: int,
    ) -> str:
        """Choose mentality based on style, opponent, and league position."""
        # Check league position for relegation/title context
        standing = (
            self.session.query(LeagueStanding)
            .filter_by(club_id=club_id)
            .first()
        )
        in_danger = False
        in_title_race = False
        if standing and (standing.played or 0) > 10:
            all_st = (
                self.session.query(LeagueStanding)
                .filter_by(league_id=standing.league_id, season=standing.season)
                .order_by(LeagueStanding.points.desc())
                .all()
            )
            n = len(all_st)
            for i, s in enumerate(all_st):
                if s.club_id == club_id:
                    if i >= n - 4:
                        in_danger = True
                    if i <= 2:
                        in_title_race = True
                    break

        if style == "attacking":
            if strength_diff > 10:
                return "attacking"
            if strength_diff > 0:
                return "positive"
            return "balanced"
        elif style == "defensive":
            if strength_diff < -10:
                return "very_defensive"
            if strength_diff < 0:
                return "defensive"
            return "cautious"
        elif style == "counter_attack":
            if strength_diff < 0:
                return "cautious"
            return "balanced"
        elif style == "possession":
            return "positive"
        else:
            # Balanced — adapt to context
            if in_danger:
                return "cautious" if strength_diff < 0 else "balanced"
            if in_title_race:
                return "positive" if strength_diff > 0 else "balanced"
            if strength_diff > 15:
                return "attacking"
            elif strength_diff < -15:
                return "defensive"
            return "balanced"

    def _choose_pressing(self, style: str, strength_diff: float) -> str:
        if style in ("attacking", "possession"):
            return "high" if strength_diff >= -5 else "standard"
        elif style == "defensive":
            return "low" if strength_diff < -10 else "standard"
        elif style == "counter_attack":
            return "high" if strength_diff < 0 else "standard"
        else:
            if strength_diff > 10:
                return "high"
            elif strength_diff < -10:
                return "low"
            return "standard"

    def _choose_tempo(self, style: str, profile: dict) -> str:
        if style == "counter_attack":
            return "fast"
        elif style == "possession":
            return "slow"
        elif style == "attacking":
            return "fast" if profile.get("has_fast_forwards") else "normal"
        elif style == "defensive":
            return "slow"
        return "normal"

    def _choose_passing(self, style: str, profile: dict) -> str:
        if style == "possession":
            return "short"
        elif style == "counter_attack":
            return "direct"
        elif style == "attacking":
            return "mixed" if profile.get("creative_midfield") else "direct"
        elif style == "defensive":
            return "direct"
        return "mixed"

    def _choose_width(
        self, style: str, profile: dict, formation: str,
    ) -> str:
        if profile.get("strong_wings"):
            return "wide"
        if formation in ("3-4-3", "3-5-2"):
            return "wide"
        if style == "defensive":
            return "narrow"
        return "normal"

    def _choose_def_line(
        self, style: str, strength_diff: float, profile: dict,
    ) -> str:
        if style in ("attacking", "possession"):
            return "high"
        elif style == "defensive":
            return "deep"
        elif style == "counter_attack":
            return "deep"
        else:
            if strength_diff > 10:
                return "high"
            elif strength_diff < -10:
                return "deep"
            return "normal"


# ---------------------------------------------------------------------------
# AI Transfer Manager
# ---------------------------------------------------------------------------

class AITransferManager:
    """AI transfer decision-making: scouting, bidding, selling, loans."""

    def __init__(self, session: Session):
        self.session = session

    def evaluate_squad_needs(self, club_id: int) -> list[dict]:
        """Comprehensive squad analysis returning priority signings.

        Returns: [{"position": str, "priority": str,
                   "budget_alloc": float, "min_ability": int}]
        """
        club = self.session.get(Club, club_id)
        if not club:
            return []

        players = self.session.query(Player).filter_by(club_id=club_id).all()
        budget = club.budget or 0

        # Count players per position group
        pos_count: dict[str, int] = {}
        pos_quality: dict[str, list[int]] = {}
        pos_ages: dict[str, list[int]] = {}

        for p in players:
            pos = p.position or "CM"
            pos_count[pos] = pos_count.get(pos, 0) + 1
            pos_quality.setdefault(pos, []).append(p.overall or 50)
            pos_ages.setdefault(pos, []).append(p.age or 25)

        # Minimum depth requirements
        requirements = {
            "GK": 2, "CB": 3, "LB": 2, "RB": 2,
            "CDM": 1, "CM": 3, "CAM": 1,
            "LW": 1, "RW": 1, "LM": 1, "RM": 1,
            "ST": 2, "CF": 1,
        }

        needs = []

        # Average squad overall for quality benchmarking
        avg_overall = sum(p.overall or 50 for p in players) / max(len(players), 1)

        for pos, min_count in requirements.items():
            current = pos_count.get(pos, 0)
            quality = pos_quality.get(pos, [50])
            avg_qual = sum(quality) / max(len(quality), 1)
            ages = pos_ages.get(pos, [25])
            avg_age = sum(ages) / max(len(ages), 1)

            # Depth shortage
            if current < min_count:
                shortage = min_count - current
                priority = "critical" if shortage >= 2 else "high"
                alloc = min(budget * 0.35, budget)
                needs.append({
                    "position": pos,
                    "priority": priority,
                    "budget_alloc": round(alloc, 2),
                    "min_ability": max(int(avg_overall - 10), 40),
                    "reason": f"depth ({current}/{min_count})",
                })

            # Quality gap: position is much weaker than squad average
            elif avg_qual < avg_overall - 8:
                needs.append({
                    "position": pos,
                    "priority": "medium",
                    "budget_alloc": round(budget * 0.25, 2),
                    "min_ability": int(avg_overall - 5),
                    "reason": "quality_gap",
                })

            # Age profile: squad too old at this position
            elif avg_age > 31 and current <= min_count:
                needs.append({
                    "position": pos,
                    "priority": "low",
                    "budget_alloc": round(budget * 0.15, 2),
                    "min_ability": max(int(avg_overall - 15), 40),
                    "reason": "aging",
                })

        # Sort by priority
        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        needs.sort(key=lambda x: priority_order.get(x["priority"], 99))

        return needs

    def scout_and_sign(
        self,
        club_id: int,
        season: int,
        matchday: int | None = None,
    ):
        """Complete transfer cycle: identify needs, scout, bid, sign."""
        from fm.world.transfer_market import TransferMarket

        club = self.session.get(Club, club_id)
        if not club or (club.budget or 0) < 0.5:
            return

        needs = self.evaluate_squad_needs(club_id)
        if not needs:
            return

        tm = TransferMarket(self.session)

        # Try to fill the top 2 needs
        signings_made = 0
        for need in needs[:3]:
            if signings_made >= 2:
                break
            if (club.budget or 0) < 0.5:
                break

            pos = need["position"]
            max_spend = min(
                need["budget_alloc"],
                (club.budget or 0) * 0.5,
            )

            # Search for targets
            targets = tm.search_players(
                position=pos,
                min_overall=need["min_ability"],
                max_value=max_spend,
                exclude_club_id=club_id,
                max_results=20,
            )

            # Also check free agents
            free_agents = tm.get_free_agents(position=pos)
            free_agents = [
                fa for fa in free_agents
                if (fa.overall or 0) >= need["min_ability"]
            ]

            # Try free agents first (cheaper)
            if free_agents:
                free_agents.sort(
                    key=lambda p: p.overall or 0, reverse=True,
                )
                target = free_agents[0]
                # Offer wage based on quality
                wage_offer = self._calculate_wage_offer(target, club)
                if self._can_afford_wages(club, wage_offer):
                    success = tm.sign_free_agent(
                        club.id, target.id, wage_offer, season,
                    )
                    if success:
                        signings_made += 1
                        continue

            # Try to buy
            if targets:
                # Pick from top 5 with some randomness
                pool = targets[:min(5, len(targets))]
                target = random.choice(pool)
                fair_value = tm.calculate_market_value(target)

                # Bid slightly above market value for higher chance
                bid_amount = fair_value * random.uniform(1.0, 1.25)
                bid_amount = min(bid_amount, max_spend)

                wage_offer = self._calculate_wage_offer(target, club)
                if (
                    bid_amount <= (club.budget or 0)
                    and self._can_afford_wages(club, wage_offer)
                ):
                    tm.make_bid(
                        buyer_club_id=club.id,
                        player_id=target.id,
                        bid_amount=bid_amount,
                        season=season,
                    )
                    signings_made += 1

    def respond_to_incoming_bid(
        self,
        player_id: int,
        club_id: int,
        bid_amount: float,
        season: int,
    ) -> str:
        """Evaluate an incoming bid for one of our players.

        Returns: "accept", "reject", or "counter"
        """
        from fm.world.transfer_market import TransferMarket

        player = self.session.get(Player, player_id)
        club = self.session.get(Club, club_id)
        if not player or not club:
            return "reject"

        tm = TransferMarket(self.session)
        fair_value = tm.calculate_market_value(player)

        # Is this a key player? (top 3 by overall in their position)
        same_pos = (
            self.session.query(Player)
            .filter_by(club_id=club_id, position=player.position)
            .order_by(Player.overall.desc())
            .all()
        )
        is_key = player.id in [p.id for p in same_pos[:2]]

        # Squad depth at this position
        depth = len(same_pos)

        # How good is the offer?
        offer_ratio = bid_amount / max(fair_value, 0.1)

        # Decision logic
        if is_key and depth <= 2:
            # Key player, can't afford to lose
            if offer_ratio >= 2.0:
                return "accept"  # too good to refuse
            elif offer_ratio >= 1.5:
                return "counter"
            return "reject"

        if depth >= 3:
            # We have depth, more willing to sell
            if offer_ratio >= 0.85:
                return "accept"
            elif offer_ratio >= 0.6:
                return "counter"
            return "reject"

        # Standard case
        if offer_ratio >= 1.1:
            return "accept"
        elif offer_ratio >= 0.8:
            return "counter"
        return "reject"

    def decide_loan_moves(self, club_id: int, season: int):
        """Send young players on loan if squad is deep enough."""
        players = self.session.query(Player).filter_by(club_id=club_id).all()
        if len(players) < 20:
            return  # squad too thin

        # Young players (under 22) who are not in the top 15 by overall
        players_sorted = sorted(
            players, key=lambda p: p.overall or 0, reverse=True,
        )
        top_15_ids = {p.id for p in players_sorted[:15]}

        young = [
            p for p in players
            if (p.age or 25) <= 21
            and p.id not in top_15_ids
            and (p.potential or 50) >= (p.overall or 50)
        ]

        if not young:
            return

        # Find clubs in a lower tier that might loan them
        club = self.session.get(Club, club_id)
        if not club or not club.league_id:
            return

        league = self.session.get(League, club.league_id)
        if not league:
            return

        lower_leagues = (
            self.session.query(League)
            .filter(
                League.country == league.country,
                League.tier > league.tier,
            )
            .all()
        )
        if not lower_leagues:
            return

        for player in young[:2]:  # max 2 loans per window
            # Find a club in a lower league
            target_league = random.choice(lower_leagues)
            target_clubs = (
                self.session.query(Club)
                .filter_by(league_id=target_league.id)
                .all()
            )
            if not target_clubs:
                continue

            target_club = random.choice(target_clubs)

            # Create loan transfer
            loan = Transfer(
                player_id=player.id,
                from_club_id=club_id,
                to_club_id=target_club.id,
                fee=0.0,
                wage=player.wage or 0,
                season=season,
                is_loan=True,
                loan_end_season=season + 1,
            )
            self.session.add(loan)

            player.club_id = target_club.id

            self.session.add(NewsItem(
                season=season,
                headline=(
                    f"{player.short_name or player.name} loaned to "
                    f"{target_club.name}"
                ),
                body=(
                    f"{club.name} have loaned {player.name} to "
                    f"{target_club.name} for the season."
                ),
                category="transfer",
            ))

    def decide_contract_renewals(self, club_id: int, season: int):
        """Identify players needing new contracts and renew them."""
        players = self.session.query(Player).filter_by(club_id=club_id).all()
        club = self.session.get(Club, club_id)
        if not club:
            return

        for player in players:
            expiry = player.contract_expiry or season
            years_left = expiry - season

            # Only renew if contract expiring soon and player is valuable
            if years_left > 1:
                continue

            # Check if player is worth keeping
            avg_overall = sum(
                p.overall or 0 for p in players
            ) / max(len(players), 1)

            if (player.overall or 0) < avg_overall - 10 and (player.age or 25) > 29:
                continue  # let them go

            # Offer new contract
            new_wage = (player.wage or 0) * random.uniform(1.05, 1.25)
            new_expiry = season + random.randint(2, 4)

            # Check if club can afford the wage increase
            from fm.world.finance import FinanceManager
            fin = FinanceManager(self.session)
            extra = new_wage - (player.wage or 0)
            if not fin.can_afford_wage(club_id, extra):
                continue

            player.wage = new_wage
            player.contract_expiry = new_expiry

    def _calculate_wage_offer(
        self, player: Player, club: Club,
    ) -> float:
        """Calculate a wage offer for a target player (K-euro/week)."""
        base = player.wage or 0

        # Offer slightly more than current wage
        offer = base * random.uniform(1.05, 1.3)

        # Cap by club's budget tier
        rep = club.reputation or 50
        if rep < 30:
            max_wage = 30.0
        elif rep < 50:
            max_wage = 80.0
        elif rep < 70:
            max_wage = 200.0
        elif rep < 85:
            max_wage = 350.0
        else:
            max_wage = 500.0

        return min(offer, max_wage)

    def _can_afford_wages(self, club: Club, extra_wage: float) -> bool:
        """Quick check if club can handle extra weekly wage."""
        from fm.world.finance import FinanceManager
        fin = FinanceManager(self.session)
        return fin.can_afford_wage(club.id, extra_wage)


# ---------------------------------------------------------------------------
# AI Team Talk Manager
# ---------------------------------------------------------------------------

class AITeamTalkManager:
    """AI chooses appropriate team talks based on context."""

    def __init__(self, session: Session):
        self.session = session

    def choose_pre_match_talk(
        self,
        club_id: int,
        opponent_rep: int,
        team_morale: float,
    ) -> str:
        """Choose best pre-match team talk.

        Returns one of: motivate, calm, praise, criticize, focus, no_pressure
        """
        club = self.session.get(Club, club_id)
        club_rep = (club.reputation if club else 50) or 50
        rep_diff = club_rep - opponent_rep

        # Underdog scenario
        if rep_diff < -15:
            if team_morale < 45:
                return "no_pressure"  # remove pressure, they're not expected to win
            return "motivate"  # fire them up for a big game

        # Favourites
        if rep_diff > 15:
            if team_morale > 80:
                return "calm"  # avoid complacency
            return "focus"  # stay concentrated

        # Even match
        if team_morale < 40:
            return "motivate"
        elif team_morale > 80:
            return "calm"
        return "focus"

    def choose_half_time_talk(
        self,
        club_id: int,
        score_diff: int,
        performance_rating: float,
    ) -> str:
        """React to the first half.

        score_diff: our goals - their goals
        performance_rating: 0-10 team performance
        """
        if score_diff >= 3:
            # Winning comfortably
            return "calm"
        elif score_diff >= 1:
            # Winning, keep focus
            if performance_rating < 5.0:
                return "focus"  # winning but playing badly
            return "praise"
        elif score_diff == 0:
            # Drawing
            if performance_rating >= 6.0:
                return "motivate"  # unlucky, push on
            return "focus"
        elif score_diff >= -1:
            # Losing narrowly
            return "motivate"
        else:
            # Losing badly
            if random.random() < 0.3:
                return "criticize"  # risky but sometimes needed
            return "motivate"

    def choose_post_match_talk(
        self,
        club_id: int,
        goals_for: int,
        goals_against: int,
        opponent_rep: int,
    ) -> str:
        """React to the match result."""
        goal_diff = goals_for - goals_against
        club = self.session.get(Club, club_id)
        club_rep = (club.reputation if club else 50) or 50

        if goal_diff > 0:
            # Win
            if club_rep < opponent_rep - 10:
                return "praise"  # great result as underdogs
            if goal_diff >= 3:
                return "praise"  # comprehensive win
            return "praise"  # wins always get praise
        elif goal_diff == 0:
            # Draw
            if club_rep > opponent_rep + 15:
                return "focus"  # should have won
            if club_rep < opponent_rep - 15:
                return "praise"  # good result against better team
            return "motivate"  # push for more next time
        else:
            # Loss
            if club_rep < opponent_rep - 20:
                return "no_pressure"  # expected loss
            if abs(goal_diff) >= 3:
                if random.random() < 0.25:
                    return "criticize"  # heavy loss deserves critique
                return "motivate"  # bounce back
            return "motivate"  # standard response to a loss


# ---------------------------------------------------------------------------
# Main AI Manager (orchestrator)
# ---------------------------------------------------------------------------

class AIManager:
    """Central decision engine for AI-controlled clubs.

    Maintains backward compatibility while providing comprehensive
    AI intelligence through specialist sub-managers.
    """

    def __init__(self, session: Session):
        self.session = session
        self.squad_selector = AISquadSelector(session)
        self.tactical_mgr = AITacticalManager(session)
        self.transfer_mgr = AITransferManager(session)
        self.talk_mgr = AITeamTalkManager(session)

    # -- Backward-compatible interface ---------------------------------------

    def select_squad(self, club_id: int) -> list[int]:
        """Return player IDs for the best XI (backward-compatible)."""
        result = self.squad_selector.select_match_squad(club_id)
        return result["starting_xi"]

    def adapt_tactics(self, club_id: int, opponent_id: int):
        """Adjust tactical setup based on opponent strength."""
        self.tactical_mgr.decide_pre_match_tactics(club_id, opponent_id)

    def evaluate_squad_needs(self, club_id: int) -> list[str]:
        """Return positions where the squad needs reinforcement.

        Backward-compatible: returns flat list of position strings.
        """
        detailed = self.transfer_mgr.evaluate_squad_needs(club_id)
        positions = []
        for need in detailed:
            positions.append(need["position"])
        return positions

    def make_transfer_decisions(self, club_id: int, season: int):
        """AI manager evaluates and executes transfers during windows."""
        self.transfer_mgr.scout_and_sign(club_id, season)

    def run_all_ai_decisions(self, season: int):
        """Run AI decisions for all non-human clubs."""
        managers = self.session.query(Manager).filter_by(is_human=False).all()
        for mgr in managers:
            if mgr.club_id:
                self.make_transfer_decisions(mgr.club_id, season)
        self.session.commit()

    # -- New comprehensive methods -------------------------------------------

    def process_matchday(
        self,
        club_id: int,
        fixture: Fixture | None = None,
    ) -> dict:
        """Full matchday processing for an AI club.

        Returns dict with squad selection, tactics, and team talk info.
        """
        result = {}

        if not fixture:
            return result

        # Determine opponent
        is_home = fixture.home_club_id == club_id
        opponent_id = (
            fixture.away_club_id if is_home else fixture.home_club_id
        )

        # Adapt tactics for this opponent
        tactics = self.tactical_mgr.decide_pre_match_tactics(
            club_id, opponent_id,
        )
        result["tactics"] = tactics

        # Select squad
        squad = self.squad_selector.select_match_squad(
            club_id, opponent_id,
        )
        result["squad"] = squad

        # Choose pre-match team talk
        opponent = self.session.get(Club, opponent_id)
        opp_rep = (opponent.reputation if opponent else 50) or 50

        players = self.session.query(Player).filter_by(
            club_id=club_id
        ).all()
        avg_morale = sum(
            p.morale or 65 for p in players
        ) / max(len(players), 1)

        talk = self.talk_mgr.choose_pre_match_talk(
            club_id, opp_rep, avg_morale,
        )
        result["pre_match_talk"] = talk

        return result

    def process_weekly(
        self,
        club_id: int,
        season: int,
        matchday: int,
    ):
        """Weekly AI processing between matchdays.

        Handles contract renewals and squad morale management.
        """
        # Contract renewals (check periodically)
        if matchday % 8 == 0:
            self.transfer_mgr.decide_contract_renewals(club_id, season)

    def process_transfer_window(self, club_id: int, season: int):
        """Full transfer window processing for an AI club."""
        # Evaluate needs and make signings
        self.transfer_mgr.scout_and_sign(club_id, season)

        # Consider sending youngsters on loan
        self.transfer_mgr.decide_loan_moves(club_id, season)

    def process_end_of_season(self, club_id: int, season: int):
        """End-of-season decisions: renewals, loan recalls, squad planning."""
        # Contract renewals
        self.transfer_mgr.decide_contract_renewals(club_id, season)

        # Recall loan players (set club_id back)
        loans_out = (
            self.session.query(Transfer)
            .filter_by(
                from_club_id=club_id,
                is_loan=True,
                loan_end_season=season,
            )
            .all()
        )
        for loan in loans_out:
            player = self.session.get(Player, loan.player_id)
            if player:
                player.club_id = club_id

        # Release players that are no longer needed
        self._release_surplus_players(club_id, season)

    def _release_surplus_players(self, club_id: int, season: int):
        """Release low-quality or surplus players to reduce wage bill."""
        players = self.session.query(Player).filter_by(
            club_id=club_id
        ).all()

        if len(players) <= 22:
            return  # squad is lean enough

        # Sort by contribution value (overall, age, wage)
        def value_score(p):
            ovr = p.overall or 50
            age = p.age or 25
            wage = p.wage or 0
            # Young + high potential is valuable
            pot_bonus = max((p.potential or 50) - ovr, 0) * 0.5 if age < 24 else 0
            age_penalty = max(age - 32, 0) * 3
            return ovr + pot_bonus - age_penalty - (wage / 50.0)

        players.sort(key=value_score)

        # Release the worst players until squad is at 25
        excess = len(players) - 25
        for p in players[:excess]:
            # Don't release anyone with overall > squad average - 5
            avg = sum(pl.overall or 50 for pl in players) / len(players)
            if (p.overall or 50) > avg - 5:
                continue

            p.club_id = None

            club = self.session.get(Club, club_id)
            self.session.add(NewsItem(
                season=season,
                headline=f"{p.short_name or p.name} released by {club.name if club else 'club'}",
                body=(
                    f"{p.name} has been released and is now a free agent."
                ),
                category="transfer",
            ))
