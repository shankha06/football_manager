"""Markov chain possession-based match simulator (V3 engine).

Each match is modelled as a series of possession chains (~300-350 per match).
Each chain starts from GOAL_KICK or TRANSITION and walks through states
using probabilities from the TransitionCalculator until reaching a
terminal state, at which point possession switches.
"""
from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING

from fm.config import (
    FATIGUE_PER_MINUTE,
    MATCH_MINUTES,
    SCORECARD_INTERVAL,
)
from fm.engine.chain_states import ChainState, TERMINAL_STATES
from fm.engine.commentary import Commentary
from fm.engine.match_state import (
    MatchResult,
    MatchState,
    PlayerInMatch,
    Scorecard,
)
from fm.engine.pitch import N_COLS, Pitch, ZoneCol, ZoneRow
from fm.engine.psychology import PsychologyEngine
from fm.engine.resolver_v3 import (
    ResolutionResult,
    resolve_cross,
    resolve_dribble,
    resolve_free_kick,
    resolve_header,
    resolve_interception,
    resolve_pass,
    resolve_penalty,
    resolve_shot_v3,
    resolve_tackle,
)
from fm.engine.tactics import TacticalContext
from fm.engine.transition_calculator import TransitionCalculator
from fm.utils.helpers import clamp

if TYPE_CHECKING:
    pass


