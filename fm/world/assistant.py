"""AI Match Preparation Assistant.

Provides tactical analysis, opponent scouting reports, lineup suggestions,
and strategic advice before each match — like having a real assistant manager.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import or_, and_
from sqlalchemy.orm import Session

from fm.db.models import (
    Club, Player, Fixture, LeagueStanding, TacticalSetup,
    PlayerStats, Season,
)
from fm.engine.tactics import TacticalContext, FORMATIONS


# ═══════════════════════════════════════════════════════════════════════════
#  Data Structures
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class OpponentProfile:
    """Scouted profile of an upcoming opponent."""
    club_name: str
    club_id: int
    reputation: int
    formation: str
    mentality: str
    pressing: str
    passing_style: str
    width: str
    defensive_line: str
    avg_overall: float
    avg_attack: float
    avg_midfield: float
    avg_defense: float
    avg_gk: float
    recent_form: str  # e.g. "WWDLW"
    league_position: int
    goals_scored: int
    goals_conceded: int
    key_players: list[dict] = field(default_factory=list)  # name, pos, ovr, threat
    weaknesses: list[str] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)


@dataclass
class HeadToHeadRecord:
    """Historical record between two clubs."""
    total_matches: int = 0
    wins: int = 0
    draws: int = 0
    losses: int = 0
    goals_for: int = 0
    goals_against: int = 0
    recent_results: list[dict] = field(default_factory=list)


@dataclass
class MatchPrepReport:
    """Full pre-match preparation report from the assistant."""
    opponent: OpponentProfile
    match_context: str  # "league", "cup", "continental"
    venue: str  # "home" or "away"
    importance: str  # "low", "normal", "high", "must_win"

    # Tactical recommendations
    recommended_formation: str = "4-3-3"
    recommended_mentality: str = "balanced"
    recommended_pressing: str = "standard"
    recommended_passing: str = "mixed"
    recommended_width: str = "normal"
    recommended_defensive_line: str = "normal"
    recommended_tempo: str = "normal"

    # Special instructions
    key_battle: str = ""  # e.g. "midfield dominance"
    tactical_plan: str = ""  # narrative description
    set_piece_advice: str = ""
    warnings: list[str] = field(default_factory=list)

    # Lineup suggestion
    suggested_xi: list[dict] = field(default_factory=list)  # name, pos, reason
    rest_recommendations: list[str] = field(default_factory=list)

    # Match predictions
    win_probability: float = 0.0
    draw_probability: float = 0.0
    loss_probability: float = 0.0
    predicted_score: str = ""

    # Talking points for team talk
    team_talk_advice: str = ""

    # Historical context
    head_to_head: HeadToHeadRecord = field(default_factory=HeadToHeadRecord)
    opponent_recent_matches: list[dict] = field(default_factory=list)
    player_form_analysis: dict = field(default_factory=dict)  # {"in_form": [...], "out_of_form": [...]}


# ═══════════════════════════════════════════════════════════════════════════
#  Assistant Manager
# ═══════════════════════════════════════════════════════════════════════════

class AssistantManager:
    """AI-powered assistant that helps prepare for matches."""

    def __init__(self, session: Session):
        self.session = session

    # ── Public API ─────────────────────────────────────────────────────────

    def prepare_match_report(
        self,
        club_id: int,
        opponent_id: int,
        is_home: bool,
        match_context: str = "league",
    ) -> MatchPrepReport:
        """Generate a full match preparation report."""
        club = self.session.get(Club, club_id)
        opponent = self.session.get(Club, opponent_id)
        if not club or not opponent:
            return MatchPrepReport(
                opponent=OpponentProfile(
                    club_name="Unknown", club_id=0, reputation=50,
                    formation="4-4-2", mentality="balanced", pressing="standard",
                    passing_style="mixed", width="normal", defensive_line="normal",
                    avg_overall=50, avg_attack=50, avg_midfield=50, avg_defense=50,
                    avg_gk=50, recent_form="", league_position=0,
                    goals_scored=0, goals_conceded=0,
                ),
                match_context=match_context,
                venue="home" if is_home else "away",
                importance="normal",
            )

        # 1. Profile the opponent
        opp_profile = self._profile_opponent(opponent)

        # 2. Assess match importance
        importance = self._assess_importance(club, opponent, match_context)

        # 3. Generate tactical recommendations
        rec = self._recommend_tactics(club, opp_profile, is_home, importance)

        # 4. Suggest lineup
        suggested_xi, rest_recs = self._suggest_lineup(club_id, opp_profile, importance)

        # 5. Predict outcome
        win_p, draw_p, loss_p, pred_score = self._predict_outcome(
            club, opponent, is_home,
        )

        # 5b. Historical & form analysis
        h2h = self._get_head_to_head(club_id, opponent_id)
        opp_recent = self._get_opponent_recent_matches(opponent_id)
        form_analysis = self._analyze_player_form(club_id)

        # 6. Generate narrative advice
        tactical_plan = self._generate_tactical_plan(
            club, opp_profile, rec, is_home, importance, h2h,
        )
        key_battle = self._identify_key_battle(club_id, opp_profile)
        set_piece_advice = self._set_piece_advice(club_id, opp_profile)
        warnings = self._generate_warnings(club_id, opp_profile, importance)
        talk_advice = self._team_talk_advice(club, opp_profile, importance, is_home)

        venue = "home" if is_home else "away"

        return MatchPrepReport(
            opponent=opp_profile,
            match_context=match_context,
            venue=venue,
            importance=importance,
            recommended_formation=rec["formation"],
            recommended_mentality=rec["mentality"],
            recommended_pressing=rec["pressing"],
            recommended_passing=rec["passing"],
            recommended_width=rec["width"],
            recommended_defensive_line=rec["defensive_line"],
            recommended_tempo=rec["tempo"],
            key_battle=key_battle,
            tactical_plan=tactical_plan,
            set_piece_advice=set_piece_advice,
            warnings=warnings,
            suggested_xi=suggested_xi,
            rest_recommendations=rest_recs,
            win_probability=win_p,
            draw_probability=draw_p,
            loss_probability=loss_p,
            predicted_score=pred_score,
            team_talk_advice=talk_advice,
            head_to_head=h2h,
            opponent_recent_matches=opp_recent,
            player_form_analysis=form_analysis,
        )

    def get_quick_advice(self, club_id: int, opponent_id: int, is_home: bool) -> str:
        """Get a quick one-paragraph tactical summary."""
        report = self.prepare_match_report(club_id, opponent_id, is_home)
        return report.tactical_plan

    # ── Opponent Profiling ─────────────────────────────────────────────────

    def _profile_opponent(self, opponent: Club) -> OpponentProfile:
        """Build a detailed opponent profile from DB data."""
        players = self.session.query(Player).filter_by(club_id=opponent.id).all()
        tactics = self.session.query(TacticalSetup).filter_by(
            club_id=opponent.id
        ).first()

        # Average attributes by position group
        attackers = [p for p in players if p.position in ("ST", "CF", "LW", "RW", "CAM")]
        midfielders = [p for p in players if p.position in ("CM", "CDM", "LM", "RM")]
        defenders = [p for p in players if p.position in ("CB", "LB", "RB", "LWB", "RWB")]
        goalkeepers = [p for p in players if p.position == "GK"]

        avg_att = sum(p.overall or 50 for p in attackers) / max(len(attackers), 1)
        avg_mid = sum(p.overall or 50 for p in midfielders) / max(len(midfielders), 1)
        avg_def = sum(p.overall or 50 for p in defenders) / max(len(defenders), 1)
        avg_gk = sum(p.overall or 50 for p in goalkeepers) / max(len(goalkeepers), 1)
        avg_ovr = sum(p.overall or 50 for p in players) / max(len(players), 1)

        # Get recent form from standings
        standing = self.session.query(LeagueStanding).filter_by(
            club_id=opponent.id,
        ).order_by(LeagueStanding.season.desc()).first()
        recent_form = (standing.form or "")[-5:] if standing else ""
        league_pos = 0
        gs = 0
        gc = 0
        if standing:
            # Calculate position
            all_standings = (
                self.session.query(LeagueStanding)
                .filter_by(league_id=opponent.league_id, season=standing.season)
                .order_by(LeagueStanding.points.desc(), LeagueStanding.goal_difference.desc())
                .all()
            )
            for i, s in enumerate(all_standings):
                if s.club_id == opponent.id:
                    league_pos = i + 1
                    break
            gs = standing.goals_for or 0
            gc = standing.goals_against or 0

        # Key players (top 5 by overall)
        top_players = sorted(players, key=lambda p: p.overall or 0, reverse=True)[:5]
        key_players = []
        for p in top_players:
            threat = self._assess_player_threat(p)
            key_players.append({
                "name": p.name,
                "position": p.position,
                "overall": p.overall,
                "threat": threat,
            })

        # Identify strengths and weaknesses
        strengths, weaknesses = self._analyze_squad_balance(
            avg_att, avg_mid, avg_def, avg_gk, players,
        )

        formation = (tactics.formation if tactics else "4-4-2") or "4-4-2"
        mentality = (tactics.mentality if tactics else "balanced") or "balanced"
        pressing = (tactics.pressing if tactics else "standard") or "standard"
        passing_style = (tactics.passing_style if tactics else "mixed") or "mixed"
        width = (tactics.width if tactics else "normal") or "normal"
        def_line = (tactics.defensive_line if tactics else "normal") or "normal"

        return OpponentProfile(
            club_name=opponent.name,
            club_id=opponent.id,
            reputation=opponent.reputation or 50,
            formation=formation,
            mentality=mentality,
            pressing=pressing,
            passing_style=passing_style,
            width=width,
            defensive_line=def_line,
            avg_overall=round(avg_ovr, 1),
            avg_attack=round(avg_att, 1),
            avg_midfield=round(avg_mid, 1),
            avg_defense=round(avg_def, 1),
            avg_gk=round(avg_gk, 1),
            recent_form=recent_form,
            league_position=league_pos,
            goals_scored=gs,
            goals_conceded=gc,
            key_players=key_players,
            weaknesses=weaknesses,
            strengths=strengths,
        )

    def _assess_player_threat(self, player: Player) -> str:
        """Classify a player's main threat type."""
        pos = player.position or ""
        ovr = player.overall or 50
        pace = player.pace or 50
        finishing = player.finishing or 50
        dribbling = player.dribbling or 50
        passing = player.passing or 50
        heading = player.heading_accuracy or 50

        if pos in ("ST", "CF"):
            if finishing > 80:
                return "clinical finisher"
            if pace > 80:
                return "pace threat"
            if heading > 80:
                return "aerial target"
            return "all-round forward"
        elif pos in ("LW", "RW"):
            if pace > 82:
                return "rapid winger"
            if dribbling > 80:
                return "tricky dribbler"
            if passing > 78:
                return "creative wide player"
            return "wide threat"
        elif pos in ("CAM",):
            if passing > 80:
                return "playmaker"
            if finishing > 75:
                return "goal-threat midfielder"
            return "creative threat"
        elif pos in ("CM", "CDM"):
            if passing > 80:
                return "deep playmaker"
            if player.standing_tackle and player.standing_tackle > 80:
                return "midfield enforcer"
            return "box-to-box"
        elif pos in ("CB", "LB", "RB"):
            if pace > 78 and pos in ("LB", "RB"):
                return "overlapping full-back"
            if heading > 80:
                return "commanding defender"
            return "solid defender"
        elif pos == "GK":
            return "shot-stopper" if ovr > 78 else "goalkeeper"
        return "squad player"

    def _analyze_squad_balance(
        self, avg_att: float, avg_mid: float, avg_def: float,
        avg_gk: float, players: list[Player],
    ) -> tuple[list[str], list[str]]:
        """Identify squad strengths and weaknesses."""
        strengths = []
        weaknesses = []

        # Attack quality
        if avg_att >= 78:
            strengths.append("Dangerous attack with high-quality forwards")
        elif avg_att < 65:
            weaknesses.append("Weak attacking options — may struggle to score")

        # Midfield
        if avg_mid >= 78:
            strengths.append("Strong midfield — expect them to dominate possession")
        elif avg_mid < 65:
            weaknesses.append("Vulnerable in midfield — can be overrun")

        # Defense
        if avg_def >= 78:
            strengths.append("Rock-solid defense — hard to break down")
        elif avg_def < 65:
            weaknesses.append("Shaky defense — can be exposed with pace and movement")

        # GK
        if avg_gk >= 80:
            strengths.append("World-class goalkeeper — shots from distance less effective")
        elif avg_gk < 65:
            weaknesses.append("Weak goalkeeper — test them with shots from range")

        # Pace analysis
        fast_players = [p for p in players if (p.pace or 50) > 80]
        slow_defenders = [p for p in players
                          if p.position in ("CB",) and (p.pace or 50) < 60]
        if len(fast_players) >= 3:
            strengths.append("Rapid counter-attack threat — pace in forward positions")
        if slow_defenders:
            weaknesses.append("Slow centre-backs — vulnerable to through balls and pace")

        # Set piece specialists
        fk_specialists = [p for p in players if (p.free_kick_accuracy or 50) > 80]
        if fk_specialists:
            strengths.append("Set-piece danger — excellent free kick taker(s)")

        # Aerial
        tall_players = [p for p in players if (p.heading_accuracy or 50) > 80]
        if len(tall_players) >= 3:
            strengths.append("Aerial dominance — strong in the air from set pieces")

        # Depth
        if len(players) < 20:
            weaknesses.append("Thin squad — fatigue could be a factor")
        elif len(players) > 28:
            strengths.append("Deep squad — can rotate without quality drop")

        return strengths, weaknesses

    # ── Tactical Recommendations ───────────────────────────────────────────

    def _recommend_tactics(
        self, club: Club, opp: OpponentProfile,
        is_home: bool, importance: str,
    ) -> dict:
        """Recommend tactics to counter the opponent."""
        rec = {
            "formation": "4-3-3",
            "mentality": "balanced",
            "pressing": "standard",
            "passing": "mixed",
            "width": "normal",
            "defensive_line": "normal",
            "tempo": "normal",
        }
        our_rep = club.reputation or 50
        their_rep = opp.reputation

        # Formation counter-play
        opp_form = opp.formation
        if opp_form in ("4-3-3", "4-2-3-1"):
            # Mirror or use midfield overload
            if opp.avg_midfield > 75:
                rec["formation"] = "4-2-3-1"  # extra midfielder to compete
            else:
                rec["formation"] = "4-3-3"  # match them
        elif opp_form in ("3-5-2", "3-4-3"):
            # Exploit wide areas against 3-back
            rec["formation"] = "4-3-3"
            rec["width"] = "wide"
        elif opp_form in ("5-3-2", "5-4-1"):
            # They're parking the bus — play through the middle
            rec["formation"] = "4-2-3-1"
            rec["passing"] = "short"
            rec["tempo"] = "fast"
        elif opp_form == "4-5-1":
            # Midfield-heavy — match numbers or go direct
            rec["formation"] = "4-3-3"
            rec["passing"] = "direct"

        # Mentality based on relative strength and venue
        strength_diff = our_rep - their_rep
        if strength_diff > 20:
            rec["mentality"] = "positive"
            rec["pressing"] = "high"
        elif strength_diff > 5:
            rec["mentality"] = "positive" if is_home else "balanced"
        elif strength_diff < -20:
            rec["mentality"] = "cautious"
            rec["pressing"] = "standard"
            rec["defensive_line"] = "deep"
        elif strength_diff < -5:
            rec["mentality"] = "balanced"
            if not is_home:
                rec["mentality"] = "cautious"

        # Home advantage adjustments
        if is_home:
            if rec["mentality"] == "cautious":
                rec["mentality"] = "balanced"
            if rec["pressing"] == "low":
                rec["pressing"] = "standard"

        # Counter opponent pressing
        if opp.pressing in ("high", "very_high"):
            rec["passing"] = "direct"  # bypass their press
            rec["tempo"] = "fast"
            if opp.defensive_line == "high":
                rec["passing"] = "direct"
                # Counter-attack opportunity
                rec["mentality"] = "balanced"  # absorb then strike

        # Counter opponent width
        if opp.width in ("wide", "very_wide"):
            rec["width"] = "narrow"  # compact shape to deny crosses

        # Importance adjustments
        if importance == "must_win":
            if rec["mentality"] in ("cautious", "defensive"):
                rec["mentality"] = "balanced"
            rec["pressing"] = "high"
        elif importance == "low":
            rec["mentality"] = "balanced"  # conserve energy

        # Counter low-block opponents
        if opp.mentality in ("defensive", "very_defensive"):
            rec["width"] = "wide"
            rec["tempo"] = "fast"
            rec["passing"] = "short"  # patient build-up

        # Exploit weak defense
        if "Shaky defense" in " ".join(opp.weaknesses) or "Slow centre-backs" in " ".join(opp.weaknesses):
            rec["tempo"] = "fast"
            rec["pressing"] = "high"  # force errors

        return rec

    def _assess_importance(
        self, club: Club, opponent: Club, context: str,
    ) -> str:
        """How important is this match?"""
        if context in ("continental", "cup_final", "cup_semi"):
            return "must_win"
        if context == "cup":
            return "high"

        # League position context
        standing = self.session.query(LeagueStanding).filter_by(
            club_id=club.id,
        ).order_by(LeagueStanding.season.desc()).first()
        opp_standing = self.session.query(LeagueStanding).filter_by(
            club_id=opponent.id,
        ).order_by(LeagueStanding.season.desc()).first()

        if not standing:
            return "normal"

        played = standing.played or 0
        pts = standing.points or 0

        # Late-season pressure
        if played > 30:
            if pts < played * 1.2:  # relegation zone
                return "must_win"
            # Title race
            all_standings = (
                self.session.query(LeagueStanding)
                .filter_by(league_id=club.league_id, season=standing.season)
                .order_by(LeagueStanding.points.desc())
                .limit(4)
                .all()
            )
            if all_standings and abs((all_standings[0].points or 0) - pts) <= 6:
                return "high"

        # Big match against a rival
        if opponent.reputation and opponent.reputation > 75:
            return "high"

        return "normal"

    # ── Lineup Suggestions ─────────────────────────────────────────────────

    def _suggest_lineup(
        self, club_id: int, opp: OpponentProfile, importance: str,
    ) -> tuple[list[dict], list[str]]:
        """Suggest starting XI and rotation candidates."""
        players = self.session.query(Player).filter_by(club_id=club_id).all()
        if not players:
            return [], []

        # Score each player
        scored = []
        for p in players:
            if (p.injured_weeks or 0) > 0:
                continue
            if (p.suspended_matches or 0) > 0:
                continue

            fitness = p.fitness or 100
            morale = p.morale or 65
            form = p.form or 65
            ovr = p.overall or 50

            # Base score from overall
            score = ovr * 1.0
            # Fitness penalty (below 70 is risky)
            if fitness < 70:
                score -= (70 - fitness) * 0.3
            if fitness < 50:
                score -= 10  # heavily penalize very tired players
            # Morale bonus
            score += (morale - 65) * 0.1
            # Form bonus
            score += (form - 65) * 0.15

            scored.append((p, score))

        # Sort by position priority
        position_needs = _formation_positions(opp.formation)  # we want to fill our formation

        suggested = []
        rest_recs = []
        used_ids = set()

        # Pick best player for each position
        for pos in ["GK", "CB", "CB", "LB", "RB", "CDM", "CM", "CM",
                     "CAM", "LW", "RW", "ST", "CF"]:
            candidates = [
                (p, s) for p, s in scored
                if p.id not in used_ids
                and _can_play(p.position, pos)
            ]
            if not candidates:
                continue
            candidates.sort(key=lambda x: x[1], reverse=True)
            best_p, best_s = candidates[0]
            reason = ""
            if (best_p.fitness or 100) < 75:
                reason = "⚠️ Low fitness"
            elif (best_p.morale or 65) > 80:
                reason = "High morale"
            elif (best_p.form or 65) > 80:
                reason = "In great form"
            else:
                reason = "Best available"

            suggested.append({
                "name": best_p.name,
                "position": pos,
                "overall": best_p.overall,
                "fitness": best_p.fitness or 100,
                "reason": reason,
            })
            used_ids.add(best_p.id)

            # Rest recommendations
            if (best_p.fitness or 100) < 65 and importance != "must_win":
                rest_recs.append(
                    f"{best_p.name} ({pos}) — fitness at {best_p.fitness}%, "
                    f"consider resting"
                )

        return suggested[:11], rest_recs

    # ── Predictions ────────────────────────────────────────────────────────

    def _predict_outcome(
        self, club: Club, opponent: Club, is_home: bool,
    ) -> tuple[float, float, float, str]:
        """Simple Elo-like match prediction."""
        our_rep = club.reputation or 50
        opp_rep = opponent.reputation or 50

        # Elo-style expected score
        diff = our_rep - opp_rep
        if is_home:
            diff += 8  # home advantage ≈ 8 reputation points

        # Logistic function
        expected = 1.0 / (1.0 + 10 ** (-diff / 40.0))

        # Convert to W/D/L probabilities
        # Draw probability peaks around 50% expected
        draw_base = 0.25
        draw_p = draw_base - abs(expected - 0.5) * 0.3
        draw_p = max(0.10, min(0.35, draw_p))

        win_p = expected * (1.0 - draw_p)
        loss_p = 1.0 - win_p - draw_p

        # Predict score
        our_strength = our_rep / 100.0 * 2.5
        their_strength = opp_rep / 100.0 * 2.5
        if is_home:
            our_strength += 0.3

        our_goals = round(our_strength * (0.4 + expected * 0.6))
        their_goals = round(their_strength * (0.4 + (1 - expected) * 0.6))
        predicted = f"{our_goals}-{their_goals}"

        return round(win_p, 2), round(draw_p, 2), round(loss_p, 2), predicted

    # ── Narrative Generation ───────────────────────────────────────────────

    def _generate_tactical_plan(
        self, club: Club, opp: OpponentProfile,
        rec: dict, is_home: bool, importance: str,
        h2h: Optional[HeadToHeadRecord] = None,
    ) -> str:
        """Generate a readable tactical briefing."""
        venue = "at home" if is_home else "away"
        our_name = club.name

        lines = []
        lines.append(
            f"Boss, we're up against {opp.club_name} {venue}. "
            f"They're sitting {_ordinal(opp.league_position)} in the table "
            f"with form {opp.recent_form or 'unknown'}."
        )

        # Opponent style
        style_desc = _describe_style(opp.mentality, opp.pressing, opp.passing_style)
        lines.append(f"They play a {opp.formation} — {style_desc}.")

        # Our approach
        rec_desc = _describe_style(rec["mentality"], rec["pressing"], rec["passing"])
        lines.append(
            f"I'd recommend we go with a {rec['formation']} — {rec_desc}. "
            f"Set the tempo to {rec['tempo']} and width {rec['width']}."
        )

        # Key threats
        if opp.key_players:
            top = opp.key_players[0]
            lines.append(
                f"Watch out for {top['name']} ({top['position']}, {top['overall']} OVR) "
                f"— {top['threat']}. "
                f"We need to have a plan to neutralize them."
            )

        # Weaknesses to exploit
        if opp.weaknesses:
            lines.append(f"Their weaknesses: {opp.weaknesses[0].lower()}.")

        # Head-to-head context
        if h2h and h2h.total_matches > 0:
            if h2h.wins > h2h.losses:
                lines.append(
                    f"We have a strong record against them — "
                    f"{h2h.wins} wins in {h2h.total_matches} meetings."
                )
            elif h2h.losses > h2h.wins:
                lines.append(
                    "They've had the upper hand recently — "
                    "we need to find a different approach."
                )
            else:
                lines.append(
                    f"It's been evenly matched historically — "
                    f"{h2h.draws} draws in {h2h.total_matches} meetings."
                )

        # Importance
        if importance == "must_win":
            lines.append("This is a huge match — we need three points here.")
        elif importance == "high":
            lines.append("A big game for us — let's make sure we're fully prepared.")

        return " ".join(lines)

    def _identify_key_battle(self, club_id: int, opp: OpponentProfile) -> str:
        """Identify the key tactical battle."""
        our_players = self.session.query(Player).filter_by(club_id=club_id).all()
        our_mid = [p for p in our_players if p.position in ("CM", "CDM", "CAM")]
        our_mid_avg = sum(p.overall or 50 for p in our_mid) / max(len(our_mid), 1)

        if abs(our_mid_avg - opp.avg_midfield) < 5:
            return "Midfield battle — evenly matched, whoever wins here controls the game"
        elif our_mid_avg > opp.avg_midfield + 5:
            return "We should dominate midfield — look to control possession and tempo"
        elif opp.avg_attack > 78:
            return "Our defense vs their attack — stay organized and don't get caught out"
        elif opp.avg_defense > 78:
            return "Breaking down their defense — need patience and movement"
        else:
            return "Midfield control — win the battle in the middle of the park"

    def _set_piece_advice(self, club_id: int, opp: OpponentProfile) -> str:
        """Advice on set pieces."""
        our_players = self.session.query(Player).filter_by(club_id=club_id).all()
        our_headers = [p for p in our_players
                       if (p.heading_accuracy or 50) > 75]
        opp_aerial_weak = opp.avg_defense < 72

        if our_headers and opp_aerial_weak:
            names = ", ".join(p.name for p in our_headers[:2])
            return (
                f"Set pieces could be key — target {names} from corners "
                f"and free kicks. Their defense is vulnerable in the air."
            )
        elif our_headers:
            return "Look for set-piece opportunities — we have good aerial threats."
        else:
            return "Play corners short and work the ball in — we lack aerial power."

    def _generate_warnings(
        self, club_id: int, opp: OpponentProfile, importance: str,
    ) -> list[str]:
        """Generate warnings about potential issues."""
        warnings = []
        players = self.session.query(Player).filter_by(club_id=club_id).all()

        # Fitness warnings
        tired = [p for p in players if (p.fitness or 100) < 65
                 and (p.injured_weeks or 0) == 0]
        if tired:
            names = ", ".join(p.name for p in tired[:3])
            warnings.append(f"Fitness concern: {names} may need rotation")

        # Yellow card warnings (1 away from ban)
        from fm.config import YELLOW_CARD_BAN_THRESHOLD
        close_to_ban = [
            p for p in players
            if (getattr(p, 'yellow_cards_season', 0) or 0) == YELLOW_CARD_BAN_THRESHOLD - 1
        ]
        if close_to_ban:
            names = ", ".join(p.name for p in close_to_ban[:3])
            warnings.append(
                f"Card risk: {names} — one yellow from suspension"
            )

        # Opponent pace vs our slow CBs
        if "pace threat" in str(opp.key_players) or "rapid winger" in str(opp.key_players):
            our_cbs = [p for p in players if p.position == "CB"]
            slow_cbs = [p for p in our_cbs if (p.pace or 50) < 60]
            if slow_cbs:
                names = ", ".join(p.name for p in slow_cbs[:2])
                warnings.append(
                    f"Pace mismatch: {names} could be exposed against "
                    f"their quick forwards"
                )

        # Injury risk from high intensity
        if importance == "must_win":
            warnings.append(
                "High-intensity match expected — monitor fatigue closely"
            )

        return warnings

    # ── Historical & Form Analysis ──────────────────────────────────────

    def _get_head_to_head(self, club_id: int, opponent_id: int) -> HeadToHeadRecord:
        """Get historical head-to-head record between two clubs."""
        fixtures = (
            self.session.query(Fixture)
            .filter(
                Fixture.played == True,  # noqa: E712
                or_(
                    and_(Fixture.home_club_id == club_id, Fixture.away_club_id == opponent_id),
                    and_(Fixture.home_club_id == opponent_id, Fixture.away_club_id == club_id),
                ),
            )
            .order_by(Fixture.season.desc(), Fixture.matchday.desc())
            .all()
        )

        record = HeadToHeadRecord()
        record.total_matches = len(fixtures)

        for fix in fixtures:
            home_goals = fix.home_goals or 0
            away_goals = fix.away_goals or 0

            if fix.home_club_id == club_id:
                gf, ga = home_goals, away_goals
                venue = "H"
            else:
                gf, ga = away_goals, home_goals
                venue = "A"

            record.goals_for += gf
            record.goals_against += ga

            if gf > ga:
                result = "W"
                record.wins += 1
            elif gf == ga:
                result = "D"
                record.draws += 1
            else:
                result = "L"
                record.losses += 1

            # Keep last 5 for recent_results
            if len(record.recent_results) < 5:
                record.recent_results.append({
                    "score": f"{gf}-{ga}",
                    "result": result,
                    "venue": venue,
                    "season": getattr(fix, "season", 0),
                    "matchday": getattr(fix, "matchday", 0),
                })

        return record

    def _get_opponent_recent_matches(self, opponent_id: int, limit: int = 5) -> list[dict]:
        """Get opponent's recent match results."""
        fixtures = (
            self.session.query(Fixture)
            .filter(
                Fixture.played == True,  # noqa: E712
                or_(
                    Fixture.home_club_id == opponent_id,
                    Fixture.away_club_id == opponent_id,
                ),
            )
            .order_by(Fixture.season.desc(), Fixture.matchday.desc())
            .limit(limit)
            .all()
        )

        results = []
        for fix in fixtures:
            home_goals = fix.home_goals or 0
            away_goals = fix.away_goals or 0

            if fix.home_club_id == opponent_id:
                venue = "H"
                gf, ga = home_goals, away_goals
                other_id = fix.away_club_id
                formation = getattr(fix, "home_formation", None)
            else:
                venue = "A"
                gf, ga = away_goals, home_goals
                other_id = fix.home_club_id
                formation = getattr(fix, "away_formation", None)

            if gf > ga:
                result = "W"
            elif gf == ga:
                result = "D"
            else:
                result = "L"

            # Get opponent club name
            other_club = self.session.get(Club, other_id)
            other_name = other_club.name if other_club else "Unknown"

            results.append({
                "opponent": other_name,
                "score": f"{gf}-{ga}",
                "result": result,
                "venue": venue,
                "matchday": getattr(fix, "matchday", 0),
                "formation": formation or "unknown",
            })

        return results

    def _analyze_player_form(self, club_id: int) -> dict:
        """Analyze player form to identify in-form and out-of-form players."""
        players = self.session.query(Player).filter_by(club_id=club_id).all()
        if not players:
            return {"in_form": [], "out_of_form": []}

        # Filter out injured players
        available = [p for p in players if (getattr(p, "injured_weeks", 0) or 0) == 0]
        if not available:
            available = players

        def form_score(p: Player) -> float:
            """Composite score: form > morale > fitness."""
            f = getattr(p, "form", None) or 65.0
            m = getattr(p, "morale", None) or 65.0
            fit = getattr(p, "fitness", None) or 100.0
            return f * 0.5 + m * 0.3 + fit * 0.2

        sorted_players = sorted(available, key=form_score, reverse=True)

        def _player_entry(p: Player) -> dict:
            # Try to get recent goals from PlayerStats
            recent_goals = 0
            stats = (
                self.session.query(PlayerStats)
                .filter_by(player_id=p.id)
                .order_by(PlayerStats.season.desc())
                .first()
            )
            if stats:
                recent_goals = getattr(stats, "goals", 0) or 0

            return {
                "name": getattr(p, "name", "Unknown"),
                "position": getattr(p, "position", ""),
                "overall": getattr(p, "overall", 50) or 50,
                "form": getattr(p, "form", None) or 65.0,
                "morale": getattr(p, "morale", None) or 65.0,
                "fitness": getattr(p, "fitness", None) or 100.0,
                "recent_goals": recent_goals,
            }

        in_form = [_player_entry(p) for p in sorted_players[:3]]
        out_of_form = [_player_entry(p) for p in sorted_players[-3:]]

        # Avoid overlap if fewer than 6 players
        if len(sorted_players) <= 6:
            out_of_form = [
                _player_entry(p) for p in sorted_players[-3:]
                if p not in sorted_players[:3]
            ]

        return {"in_form": in_form, "out_of_form": out_of_form}

    def _team_talk_advice(
        self, club: Club, opp: OpponentProfile,
        importance: str, is_home: bool,
    ) -> str:
        """Suggest what kind of team talk to give."""
        our_rep = club.reputation or 50
        diff = our_rep - opp.reputation

        if diff > 20:
            return (
                "We're clear favourites. A calm, focused approach should work — "
                "remind them it's a match they're expected to win, but stay sharp."
            )
        elif diff > 5:
            return (
                "We have the edge. Motivate the lads — tell them to express "
                "themselves and play with confidence."
            )
        elif diff < -20:
            return (
                "We're the underdogs here. Use 'No Pressure' — take the burden "
                "off their shoulders and let them play freely."
            )
        elif diff < -5:
            return (
                "Tough match against a strong side. A passionate team talk "
                "could fire them up — show them we believe."
            )
        else:
            if is_home:
                return (
                    "Even match on paper but we have home advantage. "
                    "Motivate them — the crowd is behind us."
                )
            return (
                "This could go either way. Focus the team — "
                "concentration and discipline will be key."
            )


