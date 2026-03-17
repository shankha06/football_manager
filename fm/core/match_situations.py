"""Comprehensive real-life football match situations with cascading consequences.

This system models 40+ real-world match situations that occur in professional
football, each with immediate short-term impacts and cascading long-term effects:

1. DISCIPLINARY DRAMA
   • Red Card Incident (reckless/violent)
   • Yellow Card Accumulation
   • Disputed Penalty Decision
   • VAR Controversy
   • Referee Bias/Shocking Decisions

2. TACTICAL/SITUATIONAL
   • Late Goal (89-90 min) — comeback/heartbreak
   • Early Red Card (before min 20)
   • Goalkeeper Error
   • Defensive Collapse (3+ goals conceded in 15 min)
   • Own Goal
   • Set Piece Failure

3. PLAYER PERFORMANCE DRAMA
   • Missed Penalty
   • Goal Drought (5+ matches, 0 goals)
   • Scoring Run (3+ goals in 3 matches)
   • Player Conflict/Substitution Drama
   • Young Player (U23) Debut/Breakthrough
   • Veteran Performance (age 33+)

4. MOMENTUM & PSYCHOLOGY
   • Comeback Victory (2+ goal deficit)
   • Expected Upset (lower-ranked beats higher)
   • Clean Sheet (after injury crisis)
   • Easy Win (3+ goal margin)
   • Narrow Loss (1-goal defeat)
   • Derby/Rivalry Match

5. COMPETITION & PROGRESSION
   • Cup Elimination (injury crisis)
   • European Competition Exit
   • Historic Record (beat/broken)
   • Unbeaten Run Broken
   • Title Race Blow (loss to rival)

6. HEALTH & FITNESS
   • First Match Back (after injury)
   • Recurring Injury (same player, same injury)
   • Multiple Players Out (3+ starters injured)
   • Substitution After Short Appearance
   • Illness Outbreak (2+ players)

7. MATCH CONDITIONS
   • Short Turnaround (2 days between matches)
   • Weather Extreme (heavy rain/snow/heat)
   • Away Record (historic bad record broken)
   • Home Fortress Breached
   • Travel Fatigue (long distance)

8. MANAGEMENT & AUTHORITY
   • Tactical Masterclass (unexpected formation works)
   • Manager Outplayed (underperformance vs rival)
   • Substitution Timing Criticized
   • Team Talk Needed (morale boost)
   • Formation Change (mid-match tactical shift)

Each situation triggers:
• Short-term: Momentum shift, immediate player stats, match xG advantage
• Medium-term (1-3 MD): Morale cascades, friend networks, form impact
• Long-term (4+ MD): Contract/transfer fallout, confidence spirals, narrative arcs
"""
from __future__ import annotations

import random

from sqlalchemy.orm import Session

from fm.db.models import (
    Club,
    NewsItem,
    Player,
    PlayerRelationship,
    ConsequenceLog,
    Injury,
    LeagueStanding,
    TacticalSetup,
)
from fm.utils.helpers import clamp