class MarkovPossessionChain:
    """Main V3 match engine built on Markov possession chains."""

    def __init__(self, transition_calc: TransitionCalculator | None = None) -> None:
        self.transition_calc = transition_calc or TransitionCalculator()
        self.commentary = Commentary()
        self.psychology = PsychologyEngine()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def simulate(
        self,
        home_players: list[PlayerInMatch],
        away_players: list[PlayerInMatch],
        home_tactics: TacticalContext,
        away_tactics: TacticalContext,
        home_name: str = "Home",
        away_name: str = "Away",
        home_subs: list[PlayerInMatch] | None = None,
        away_subs: list[PlayerInMatch] | None = None,
        match_context: dict | None = None,
        pitch: Pitch | None = None,
    ) -> MatchResult:
        """Simulate a full match. Compatible with MatchSimulator.simulate() signature."""
        return self.simulate_match(
            home_players, away_players, home_tactics, away_tactics,
            match_context=match_context, pitch=pitch,
            home_name=home_name, away_name=away_name,
        )

    def simulate_match(
        self,
        home_players: list[PlayerInMatch],
        away_players: list[PlayerInMatch],
        home_tactics: TacticalContext,
        away_tactics: TacticalContext,
        match_context: dict | None = None,
        pitch: Pitch | None = None,
        home_name: str = "Home",
        away_name: str = "Away",
    ) -> MatchResult:
        """Simulate a full match and return the result.

        Args:
            home_players: Starting XI for home side.
            away_players: Starting XI for away side.
            home_tactics: Home team tactical instructions.
            away_tactics: Away team tactical instructions.
            match_context: Optional dict with ``"importance"``, etc.
            pitch: Optional Pitch instance (created if not provided).
            home_name: Display name for home team.
            away_name: Display name for away team.
        """
        # Accept both dict and MatchContext dataclass
        if match_context is None:
            ctx = {}
        elif isinstance(match_context, dict):
            ctx = match_context
        else:
            # Convert dataclass to dict
            from dataclasses import asdict
            try:
                ctx = asdict(match_context)
            except TypeError:
                ctx = {k: getattr(match_context, k, None) for k in dir(match_context) if not k.startswith('_')}
        if pitch is None:
            pitch = Pitch()

        state = MatchState(
            home_players=list(home_players),
            away_players=list(away_players),
        )

        # --- Assign zones to players ---
        self._assign_zones(state.home_players, home_tactics, "attack")
        self._assign_zones(state.away_players, away_tactics, "defend")
        pitch.clear_all()
        pitch.place_players(state.home_players, "home")
        pitch.place_players(state.away_players, "away")

        # --- Pre-compute initial transition matrices ---
        home_matrix = self._build_team_matrix(
            state.home_players, home_tactics, away_tactics, ctx, pitch, "home",
        )
        away_matrix = self._build_team_matrix(
            state.away_players, away_tactics, home_tactics, ctx, pitch, "away",
        )

        # --- Distribute chains across minutes ---
        total_chains = random.randint(160, 200)
        chains_per_minute = self._distribute_chains(total_chains, MATCH_MINUTES)

        # --- Main simulation loop ---
        possessing_side = "home"  # kick-off
        last_recompute = 0

        for minute in range(1, MATCH_MINUTES + 1):
            state.current_minute = minute

            # Recompute matrices periodically
            if minute - last_recompute >= self.transition_calc.recompute_interval:
                # Re-place players for updated zone control
                pitch.clear_all()
                self._assign_zones(state.home_players, home_tactics, "attack")
                self._assign_zones(state.away_players, away_tactics, "defend")
                pitch.place_players(state.home_players, "home")
                pitch.place_players(state.away_players, "away")

                home_matrix = self._build_team_matrix(
                    state.home_players, home_tactics, away_tactics, ctx, pitch, "home",
                )
                away_matrix = self._build_team_matrix(
                    state.away_players, away_tactics, home_tactics, ctx, pitch, "away",
                )
                last_recompute = minute

            # Process chains for this minute
            n_chains = chains_per_minute[minute - 1]
            for _ in range(n_chains):
                matrix = home_matrix if possessing_side == "home" else away_matrix
                start_state = ChainState.GOAL_KICK if random.random() < 0.5 else ChainState.TRANSITION

                possessing_side = self._run_chain(
                    state, matrix, possessing_side, start_state,
                    minute, pitch, home_tactics, away_tactics,
                    home_name, away_name, ctx,
                )

                # Track possession ticks
                if possessing_side == "home":
                    state.home_possession_ticks += 1
                else:
                    state.away_possession_ticks += 1

            # --- End-of-minute processing ---
            self._apply_fatigue(state, minute)
            self.psychology.decay_momentum()
            state._decay_momentum()

            # Update MatchState momentum from psychology engine
            state.home_momentum = self.psychology.momentum["home"]
            state.away_momentum = self.psychology.momentum["away"]

            # Scorecard every SCORECARD_INTERVAL minutes
            if minute % SCORECARD_INTERVAL == 0:
                state.scorecards.append(self._make_scorecard(state, minute))

            # Half-time commentary
            if minute == 45:
                state.commentary.append(
                    self.commentary.half_time(home_name, away_name, state.home_goals, state.away_goals)
                )

            # Update minutes played
            for p in state.home_players + state.away_players:
                if p.is_on_pitch and not p.red_card:
                    p.minutes_played = minute

        # --- Full time ---
        state.commentary.append(
            self.commentary.full_time(home_name, away_name, state.home_goals, state.away_goals)
        )

        # Final scorecard
        if MATCH_MINUTES % SCORECARD_INTERVAL != 0:
            state.scorecards.append(self._make_scorecard(state, MATCH_MINUTES))

        # Sync all player-level stats into MatchState team counters
        self._sync_stats_from_players(state)

        return state.to_result()

    # ------------------------------------------------------------------
    # Chain execution
    # ------------------------------------------------------------------

    def _run_chain(
        self,
        state: MatchState,
        matrix: dict[ChainState, dict[ChainState, float]],
        possessing_side: str,
        start_state: ChainState,
        minute: int,
        pitch: Pitch,
        home_tactics: TacticalContext,
        away_tactics: TacticalContext,
        home_name: str,
        away_name: str,
        ctx: dict,
    ) -> str:
        """Execute a single possession chain.  Returns the side that has
        possession after the chain ends."""
        current = start_state
        other_side = "away" if possessing_side == "home" else "home"
        att_players = state.home_players if possessing_side == "home" else state.away_players
        def_players = state.away_players if possessing_side == "home" else state.home_players
        att_tactics = home_tactics if possessing_side == "home" else away_tactics
        def_tactics = away_tactics if possessing_side == "home" else home_tactics
        team_name = home_name if possessing_side == "home" else away_name
        opp_name = away_name if possessing_side == "home" else home_name
        importance = ctx.get("importance", 1.0)

        max_steps = 20  # safety limit on chain length

        for _ in range(max_steps):
            if current in TERMINAL_STATES:
                break

            # Get transition probabilities for current state
            row = matrix.get(current)
            if not row:
                break

            # Apply snowball bonus
            snowball = self.psychology.get_snowball_bonus(possessing_side, minute)
            if snowball > 0 and current == ChainState.CHANCE_CREATION:
                row = dict(row)  # copy to avoid mutating matrix
                row[ChainState.SHOT] = row.get(ChainState.SHOT, 0.0) + snowball
                total = sum(row.values())
                row = {k: v / total for k, v in row.items()}

            # Sample next state
            current = self._sample_state(row)

            # --- Handle states that produce events ---
            if current == ChainState.SHOT:
                result = self._handle_shot(
                    state, att_players, def_players, att_tactics, possessing_side,
                    minute, pitch, team_name, opp_name, home_name, away_name, importance,
                )
                if result and result.success:
                    # Goal scored — chain ends
                    return other_side
                # Shot missed — end chain deterministically based on result
                # (don't let matrix re-roll GOAL, which would bypass the resolver)
                detail = result.detail if result else "off_target"
                if detail == "saved" or detail == "blocked":
                    # Corner or goal kick
                    if random.random() < 0.35:
                        state._inc(possessing_side, "corners")
                    break  # turnover
                else:
                    # Off target / woodwork → goal kick (possession to opponent)
                    break
                continue

            elif current == ChainState.CROSS:
                result = self._handle_cross(
                    state, att_players, def_players, att_tactics, possessing_side,
                    minute, pitch, team_name, opp_name, home_name, away_name, importance,
                )
                if result and result.success:
                    return other_side
                # Cross failed — turnover or corner
                break

            elif current == ChainState.PENALTY:
                self._handle_penalty(
                    state, att_players, def_players, att_tactics, possessing_side,
                    minute, team_name, opp_name, home_name, away_name,
                )
                return other_side

            elif current == ChainState.SET_PIECE_FK_DIRECT:
                # A foul was committed to produce this free kick
                state._inc(other_side, "fouls")
                fouler = self._select_player_for_zone(def_players, range(0, 4), ["CB", "CDM", "CM", "LB", "RB"])
                if fouler:
                    fouler.fouls_committed += 1
                fouled = self._select_player_for_zone(att_players, range(2, 6), ["CAM", "LW", "RW", "ST"])
                if fouled:
                    fouled.fouls_won += 1
                self._handle_free_kick(
                    state, att_players, def_players, att_tactics, possessing_side,
                    minute, team_name, opp_name, home_name, away_name,
                )
                return other_side

            elif current == ChainState.SET_PIECE_CORNER:
                state._inc(possessing_side, "corners")
                if random.random() < 0.3:
                    state.commentary.append(
                        self.commentary.corner(minute, team_name)
                    )
                return possessing_side  # retain possession for corner

            elif current == ChainState.SET_PIECE_FK_INDIRECT:
                # A foul was committed to produce this free kick
                state._inc(other_side, "fouls")
                fouler = self._select_player_for_zone(def_players, range(0, 4), ["CB", "CDM", "CM", "LB", "RB"])
                if fouler:
                    fouler.fouls_committed += 1
                fouled = self._select_player_for_zone(att_players, range(1, 5), ["CM", "CAM", "LW", "RW"])
                if fouled:
                    fouled.fouls_won += 1
                return possessing_side

            elif current == ChainState.TURNOVER:
                # Track pass attempts for the chain
                passer = self._select_player_for_zone(att_players, range(1, 4), ["CM", "CDM", "CAM"])
                if passer:
                    passer.passes_attempted += 1
                    state._inc(possessing_side, "passes")

                # Simulate a defensive action that caused the turnover
                self._simulate_defensive_action(
                    state, att_players, def_players, def_tactics,
                    possessing_side, other_side, minute,
                )
                return other_side

            elif current == ChainState.PRESS_TRIGGERED:
                # Commentary for press events
                if random.random() < 0.15:
                    presser = self._select_player_for_zone(def_players, range(2, 5), ["CM", "CDM", "ST"])
                    if presser:
                        state.commentary.append(
                            self.commentary.pressing_event(minute, opp_name, presser.name)
                        )

            elif current == ChainState.COUNTER_ATTACK:
                if random.random() < 0.20:
                    state.commentary.append(
                        self.commentary.counter_attack(minute, team_name)
                    )

            elif current == ChainState.BUILDUP_DEEP or current == ChainState.BUILDUP_MID:
                # Track successful passes during build-up
                passer = self._select_player_for_zone(att_players, range(1, 4), ["CB", "CM", "CDM"])
                if passer:
                    passer.passes_attempted += 1
                    passer.passes_completed += 1
                    state._inc(possessing_side, "passes")
                    state._inc(possessing_side, "passes_completed")

            elif current == ChainState.PROGRESSION:
                passer = self._select_player_for_zone(att_players, range(2, 5), ["CM", "CAM", "LW", "RW"])
                if passer:
                    passer.passes_attempted += 1
                    passer.passes_completed += 1
                    passer.key_passes += 1
                    state._inc(possessing_side, "passes")
                    state._inc(possessing_side, "passes_completed")
                    state._inc(possessing_side, "key_passes")

                # Dribble attempt during progression (~30% chance)
                if random.random() < 0.30:
                    dribbler = self._select_player_for_zone(
                        att_players, range(3, 6), ["LW", "RW", "CAM", "ST"],
                    )
                    opp_defender = self._select_player_for_zone(
                        def_players, range(0, 3), ["CB", "LB", "RB", "CDM"],
                    )
                    if dribbler:
                        resolve_dribble(dribbler, opp_defender, att_tactics)

        # Chain ended without a terminal state (safety limit)
        return possessing_side

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _handle_shot(
        self, state, att_players, def_players, att_tactics, side,
        minute, pitch, team_name, opp_name, home_name, away_name, importance,
    ) -> ResolutionResult | None:
        """Handle a SHOT chain state."""
        shooter = self._select_player_for_zone(
            att_players, range(3, 6), ["ST", "CF", "CAM", "LW", "RW"],
        )
        if not shooter:
            return None

        gk = self._find_gk(def_players)
        defender = self._select_player_for_zone(
            def_players, range(0, 3), ["CB", "LB", "RB"],
        )

        # Psychology modifiers
        psych_mods = self.psychology.get_individual_modifier(shooter, minute, importance)
        psych_mods["crowd_pressure"] = self.psychology.get_crowd_pressure(
            side, side == "home", importance,
        )

        result = resolve_shot_v3(
            shooter, gk, defender,
            shooter.zone_col, shooter.zone_row,
            att_tactics,
            psychology_mods=psych_mods,
        )

        # Track stats
        state._inc(side, "shots")
        state._inc(side, "xg", result.xg_value)

        if result.is_blocked:
            state._inc(side, "shots_blocked")
            return result

        if result.detail == "off_target":
            if result.hit_woodwork:
                state._inc(side, "woodwork")
                state.commentary.append(
                    self.commentary.woodwork(minute, shooter.name, team_name)
                )
            return result

        if result.detail == "saved":
            state._inc(side, "sot")
            other = "away" if side == "home" else "home"
            state._inc(other, "saves")
            if gk:
                state.commentary.append(
                    self.commentary.save(minute, gk.name, shooter.name)
                )
                self.psychology.process_event("save", other, minute)
                state._update_momentum(other, "save")
            return result

        if result.success:
            # GOAL
            state._inc(side, "sot")
            if side == "home":
                state.home_goals += 1
            else:
                state.away_goals += 1

            # Find potential assister
            assister = self._select_player_for_zone(
                att_players, range(2, 5), ["CAM", "CM", "LW", "RW"],
            )
            assist_name = None
            if assister and assister.player_id != shooter.player_id:
                assister.assists += 1
                assister.rating_points += 0.3
                assister.rating_events += 1
                assist_name = assister.name

            # Check if equaliser
            is_eq = state.home_goals == state.away_goals

            state.commentary.append(
                self.commentary.goal(
                    minute, shooter.name, team_name,
                    assist_name=assist_name,
                    score_home=state.home_goals, score_away=state.away_goals,
                    home_name=home_name, away_name=away_name,
                    is_equaliser=is_eq,
                    detail=result.detail,
                )
            )

            state.events.append({
                "type": "goal", "minute": minute, "side": side,
                "player": shooter.name, "assist": assist_name,
                "xg": result.xg_value,
            })

            self.psychology.process_event("goal", side, minute)
            state._update_momentum(side, "goal")
            return result

        return result

    def _handle_cross(
        self, state, att_players, def_players, att_tactics, side,
        minute, pitch, team_name, opp_name, home_name, away_name, importance,
    ) -> ResolutionResult | None:
        """Handle a CROSS chain state — cross then header."""
        crosser = self._select_player_for_zone(
            att_players, range(3, 6), ["LW", "RW", "LB", "RB", "LM", "RM"],
        )
        if not crosser:
            return None

        target = self._select_player_for_zone(
            att_players, range(4, 6), ["ST", "CF", "CAM"],
        )
        defender = self._select_player_for_zone(
            def_players, range(0, 2), ["CB", "LB", "RB"],
        )

        cross_result = resolve_cross(crosser, target, defender, att_tactics)
        state._inc(side, "crosses")

        if not cross_result.success:
            return cross_result

        state._inc(side, "crosses_completed")

        if not target:
            return cross_result

        # Header attempt
        gk = self._find_gk(def_players)
        header_result = resolve_header(target, gk, defender, att_tactics)

        state._inc(side, "shots")
        state._inc(side, "xg", header_result.xg_value)

        if header_result.hit_woodwork:
            state._inc(side, "woodwork")
            state.commentary.append(
                self.commentary.woodwork(minute, target.name, team_name)
            )
            return header_result

        if header_result.detail == "saved":
            state._inc(side, "sot")
            other = "away" if side == "home" else "home"
            state._inc(other, "saves")
            if gk:
                state.commentary.append(
                    self.commentary.save(minute, gk.name, target.name)
                )
                self.psychology.process_event("save", other, minute)
            return header_result

        if header_result.success:
            state._inc(side, "sot")
            if side == "home":
                state.home_goals += 1
            else:
                state.away_goals += 1

            crosser.assists += 1
            crosser.rating_points += 0.3
            crosser.rating_events += 1

            state.commentary.append(
                self.commentary.header_goal(
                    minute, target.name, crosser.name, team_name,
                    state.home_goals, state.away_goals,
                    home_name, away_name,
                )
            )

            state.events.append({
                "type": "goal", "minute": minute, "side": side,
                "player": target.name, "assist": crosser.name,
                "xg": header_result.xg_value, "detail": "header",
            })

            self.psychology.process_event("goal", side, minute)
            state._update_momentum(side, "goal")
            return header_result

        return header_result

    def _handle_penalty(
        self, state, att_players, def_players, att_tactics, side,
        minute, team_name, opp_name, home_name, away_name,
    ) -> None:
        """Handle a PENALTY chain state."""
        # Find best penalty taker
        taker = max(
            [p for p in att_players if p.is_on_pitch and not p.red_card],
            key=lambda p: p.effective("penalties"),
            default=None,
        )
        if not taker:
            return

        gk = self._find_gk(def_players)

        state.commentary.append(self.commentary.penalty_awarded(minute, team_name))

        result = resolve_penalty(taker, gk, att_tactics)
        state._inc(side, "shots")
        state._inc(side, "xg", result.xg_value)

        if result.success:
            state._inc(side, "sot")
            if side == "home":
                state.home_goals += 1
            else:
                state.away_goals += 1

            state.commentary.append(
                self.commentary.goal(
                    minute, taker.name, team_name,
                    score_home=state.home_goals, score_away=state.away_goals,
                    home_name=home_name, away_name=away_name,
                    detail="penalty_goal",
                )
            )
            state.events.append({
                "type": "goal", "minute": minute, "side": side,
                "player": taker.name, "detail": "penalty",
                "xg": result.xg_value,
            })
            self.psychology.process_event("goal", side, minute)
            state._update_momentum(side, "goal")
        else:
            state.commentary.append(
                self.commentary.penalty_missed(minute, taker.name, team_name)
            )
            self.psychology.process_event("miss_big_chance", side, minute)

    def _handle_free_kick(
        self, state, att_players, def_players, att_tactics, side,
        minute, team_name, opp_name, home_name, away_name,
    ) -> None:
        """Handle a direct free kick."""
        taker = max(
            [p for p in att_players if p.is_on_pitch and not p.red_card],
            key=lambda p: p.effective("free_kick_accuracy"),
            default=None,
        )
        if not taker:
            return

        gk = self._find_gk(def_players)
        defender = self._select_player_for_zone(
            def_players, range(0, 3), ["CB"],
        )

        distance = random.uniform(1.0, 3.0)
        result = resolve_free_kick(taker, gk, defender, distance, att_tactics)

        state._inc(side, "shots")
        state._inc(side, "xg", result.xg_value)

        if result.success:
            state._inc(side, "sot")
            if side == "home":
                state.home_goals += 1
            else:
                state.away_goals += 1

            state.commentary.append(
                self.commentary.goal(
                    minute, taker.name, team_name,
                    score_home=state.home_goals, score_away=state.away_goals,
                    home_name=home_name, away_name=away_name,
                    detail="free_kick_goal",
                )
            )
            state.events.append({
                "type": "goal", "minute": minute, "side": side,
                "player": taker.name, "detail": "free_kick",
                "xg": result.xg_value,
            })
            self.psychology.process_event("goal", side, minute)
            state._update_momentum(side, "goal")
        elif result.detail == "saved" and gk:
            state._inc(side, "sot")
            other = "away" if side == "home" else "home"
            state._inc(other, "saves")
            state.commentary.append(
                self.commentary.save(minute, gk.name, taker.name)
            )

    # ------------------------------------------------------------------
    # Defensive action simulation & stat sync
    # ------------------------------------------------------------------

    def _simulate_defensive_action(
        self,
        state: MatchState,
        att_players: list[PlayerInMatch],
        def_players: list[PlayerInMatch],
        def_tactics: TacticalContext,
        att_side: str,
        def_side: str,
        minute: int,
    ) -> None:
        """Simulate a defensive action (tackle or interception) on turnover."""
        defender = self._select_player_for_zone(
            def_players, range(0, 4), ["CB", "CDM", "CM", "LB", "RB"],
        )
        ball_carrier = self._select_player_for_zone(
            att_players, range(1, 5), ["CM", "CAM", "LW", "RW", "ST"],
        )
        if not defender or not ball_carrier:
            return

        if random.random() < 0.5:
            # Tackle attempt
            result = resolve_tackle(defender, ball_carrier, def_tactics)
            if result.is_foul:
                state._inc(def_side, "fouls")
                if result.is_yellow:
                    defender.yellow_cards += 1
                    state._inc(def_side, "yellow_cards")
                elif result.is_red:
                    defender.red_card = True
                    state._inc(def_side, "red_cards")
        else:
            # Interception attempt
            resolve_interception(defender, ball_carrier, random.uniform(1.0, 3.0))

        # Occasionally add a clearance for defenders in their own half
        if random.random() < 0.15:
            clearer = self._select_player_for_zone(
                def_players, range(0, 2), ["CB", "LB", "RB"],
            )
            if clearer:
                clearer.clearances += 1

    @staticmethod
    def _sync_stats_from_players(state: MatchState) -> None:
        """Aggregate all PlayerInMatch stats into MatchState team counters.

        This runs once at end-of-match so that MatchState accurately reflects
        every individual player stat accumulated by the resolvers.  It
        *overwrites* the team counters with the sum of player stats to avoid
        double-counting.
        """
        for side in ("home", "away"):
            players = state.home_players if side == "home" else state.away_players
            # Shooting
            setattr(state, f"{side}_shots", sum(p.shots for p in players))
            setattr(state, f"{side}_sot", sum(p.shots_on_target for p in players))
            setattr(state, f"{side}_shots_blocked", sum(p.shots_blocked for p in players))
            setattr(state, f"{side}_woodwork", sum(p.hit_woodwork for p in players))
            setattr(state, f"{side}_big_chances", sum(p.big_chances for p in players))
            setattr(state, f"{side}_big_chances_missed", sum(p.big_chances_missed for p in players))
            # Passing — keep the higher of incremental counters vs player sums
            # (some passes are tracked at team level in build-up without resolver)
            setattr(state, f"{side}_passes", max(
                getattr(state, f"{side}_passes"),
                sum(p.passes_attempted for p in players),
            ))
            setattr(state, f"{side}_passes_completed", max(
                getattr(state, f"{side}_passes_completed"),
                sum(p.passes_completed for p in players),
            ))
            setattr(state, f"{side}_key_passes", max(
                getattr(state, f"{side}_key_passes"),
                sum(p.key_passes for p in players),
            ))
            # Crossing
            setattr(state, f"{side}_crosses", sum(p.crosses_attempted for p in players))
            setattr(state, f"{side}_crosses_completed", sum(p.crosses_completed for p in players))
            # Dribbling
            setattr(state, f"{side}_dribbles", sum(p.dribbles_attempted for p in players))
            setattr(state, f"{side}_dribbles_completed", sum(p.dribbles_completed for p in players))
            # Defensive
            setattr(state, f"{side}_tackles", sum(p.tackles_attempted for p in players))
            setattr(state, f"{side}_tackles_won", sum(p.tackles_won for p in players))
            setattr(state, f"{side}_interceptions", sum(p.interceptions_made for p in players))
            setattr(state, f"{side}_clearances", sum(p.clearances for p in players))
            setattr(state, f"{side}_blocks", sum(p.blocks for p in players))
            # Aerial
            setattr(state, f"{side}_aerials_won", sum(p.aerials_won for p in players))
            setattr(state, f"{side}_aerials_lost", sum(p.aerials_lost for p in players))
            # Discipline
            setattr(state, f"{side}_fouls", max(
                getattr(state, f"{side}_fouls"),
                sum(p.fouls_committed for p in players),
            ))
            setattr(state, f"{side}_offsides", sum(p.offsides_count for p in players))
            setattr(state, f"{side}_yellow_cards", sum(p.yellow_cards for p in players))
            setattr(state, f"{side}_red_cards", sum(1 for p in players if p.red_card))
            # GK
            setattr(state, f"{side}_saves", sum(p.saves for p in players))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_team_matrix(
        self,
        players: list[PlayerInMatch],
        own_tactics: TacticalContext,
        opp_tactics: TacticalContext,
        ctx: dict,
        pitch: Pitch,
        side: str,
    ) -> dict[ChainState, dict[ChainState, float]]:
        """Build transition matrix for one team."""
        active = [p for p in players if p.is_on_pitch and not p.red_card]

        # Compute average attributes by area
        def_players = [p for p in active if p.zone_col <= 1]
        mid_players = [p for p in active if 2 <= p.zone_col <= 3]
        att_players = [p for p in active if p.zone_col >= 4]

        def _avg(plist, attr):
            if not plist:
                return 50.0
            return sum(p.effective(attr) for p in plist) / len(plist)

        team_attrs = {
            "def_avg": (_avg(def_players, "defending") + _avg(def_players, "passing")) / 2,
            "mid_avg": (_avg(mid_players, "passing") + _avg(mid_players, "vision")) / 2,
            "att_avg": (_avg(att_players, "finishing") + _avg(att_players, "dribbling")) / 2,
        }

        # Zone control
        zone_control: dict[tuple[int, int], float] = {}
        for c in range(N_COLS):
            for r in range(3):
                zone_control[(c, r)] = pitch.get(c, r).control_ratio(side)

        # Match context for this side
        fatigue_avg = sum(p.stamina_current for p in active) / max(len(active), 1)
        match_ctx = {
            "momentum": self.psychology.momentum.get(side, 0.0),
            "fatigue_avg": fatigue_avg,
            "morale": sum(p.morale_mod for p in active) / max(len(active), 1),
        }

        return self.transition_calc.build_matrix(
            team_attrs, own_tactics, match_ctx, zone_control, opp_tactics,
        )

    @staticmethod
    def _sample_state(row: dict[ChainState, float]) -> ChainState:
        """Sample a next state from a probability distribution row."""
        r = random.random()
        cumulative = 0.0
        for state, prob in row.items():
            cumulative += prob
            if r < cumulative:
                return state
        # Fallback (shouldn't happen with normalized rows)
        return list(row.keys())[-1]

    @staticmethod
    def _select_player_for_zone(
        players: list[PlayerInMatch],
        zone_col_range: range,
        preferred_positions: list[str],
    ) -> PlayerInMatch | None:
        """Select a player from the given zone range, preferring certain positions."""
        active = [p for p in players if p.is_on_pitch and not p.red_card]

        # First try: matching zone AND position
        candidates = [
            p for p in active
            if p.zone_col in zone_col_range and p.position in preferred_positions
        ]
        if candidates:
            return random.choice(candidates)

        # Second try: matching zone only
        candidates = [p for p in active if p.zone_col in zone_col_range]
        if candidates:
            return random.choice(candidates)

        # Third try: matching position only
        candidates = [p for p in active if p.position in preferred_positions]
        if candidates:
            return random.choice(candidates)

        # Last resort: any active player
        if active:
            return random.choice(active)
        return None

    @staticmethod
    def _find_gk(players: list[PlayerInMatch]) -> PlayerInMatch | None:
        """Find the goalkeeper in a player list."""
        for p in players:
            if p.is_gk and p.is_on_pitch:
                return p
        return None

    @staticmethod
    def _assign_zones(
        players: list[PlayerInMatch],
        tactics: TacticalContext,
        phase: str,
    ) -> None:
        """Assign zone positions to players based on formation and phase."""
        if phase == "attack":
            zones = tactics.attacking_zones()
        else:
            zones = tactics.defending_zones()

        outfield_idx = 0
        for p in players:
            if p.is_gk:
                p.zone_col = ZoneCol.GK_AREA
                p.zone_row = ZoneRow.CENTER
                continue
            if not p.is_on_pitch or p.red_card:
                continue
            if outfield_idx < len(zones):
                p.zone_col, p.zone_row = zones[outfield_idx]
                outfield_idx += 1

    @staticmethod
    def _distribute_chains(total_chains: int, minutes: int) -> list[int]:
        """Distribute chains across minutes using a Poisson-like process.

        Returns a list of length *minutes* with chain counts per minute.
        """
        avg_per_min = total_chains / minutes
        result = []
        remaining = total_chains
        for m in range(minutes):
            if m == minutes - 1:
                result.append(remaining)
            else:
                # Poisson sample, clamped
                n = min(random.randint(
                    max(1, int(avg_per_min - 1)),
                    int(avg_per_min + 2),
                ), remaining)
                result.append(n)
                remaining -= n
        return result

    @staticmethod
    def _apply_fatigue(state: MatchState, minute: int) -> None:
        """Apply fatigue to all on-pitch players."""
        for p in state.home_players + state.away_players:
            if p.is_on_pitch and not p.red_card:
                p.stamina_current = max(0.0, p.stamina_current - FATIGUE_PER_MINUTE)

    @staticmethod
    def _make_scorecard(state: MatchState, minute: int) -> Scorecard:
        """Build a Scorecard snapshot at the given minute."""
        return Scorecard(
            minute=minute,
            home_goals=state.home_goals,
            away_goals=state.away_goals,
            home_possession=state.home_possession_pct,
            away_possession=100.0 - state.home_possession_pct,
            home_shots=state.home_shots,
            away_shots=state.away_shots,
            home_sot=state.home_sot,
            away_sot=state.away_sot,
            home_xg=round(state.home_xg, 2),
            away_xg=round(state.away_xg, 2),
            home_passes=state.home_passes,
            away_passes=state.away_passes,
            home_fouls=state.home_fouls,
            away_fouls=state.away_fouls,
            home_corners=state.home_corners,
            away_corners=state.away_corners,
        )