# ═══════════════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════════════

def _ordinal(n: int) -> str:
    if n == 0:
        return "unranked"
    suffixes = {1: "st", 2: "nd", 3: "rd"}
    if 11 <= n % 100 <= 13:
        suffix = "th"
    else:
        suffix = suffixes.get(n % 10, "th")
    return f"{n}{suffix}"


def _describe_style(mentality: str, pressing: str, passing: str) -> str:
    """One-line description of a playing style."""
    ment_desc = {
        "very_defensive": "ultra-defensive",
        "defensive": "defensive",
        "cautious": "cautious",
        "balanced": "balanced",
        "positive": "progressive",
        "attacking": "attacking",
        "very_attacking": "all-out attacking",
    }
    press_desc = {
        "low": "sitting deep",
        "standard": "moderate pressing",
        "high": "high pressing",
        "very_high": "intense gegenpressing",
    }
    pass_desc = {
        "very_short": "tiki-taka short passing",
        "short": "short passing game",
        "mixed": "mixed passing",
        "direct": "direct play",
        "very_direct": "long-ball",
    }

    m = ment_desc.get(mentality, mentality)
    pr = press_desc.get(pressing, pressing)
    pa = pass_desc.get(passing, passing)
    return f"{m} with {pr} and {pa}"


def _can_play(natural_pos: str, target_pos: str) -> bool:
    """Can a player play in the target position?"""
    if natural_pos == target_pos:
        return True
    compat = {
        "GK": {"GK"},
        "CB": {"CB", "CDM"},
        "LB": {"LB", "LWB", "LM"},
        "RB": {"RB", "RWB", "RM"},
        "LWB": {"LB", "LWB", "LM"},
        "RWB": {"RB", "RWB", "RM"},
        "CDM": {"CDM", "CM", "CB"},
        "CM": {"CM", "CDM", "CAM"},
        "CAM": {"CAM", "CM", "CF"},
        "LM": {"LM", "LW", "LB"},
        "RM": {"RM", "RW", "RB"},
        "LW": {"LW", "LM", "ST"},
        "RW": {"RW", "RM", "ST"},
        "CF": {"CF", "ST", "CAM"},
        "ST": {"ST", "CF", "LW", "RW"},
    }
    return target_pos in compat.get(natural_pos, set())