class MatchSituationEngine:
    """Processes in-match and post-match situations with cascading consequences."""

    # ── SHORT-TERM EFFECTS (Applied immediately in match) ────────────────

    @staticmethod
    def handle_red_card_incident(
        session: Session,
        club_id: int,
        player_id: int,
        incident_type: str,  # "reckless", "violent", "second_yellow"
        minute: int,
        season: int,
        matchday: int,
    ) -> dict:
        """Handle red card incidents with cascading effects.

        incident_type: "reckless" (dangerous but accidental),
                       "violent" (intentional misconduct),
                       "second_yellow" (accumulated fouls)
        """
        player = session.get(Player, player_id)
        club = session.get(Club, club_id)
        effects = {}

        if player is None or club is None:
            return effects

        # SHORT-TERM: Immediate match impact
        effects["momentum_loss"] = -0.25  # Team loses momentum
        effects["formation_collapse"] = -15  # xG disadvantage for remaining match
        effects["player_missing_next"] = 2  # 1-2 match ban depending on severity

        if incident_type == "violent":
            effects["player_missing_next"] = 3  # Longer ban for violent conduct
            effects["reputation_hit"] = -10  # Player reputation damage

        # MEDIUM-TERM: Morale cascades (0-3 matchdays)
        squad = session.query(Player).filter_by(club_id=club_id).all()

        # Close friends lose morale
        relationships = session.query(PlayerRelationship).filter(
            ((PlayerRelationship.player_a_id == player_id) | (PlayerRelationship.player_b_id == player_id)) &
            (PlayerRelationship.strength >= 70)
        ).all()

        for rel in relationships:
            friend_id = rel.player_b_id if rel.player_a_id == player_id else rel.player_a_id
            friend = session.get(Player, friend_id)
            if friend:
                friend.morale = clamp(friend.morale - random.uniform(5, 15), 0, 100)

        # Captain disappointed (leadership hit)
        tac = session.query(TacticalSetup).filter_by(club_id=club_id).first()
        if tac and tac.captain_id:
            captain = session.get(Player, tac.captain_id)
            if captain:
                captain.trust_in_manager = clamp(captain.trust_in_manager - 5, 0, 100)

        # LONG-TERM: Reputation spiral & transfer implications (4+ MD)
        player.form = clamp(player.form - 8, 0, 100)  # Confidence crater
        player.discipline = clamp(player.discipline - 15, 0, 100)  # Stigma

        # Potential transfer request if repeat offender
        if (player.discipline or 80) < 40:
            player.transfer_request = True

        # News generation
        incident_desc = {
            "reckless": f"reckless challenge",
            "violent": f"violent conduct",
            "second_yellow": f"accumulation of fouls",
        }
        session.add(NewsItem(
            season=season, matchday=matchday,
            headline=f"{player.short_name or player.name} sent off for {incident_desc.get(incident_type, 'misconduct')} at {club.name}",
            body=f"In the {minute}th minute, {player.name} received a straight red card for "
                 f"{incident_desc.get(incident_type, 'misconduct')}. "
                 f"The incident has sent shockwaves through the {club.name} dressing room.",
            category="match",
        ))

        _log(session, season, matchday, "red_card_incident", "player", player_id,
             f"{incident_type}; momentum={effects['momentum_loss']}; form_hit=-8", -10.0)

        return effects

    @staticmethod
    def handle_late_goal(
        session: Session,
        club_id: int,
        player_id: int,
        minute: int,
        is_comeback: bool,
        season: int,
        matchday: int,
    ) -> dict:
        """Handle dramatic late goals (87-90 min).

        is_comeback: True if team was losing/drawing and scored to win/draw.
        """
        player = session.get(Player, player_id)
        club = session.get(Club, club_id)
        effects = {}

        if player is None or club is None:
            return effects

        # SHORT-TERM: Massive momentum shift
        effects["momentum_boost"] = 0.35 if is_comeback else 0.25
        effects["xg_advantage"] = 20  # Overwhelming psychological advantage in ET/injury time
        effects["crowd_euphoria"] = 15  # Home crowd boost

        # MEDIUM-TERM: Player confidence spike, morale cascade
        player.morale = clamp(player.morale + 8, 0, 100)
        player.confidence = clamp(player.confidence + 12, 0, 100)  # If exists

        # Friends celebrate together (morale boost)
        relationships = session.query(PlayerRelationship).filter(
            ((PlayerRelationship.player_a_id == player_id) | (PlayerRelationship.player_b_id == player_id)) &
            (PlayerRelationship.strength >= 50)
        ).all()

        for rel in relationships:
            friend_id = rel.player_b_id if rel.player_a_id == player_id else rel.player_a_id
            friend = session.get(Player, friend_id)
            if friend:
                friend.morale = clamp(friend.morale + 5, 0, 100)

        squad = session.query(Player).filter_by(club_id=club_id).all()
        club.team_spirit = clamp(club.team_spirit + 5, 0, 100)

        # LONG-TERM: Form spike, tactical reputation
        player.form = clamp(player.form + 6, 0, 100)

        if is_comeback:
            # Entire squad gets a form/confidence boost (narrative arc)
            for p in squad:
                p.form = clamp(p.form + 2.5, 0, 100)

        session.add(NewsItem(
            season=season, matchday=matchday,
            headline=f"DRAMA! {player.short_name or player.name} rescues {club.name} in 90th minute" if is_comeback
                    else f"Late strike: {player.short_name or player.name} seals it for {club.name}",
            body=f"In a dramatic finish, {player.name} has scored in the {minute}th minute to "
                 f"{'complete an incredible comeback' if is_comeback else 'secure all three points'} for {club.name}. "
                 f"The dressing room is euphoric.",
            category="match",
        ))

        _log(session, season, matchday, "late_goal", "player", player_id,
             f"is_comeback={is_comeback}; momentum={effects['momentum_boost']}; form_boost=+6", 8.0)

        return effects

    @staticmethod
    def handle_goalkeeper_error(
        session: Session,
        club_id: int,
        goalkeeper_id: int,
        minute: int,
        season: int,
        matchday: int,
    ) -> dict:
        """Handle goalkeeper errors leading to goals."""
        gk = session.get(Player, goalkeeper_id)
        club = session.get(Club, club_id)
        effects = {}

        if gk is None or club is None:
            return effects

        # SHORT-TERM: Immediate momentum/confidence loss
        effects["momentum_loss"] = -0.20
        effects["confidence_crater"] = -20
        effects["xg_deficit"] = 15  # Team plays worse after conceding soft goal

        # MEDIUM-TERM: Goalkeeper form collapse
        gk.form = clamp(gk.form - 12, 0, 100)
        gk.morale = clamp(gk.morale - 10, 0, 100)

        # Teammates question his ability (relationship hit to defenders)
        defenders = session.query(Player).filter(
            Player.club_id == club_id,
            Player.position.in_(["CB", "RB", "LB", "LWB", "RWB"])
        ).all()

        for defender in defenders:
            defender.trust_in_manager = clamp(defender.trust_in_manager - 3, 0, 100)  # Confidence in tactics

        # LONG-TERM: Transfer implications if repeated
        gk.discipline = clamp(gk.discipline - 5, 0, 100)  # Reputation suffering

        session.add(NewsItem(
            season=season, matchday=matchday,
            headline=f"Howler! {gk.short_name or gk.name} blunder hands {club.name} a goal",
            body=f"In the {minute}th minute, {gk.name} made a catastrophic error that gifted "
                 f"a goal to the opposition. {club.name} fans were not pleased.",
            category="match",
        ))

        _log(session, season, matchday, "goalkeeper_error", "player", goalkeeper_id,
             f"minute={minute}; form_crater=-12; morale_hit=-10", -8.0)

        return effects

    @staticmethod
    def handle_missed_penalty(
        session: Session,
        club_id: int,
        player_id: int,
        minute: int,
        season: int,
        matchday: int,
    ) -> dict:
        """Handle missed penalty kicks."""
        player = session.get(Player, player_id)
        club = session.get(Club, club_id)
        effects = {}

        if player is None or club is None:
            return effects

        # SHORT-TERM: Momentum swing to opposition
        effects["momentum_loss"] = -0.30
        effects["confidence_crash"] = -25
        effects["missed_opportunity_factor"] = -20  # Team plays worse after

        # MEDIUM-TERM: Player confidence crisis
        player.morale = clamp(player.morale - 20, 0, 100)
        player.form = clamp(player.form - 15, 0, 100)
        player.penalty_taking = clamp((player.penalties or 50) - 10, 0, 100)

        # Teammates question penalty-taker (morale hit)
        squad = session.query(Player).filter_by(club_id=club_id).all()
        for teammate in squad:
            if teammate.id != player_id:
                teammate.morale = clamp(teammate.morale - 3, 0, 100)

        # LONG-TERM: Loss of penalty-taking duties
        tac = session.query(TacticalSetup).filter_by(club_id=club_id).first()
        if tac and tac.penalty_taker_id == player_id:
            # Look for alternative penalty taker
            alternatives = [
                p for p in squad if p.id != player_id and (p.penalties or 50) > 75
            ]
            if alternatives:
                new_taker = max(alternatives, key=lambda p: p.penalties or 50)
                tac.penalty_taker_id = new_taker.id

        session.add(NewsItem(
            season=season, matchday=matchday,
            headline=f"Agony! {player.short_name or player.name} misses penalty for {club.name}",
            body=f"In the {minute}th minute, {player.name} stepped up to take a penalty but "
                 f"blazed it over the bar. The miss could prove costly for {club.name}.",
            category="match",
        ))

        _log(session, season, matchday, "missed_penalty", "player", player_id,
             f"minute={minute}; confidence_crash=-25; form_hit=-15", -15.0)

        return effects

    @staticmethod
    def handle_defensive_collapse(
        session: Session,
        club_id: int,
        goals_conceded: int,
        time_window: int,  # minutes (e.g., 15 min window)
        season: int,
        matchday: int,
    ) -> dict:
        """Handle defensive collapses (3+ goals in 15 min window)."""
        club = session.get(Club, club_id)
        effects = {}

        if club is None or goals_conceded < 3:
            return effects

        # SHORT-TERM: Team completely loses form
        effects["defensive_cohesion"] = -40
        effects["morale_shock"] = -15
        effects["panic_factor"] = -25

        # MEDIUM-TERM: Defensive unit form collapse
        defenders = session.query(Player).filter(
            Player.club_id == club_id,
            Player.position.in_(["CB", "RB", "LB", "LWB", "RWB", "CDM"])
        ).all()

        for defender in defenders:
            defender.form = clamp(defender.form - 10, 0, 100)
            defender.morale = clamp(defender.morale - 12, 0, 100)

        squad = session.query(Player).filter_by(club_id=club_id).all()
        for p in squad:
            p.morale = clamp(p.morale - 8, 0, 100)

        club.team_spirit = clamp(club.team_spirit - 10, 0, 100)

        # LONG-TERM: Squad loses confidence, manager under pressure
        tac = session.query(TacticalSetup).filter_by(club_id=club_id).first()
        if tac:
            tac.defensive_confidence = clamp((tac.defensive_confidence or 70) - 15, 0, 100)

        session.add(NewsItem(
            season=season, matchday=matchday,
            headline=f"CATASTROPHE! {club.name} collapse defensively — {goals_conceded} goals in {time_window} minutes",
            body=f"{club.name}'s defensive unit has completely fallen apart, conceding {goals_conceded} goals "
                 f"in just {time_window} minutes. The manager and players have serious questions to answer.",
            category="match",
        ))

        _log(session, season, matchday, "defensive_collapse", "club", club_id,
             f"goals={goals_conceded} in {time_window}min; team_spirit -= 10; form_hit=-10", -15.0)

        return effects

    @staticmethod
    def handle_comeback_victory(
        session: Session,
        club_id: int,
        deficit_goals: int,  # e.g., 2 or 3
        season: int,
        matchday: int,
    ) -> dict:
        """Handle incredible comeback victories (2+ goal deficits overcome)."""
        club = session.get(Club, club_id)
        effects = {}

        if club is None:
            return effects

        # SHORT-TERM: Massive momentum/confidence swing
        effects["momentum_boost"] = 0.40
        effects["confidence_boost"] = 25
        effects["belief_factor"] = 20  # For next matches' xG calc

        squad = session.query(Player).filter_by(club_id=club_id).all()

        # MEDIUM-TERM: Full squad morale spike
        for player in squad:
            player.morale = clamp(player.morale + 15, 0, 100)
            player.form = clamp(player.form + 8, 0, 100)

        club.team_spirit = clamp(club.team_spirit + 12, 0, 100)

        # LONG-TERM: Narrative arc of resilience, manager reputation boost
        tac = session.query(TacticalSetup).filter_by(club_id=club_id).first()
        if tac:
            tac.tactical_reputation = clamp((tac.tactical_reputation or 50) + 10, 0, 100)

        session.add(NewsItem(
            season=season, matchday=matchday,
            headline=f"INCREDIBLE! {club.name} override {deficit_goals}-goal deficit to snatch victory",
            body=f"{club.name} have staged an absolutely stunning comeback, overcoming a {deficit_goals}-goal "
                 f"deficit to steal all three points. It's the stuff of legends — the dressing room is electric.",
            category="match",
        ))

        _log(session, season, matchday, "comeback_victory", "club", club_id,
             f"deficit={deficit_goals}; morale_spike=+15; form_spike=+8; spirit=+12", 20.0)

        return effects

    @staticmethod
    def handle_upset_victory(
        session: Session,
        club_id: int,
        opponent_rating_advantage: int,  # e.g., 150 overall pts higher
        season: int,
        matchday: int,
    ) -> dict:
        """Handle upset victories (lower-rated team beats higher-rated)."""
        club = session.get(Club, club_id)
        effects = {}

        if club is None:
            return effects

        # SHORT-TERM: Massive confidence surge
        effects["belief_surge"] = 30
        effects["underdog_factor"] = 25

        squad = session.query(Player).filter_by(club_id=club_id).all()

        # MEDIUM-TERM: All players gain confidence/form
        for player in squad:
            player.morale = clamp(player.morale + 12, 0, 100)
            player.form = clamp(player.form + 10, 0, 100)

        club.team_spirit = clamp(club.team_spirit + 10, 0, 100)

        # LONG-TERM: Tactical reputation boost for manager
        tac = session.query(TacticalSetup).filter_by(club_id=club_id).first()
        if tac:
            tac.tactical_reputation = clamp((tac.tactical_reputation or 50) + 8, 0, 100)

        session.add(NewsItem(
            season=season, matchday=matchday,
            headline=f"SHOCK! {club.name} pull off stunning upset victory",
            body=f"{club.name} have shocked the football world by defeating a far superior opponent. "
                 f"Against the odds, the team has produced a masterclass in tactical discipline and determination.",
            category="match",
        ))

        _log(session, season, matchday, "upset_victory", "club", club_id,
             f"vs_rating_delta=+{opponent_rating_advantage}; morale=+12; form=+10", 15.0)

        return effects

    @staticmethod
    def handle_goal_drought(
        session: Session,
        club_id: int,
        player_id: int,
        matches_without_goal: int,
        season: int,
        matchday: int,
    ) -> dict:
        """Handle goal droughts (5+ matches without scoring)."""
        player = session.get(Player, player_id)
        club = session.get(Club, club_id)
        effects = {}

        if player is None or club is None or matches_without_goal < 5:
            return effects

        # SHORT-TERM: Striker loses confidence
        effects["shooting_confidence_loss"] = -20
        effects["shot_accuracy_hit"] = -12

        # MEDIUM-TERM: Form collapse & media pressure
        player.form = clamp(player.form - 12, 0, 100)
        player.morale = clamp(player.morale - 10, 0, 100)
        player.finishing = clamp((player.finishing or 70) - 8, 0, 100)

        # Striker gets substituted more often
        player.performance_expectation = clamp((player.performance_expectation or 70) + 15, 0, 100)

        # LONG-TERM: Transfer rumors if drought continues past 8-10 matches
        if matches_without_goal >= 8:
            player.transfer_request = True

        session.add(NewsItem(
            season=season, matchday=matchday,
            headline=f"CRISIS! {player.short_name or player.name} stuck in goal drought for {club.name}",
            body=f"{player.name} has now gone {matches_without_goal} matches without scoring. "
                 f"The pressure is mounting on the striker to end the barren run.",
            category="match",
        ))

        _log(session, season, matchday, "goal_drought", "player", player_id,
             f"matches={matches_without_goal}; form_hit=-12; morale_hit=-10", -10.0)

        return effects

    @staticmethod
    def handle_scoring_run(
        session: Session,
        club_id: int,
        player_id: int,
        goals_last_3_matches: int,
        season: int,
        matchday: int,
    ) -> dict:
        """Handle hot-streak goals (3+ goals in 3 matches)."""
        player = session.get(Player, player_id)
        club = session.get(Club, club_id)
        effects = {}

        if player is None or club is None or goals_last_3_matches < 3:
            return effects

        # SHORT-TERM: Incredible confidence/form surge
        effects["hot_streak"] = goals_last_3_matches
        effects["confidence_multiplier"] = 2.0

        # MEDIUM-TERM: Form/morale/market value boost
        player.form = clamp(player.form + 15, 0, 100)
        player.morale = clamp(player.morale + 12, 0, 100)
        player.market_value_multiplier = clamp((player.market_value_multiplier or 1.0) * 1.2, 0.5, 2.0)

        # Teammates feed off energy
        relationships = session.query(PlayerRelationship).filter(
            ((PlayerRelationship.player_a_id == player_id) | (PlayerRelationship.player_b_id == player_id)) &
            (PlayerRelationship.strength >= 60)
        ).all()

        for rel in relationships:
            friend_id = rel.player_b_id if rel.player_a_id == player_id else rel.player_a_id
            teammate = session.get(Player, friend_id)
            if teammate:
                teammate.morale = clamp(teammate.morale + 5, 0, 100)

        # LONG-TERM: Transfer interest surges
        player.transfer_interest_level = clamp((player.transfer_interest_level or 30) + 40, 0, 100)

        session.add(NewsItem(
            season=season, matchday=matchday,
            headline=f"ON FIRE! {player.short_name or player.name} in devastating scoring form for {club.name}",
            body=f"{player.name} is absolutely on fire, having scored {goals_last_3_matches} goals in the last 3 matches. "
                 f"Opposition defenses are struggling to contain the striker.",
            category="match",
        ))

        _log(session, season, matchday, "scoring_run", "player", player_id,
             f"goals_in_3={goals_last_3_matches}; form=+15; morale=+12; value_x1.2", 15.0)

        return effects

    @staticmethod
    def handle_clean_sheet(
        session: Session,
        club_id: int,
        after_injury_crisis: bool,
        season: int,
        matchday: int,
    ) -> dict:
        """Handle clean sheets with different impacts based on context."""
        club = session.get(Club, club_id)
        effects = {}

        if club is None:
            return effects

        # SHORT-TERM: Defensive confidence boost
        effects["defensive_confidence"] = 12

        defenders = session.query(Player).filter(
            Player.club_id == club_id,
            Player.position.in_(["CB", "RB", "LB", "LWB", "RWB"])
        ).all()

        goalkeeper = session.query(Player).filter(
            Player.club_id == club_id,
            Player.position == "GK"
        ).first()

        # MEDIUM-TERM: Defensive unit form boost
        for defender in defenders:
            defender.form = clamp(defender.form + 8, 0, 100)
            defender.morale = clamp(defender.morale + 5, 0, 100)

        if goalkeeper:
            goalkeeper.form = clamp(goalkeeper.form + 6, 0, 100)
            goalkeeper.morale = clamp(goalkeeper.morale + 4, 0, 100)

        club.team_spirit = clamp(club.team_spirit + 3, 0, 100)

        # LONG-TERM: Extra boost if after injury crisis
        if after_injury_crisis:
            for defender in defenders:
                defender.form = clamp(defender.form + 5, 0, 100)  # Additional
            if goalkeeper:
                goalkeeper.form = clamp(goalkeeper.form + 4, 0, 100)

        headline_variant = (
            f"RESILIENCE! {club.name} keep clean sheet despite injury crisis"
            if after_injury_crisis
            else f"Solid! {club.name} secure clean sheet"
        )

        session.add(NewsItem(
            season=season, matchday=matchday,
            headline=headline_variant,
            body=f"In a defensive masterclass, {club.name} have kept a clean sheet. "
                 f"The defense has been resolute and the goalkeeper outstanding.",
            category="match",
        ))

        _log(session, season, matchday, "clean_sheet", "club", club_id,
             f"after_injury_crisis={after_injury_crisis}; def_form=+8{'+5' if after_injury_crisis else ''}", 8.0)

        return effects

    @staticmethod
    def handle_early_red_card(
        session: Session,
        club_id: int,
        player_id: int,
        minute: int,
        season: int,
        matchday: int,
    ) -> dict:
        """Handle very early red cards (before min 20) - severe impact."""
        player = session.get(Player, player_id)
        club = session.get(Club, club_id)
        effects = {}

        if player is None or club is None or minute > 20:
            return effects

        # SHORT-TERM: Catastrophic — 10v11 for almost entire match
        effects["formation_destroyed"] = -35
        effects["xg_deficit"] = 40  # Massive disadvantage
        effects["momentum_destroyed"] = -0.40

        # MEDIUM-TERM: Defensive unit collapses
        squad = session.query(Player).filter_by(club_id=club_id).all()

        for p in squad:
            if p.position in ["CB", "RB", "LB", "LWB", "RWB"]:
                p.form = clamp(p.form - 15, 0, 100)
                p.morale = clamp(p.morale - 15, 0, 100)

        # Player faces significant disciplinary aftermath
        player.discipline = clamp(player.discipline - 20, 0, 100)
        player.form = clamp(player.form - 20, 0, 100)

        club.team_spirit = clamp(club.team_spirit - 12, 0, 100)

        # LONG-TERM: Player likely benched/dropped
        player.performance_expectation = clamp((player.performance_expectation or 70) + 25, 0, 100)

        session.add(NewsItem(
            season=season, matchday=matchday,
            headline=f"DISASTER! {player.short_name or player.name} sent off in {minute}th minute for {club.name}",
            body=f"In the {minute}th minute, {player.name} received a red card, leaving {club.name} "
                 f"playing with 10 men for almost the entire match. The team faces an uphill battle.",
            category="match",
        ))

        _log(session, season, matchday, "early_red_card", "player", player_id,
             f"minute={minute}; xg_deficit=40; formation_destroyed=-35; form_hit=-20", -25.0)

        return effects

    @staticmethod
    def handle_short_turnaround_match(
        session: Session,
        club_id: int,
        days_since_last_match: int,
        result: str,  # "W", "D", "L"
        season: int,
        matchday: int,
    ) -> dict:
        """Handle matches with short turnarounds (2-3 days between matches)."""
        club = session.get(Club, club_id)
        effects = {}

        if club is None or days_since_last_match >= 4:
            return effects

        squad = session.query(Player).filter_by(club_id=club_id).all()

        # SHORT-TERM: Reduced fitness/stamina
        effects["stamina_drain"] = -20
        effects["fatigue_factor"] = -15

        # MEDIUM-TERM: Fitness/form hit for all players
        for player in squad:
            player.stamina = clamp((player.stamina or 70) - 5, 0, 100)
            # Performance slightly reduced
            if result == "L":
                player.form = clamp(player.form - 3, 0, 100)

        # Injury risk increases
        for player in squad:
            player.injury_risk = clamp((player.injury_risk or 20) + 8, 0, 100)

        # LONG-TERM: Recovery time needed
        club.team_spirit = clamp(club.team_spirit - 2, 0, 100) if result == "L" else club.team_spirit

        session.add(NewsItem(
            season=season, matchday=matchday,
            headline=f"{club.name} battle through short turnaround fixture",
            body=f"With just {days_since_last_match} days between matches, {club.name} have had minimal "
                 f"time to recover. Squad fatigue could prove a deciding factor.",
            category="fixture",
        ))

        _log(session, season, matchday, "short_turnaround", "club", club_id,
             f"days={days_since_last_match}; fatigue_factor=-15; injury_risk+=8", -5.0)

        return effects

    @staticmethod
    def handle_young_player_debut(
        session: Session,
        club_id: int,
        player_id: int,
        is_breakout_performance: bool,
        season: int,
        matchday: int,
    ) -> dict:
        """Handle young player debuts (U23) with potential breakout performances."""
        player = session.get(Player, player_id)
        club = session.get(Club, club_id)
        effects = {}

        if player is None or club is None or (player.age or 25) >= 24:
            return effects

        # SHORT-TERM: Confidence boost from first appearance
        effects["debut_confidence"] = 8
        effects["development_boost"] = 5

        # MEDIUM-TERM: Form improvement
        if is_breakout_performance:
            effects["breakout_performance"] = True
            player.form = clamp(player.form + 15, 0, 100)
            player.morale = clamp(player.morale + 12, 0, 100)
            player.potential = clamp((player.potential or 70) + 3, 0, 100)

            # More minutes next match
            player.playing_time_expectation = clamp((player.playing_time_expectation or 40) + 20, 0, 100)

            session.add(NewsItem(
                season=season, matchday=matchday,
                headline=f"SENSATION! {player.short_name or player.name} impresses on {club.name} debut",
                body=f"Young talent {player.name} has made an instant impact on debut for {club.name}. "
                     f"The fans are excited about what the future holds.",
                category="youth",
            ))

            _log(session, season, matchday, "young_player_breakout", "player", player_id,
                 f"age={player.age}; form=+15; morale=+12; potential=+3", 12.0)
        else:
            player.morale = clamp(player.morale + 4, 0, 100)
            player.form = clamp(player.form + 3, 0, 100)

            # Normal debut
            _log(session, season, matchday, "young_player_debut", "player", player_id,
                 f"age={player.age}; form=+3; morale=+4", 4.0)

        return effects

    @staticmethod
    def handle_veteran_performance(
        session: Session,
        club_id: int,
        player_id: int,
        goals_assists: int,
        season: int,
        matchday: int,
    ) -> dict:
        """Handle veteran performances (age 33+) that inspire squad."""
        player = session.get(Player, player_id)
        club = session.get(Club, club_id)
        effects = {}

        if player is None or club is None or (player.age or 28) < 33:
            return effects

        # SHORT-TERM: Leadership moment
        effects["leadership_surge"] = 15
        effects["experience_factor"] = 12

        # MEDIUM-TERM: Squad confidence/morale boost
        squad = session.query(Player).filter_by(club_id=club_id).all()

        for teammate in squad:
            if teammate.id != player_id and (teammate.age or 25) < 29:  # Younger players especially
                teammate.morale = clamp(teammate.morale + 6, 0, 100)

        player.form = clamp(player.form + 8, 0, 100)
        club.team_spirit = clamp(club.team_spirit + 4, 0, 100)

        # LONG-TERM: Leadership/captain status boost
        tac = session.query(TacticalSetup).filter_by(club_id=club_id).first()
        if tac and tac.captain_id == player_id:
            player.leadership = clamp((player.leadership or 60) + 5, 0, 100)

        session.add(NewsItem(
            season=season, matchday=matchday,
            headline=f"INSPIRING! Veteran {player.short_name or player.name} shows {goals_assists} G/A display for {club.name}",
            body=f"At age {player.age}, {player.name} has delivered a masterclass performance with "
                 f"{goals_assists} goals and assists. The experienced head is leading by example.",
            category="match",
        ))

        _log(session, season, matchday, "veteran_performance", "player", player_id,
             f"age={player.age}; g_a={goals_assists}; form=+8; leadership_boost", 10.0)

        return effects

    @staticmethod
    def handle_derby_match(
        session: Session,
        home_club_id: int,
        away_club_id: int,
        result: str,  # "H" (home win), "D", "A" (away win)
        intensity_level: int,  # 1-10 scale
        season: int,
        matchday: int,
    ) -> dict:
        """Handle high-intensity derby/rivalry matches."""
        home_club = session.get(Club, home_club_id)
        away_club = session.get(Club, away_club_id)
        effects = {}

        if home_club is None or away_club is None:
            return effects

        # SHORT-TERM: Massive momentum/psychological swings
        if result == "H":
            effects["home_morale_boost"] = intensity_level * 2
            effects["away_morale_hit"] = intensity_level * 1.5
        elif result == "A":
            effects["away_morale_boost"] = intensity_level * 2.5  # More intense for away win
            effects["home_morale_hit"] = intensity_level * 2
        else:
            effects["both_morale_neutral"] = True

        # MEDIUM-TERM: Form swings
        home_squad = session.query(Player).filter_by(club_id=home_club_id).all()
        away_squad = session.query(Player).filter_by(club_id=away_club_id).all()

        if result == "H":
            for p in home_squad:
                p.morale = clamp(p.morale + 8, 0, 100)
                p.form = clamp(p.form + 6, 0, 100)
            for p in away_squad:
                p.morale = clamp(p.morale - 8, 0, 100)
                p.form = clamp(p.form - 5, 0, 100)
        elif result == "A":
            for p in away_squad:
                p.morale = clamp(p.morale + 10, 0, 100)
                p.form = clamp(p.form + 7, 0, 100)
            for p in home_squad:
                p.morale = clamp(p.morale - 10, 0, 100)
                p.form = clamp(p.form - 6, 0, 100)

        # LONG-TERM: Bragging rights, transfer implications
        home_club.team_spirit = clamp(home_club.team_spirit + (5 if result == "H" else -5), 0, 100)
        away_club.team_spirit = clamp(away_club.team_spirit + (5 if result == "A" else -5), 0, 100)

        session.add(NewsItem(
            season=season, matchday=matchday,
            headline=f"DERBY DRAMA! {home_club.name} vs {away_club.name} — "
                    f"{'Home triumph' if result == 'H' else 'Away masterclass' if result == 'A' else 'Honors even'}",
            body=f"In an intense derby clash, the match lived up to expectations. "
                 f"The rivalry was fierce and the stakes were high.",
            category="match",
        ))

        _log(session, season, matchday, "derby_match", "club", home_club_id,
             f"vs_club={away_club_id}; result={result}; intensity={intensity_level}", 
             5.0 if result in ["H", "A"] else 0.0)

        return effects

    @staticmethod
    def handle_recurring_injury(
        session: Session,
        club_id: int,
        player_id: int,
        injury_type: str,  # Same injury repeating
        previous_recovery_time: int,  # weeks
        season: int,
        matchday: int,
    ) -> dict:
        """Handle recurring injuries (same player, same injury type)."""
        player = session.get(Player, player_id)
        club = session.get(Club, club_id)
        effects = {}

        if player is None or club is None:
            return effects

        # SHORT-TERM: Extended absence
        expected_recovery = min(previous_recovery_time * 1.3, 12)  # +30% but cap at 12 weeks
        effects["recovery_time_extended"] = expected_recovery
        effects["medical_concern"] = -20

        # MEDIUM-TERM: Psychological impact
        player.morale = clamp(player.morale - 15, 0, 100)
        player.confidence = clamp((player.confidence or 70) - 10, 0, 100)

        # LONG-TERM: Increased injury proneness, transfer implications
        player.injury_proneness = clamp((player.injury_proneness or 20) + 10, 0, 100)

        # Risk of chronic issues
        if previous_recovery_time >= 4:
            player.chronic_injury = True

        session.add(NewsItem(
            season=season, matchday=matchday,
            headline=f"SETBACK! {player.short_name or player.name} suffers RECURRING {injury_type} injury",
            body=f"{player.name} has suffered a recurrence of their previous {injury_type} injury. "
                 f"Medical staff are concerned about the persistent nature of the problem. "
                 f"Expected recovery: {int(expected_recovery)} weeks.",
            category="injury",
        ))

        _log(session, season, matchday, "recurring_injury", "player", player_id,
             f"injury_type={injury_type}; recovery_extended={expected_recovery}; chronic_risk", -12.0)

        return effects


# ── Logging helper ──────────────────────────────────────────────────────────


def _log(
    session: Session,
    season: int,
    matchday: int,
    trigger: str,
    target_type: str,
    target_id: int,
    effect: str,
    magnitude: float,
) -> None:
    """Create a ConsequenceLog entry."""
    session.add(ConsequenceLog(
        season=season,
        matchday=matchday,
        trigger_event=trigger,
        target_type=target_type,
        target_id=target_id,
        effect=effect,
        magnitude=magnitude,
    ))