def _formation_positions(formation: str) -> list[str]:
    """Get position list for a formation."""
    form_map = {
        "4-4-2": ["GK", "LB", "CB", "CB", "RB", "LM", "CM", "CM", "RM", "ST", "ST"],
        "4-3-3": ["GK", "LB", "CB", "CB", "RB", "CM", "CM", "CM", "LW", "ST", "RW"],
        "4-2-3-1": ["GK", "LB", "CB", "CB", "RB", "CDM", "CDM", "LW", "CAM", "RW", "ST"],
        "3-5-2": ["GK", "CB", "CB", "CB", "LM", "CM", "CDM", "CM", "RM", "ST", "ST"],
        "5-3-2": ["GK", "LWB", "CB", "CB", "CB", "RWB", "CM", "CM", "CM", "ST", "ST"],
        "4-1-4-1": ["GK", "LB", "CB", "CB", "RB", "CDM", "LM", "CM", "CM", "RM", "ST"],
        "3-4-3": ["GK", "CB", "CB", "CB", "LM", "CM", "CM", "RM", "LW", "ST", "RW"],
        "4-5-1": ["GK", "LB", "CB", "CB", "RB", "LM", "CM", "CM", "CM", "RM", "ST"],
    }
    return form_map.get(formation, form_map["4-4-2"])
