"""Main match simulator — tick-by-tick 90-minute simulation.

Orchestrates the pitch model, state machine, event resolver, and commentary
generator to produce a full MatchResult with 10-minute scorecards.
"""
from __future__ import annotations

import random
from typing import Optional

from fm.config import (
    TICKS_PER_MINUTE, MATCH_MINUTES, SCORECARD_INTERVAL,
    FATIGUE_PER_MINUTE, FATIGUE_SPRINT_COST, INJURY_BASE_CHANCE,
)
from fm.engine.match_state import (
    PlayerInMatch, MatchState, MatchResult, Scorecard,
)
from fm.engine.pitch import Pitch, ZoneCol, ZoneRow, N_COLS, N_ROWS
from fm.engine.tactics import TacticalContext, FORMATIONS
from fm.engine.resolver import (
    resolve_pass, resolve_dribble, resolve_shot, resolve_cross,
    resolve_header, resolve_tackle, resolve_interception,
    resolve_penalty, resolve_free_kick,
)
from fm.engine.commentary import Commentary
from fm.engine.match_engine import MatchRatingCalculator
from fm.utils.helpers import clamp, weighted_random_choice, zone_distance


class MatchSimulator:
    """Simulates a single match tick-by-tick."""

    def __init__(self):
        self.pitch = Pitch()
        self.commentary = Commentary()
        self._match_context = None

    # ── Public API ─────────────────────────────────────────────────────────

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
        match_context=None,
    ) -> MatchResult:
        """Run the full 90-minute simulation."""
        # Store match context for use in tick processing
        self._match_context = match_context

        # Apply context modifiers to players if context is provided
        if match_context is not None:
            home_kwargs = dict(
                morale_mod=match_context.home_morale_mod,
                form_mod=match_context.home_form_mod,
                sharpness=match_context.home_sharpness,
                cohesion_mod=match_context.home_cohesion_mod,
                home_boost=match_context.home_advantage,
                importance_mod=match_context.importance,
                weather_pass_pen=match_context.weather_passing_penalty(),
                weather_pace_pen=match_context.weather_pace_penalty(),
                weather_shoot_mod=match_context.weather_shooting_mod(),
                pitch_dribble_pen=match_context.pitch_dribble_penalty(),
            )
            away_kwargs = dict(
                morale_mod=match_context.away_morale_mod,
                form_mod=match_context.away_form_mod,
                sharpness=match_context.away_sharpness,
                cohesion_mod=match_context.away_cohesion_mod,
                home_boost=0.0,
                importance_mod=match_context.importance,
                weather_pass_pen=match_context.weather_passing_penalty(),
                weather_pace_pen=match_context.weather_pace_penalty(),
                weather_shoot_mod=match_context.weather_shooting_mod(),
                pitch_dribble_pen=match_context.pitch_dribble_penalty(),
            )
            for p in home_players:
                p.apply_context(**home_kwargs)
            for p in away_players:
                p.apply_context(**away_kwargs)

        state = MatchState(
            home_players=home_players,
            away_players=away_players,
            home_subs=home_subs or [],
            away_subs=away_subs or [],
        )

        # Initial kickoff
        state.ball_side = random.choice(["home", "away"])
        state.ball_zone_col = 3
        state.ball_zone_row = 1

        # Weather commentary at kickoff
        if match_context is not None:
            self._weather_kickoff_commentary(state, home_name, away_name)

        for minute in range(1, MATCH_MINUTES + 1):
            state.current_minute = minute

            # Reposition players for this minute (phase depends on possession)
            self._assign_zones(state, home_tactics, away_tactics)
            self.pitch.clear_all()
            self.pitch.place_players(
                [p for p in state.home_players if p.is_on_pitch], "home"
            )
            self.pitch.place_players(
                [p for p in state.away_players if p.is_on_pitch], "away"
            )

            for tick in range(TICKS_PER_MINUTE):
                self._process_tick(state, home_tactics, away_tactics,
                                   home_name, away_name)

            # Fatigue
            self._apply_fatigue(state, minute, home_tactics, away_tactics)

            # Per-minute weather effects
            if self._match_context is not None:
                self._apply_weather_effects(state, minute)

            # Morale events
            if self._match_context is not None:
                self._check_morale_events(state, minute, home_name, away_name)

            # Momentum decay each minute
            state._decay_momentum()

            # Half-time
            if minute == 45:
                state.commentary.append(
                    f"45' ── HALF TIME ── "
                    f"{home_name} {state.home_goals}-{state.away_goals} "
                    f"{away_name}"
                )
                # Partial momentum reset at half-time
                state.home_momentum *= 0.4
                state.away_momentum *= 0.4

            # Injury chance
            self._check_injuries(state, minute, home_name, away_name)

            # AI substitutions (for both sides)
            if minute >= 55:
                self._auto_subs(state, minute, home_name, away_name)

            # Scorecard every N minutes
            if minute % SCORECARD_INTERVAL == 0:
                sc = self._generate_scorecard(state, minute)
                state.scorecards.append(sc)

        # Stoppage time (1-5 extra ticks)
        extra = random.randint(1, 5)
        state.commentary.append(
            f"90' ⏱  {extra} minute(s) of added time."
        )
        for _ in range(extra * TICKS_PER_MINUTE):
            state.current_minute = 90
            self._process_tick(state, home_tactics, away_tactics,
                               home_name, away_name)

        # Clear match context at end
        self._match_context = None

        # Finalize ratings using the calculator (replaces raw accumulation)
        self._finalize_ratings(state)

        return state.to_result()

    def _finalize_ratings(self, state: MatchState) -> None:
        """Calculate final match ratings for all players."""
        calculator = MatchRatingCalculator()
        home_clean = state.away_goals == 0
        away_clean = state.home_goals == 0

        for p in state.home_players:
            p.rating_points = calculator.calculate(p)
            if home_clean and (p.is_gk or p.position in ("CB", "LB", "RB", "LWB", "RWB")):
                p.rating_points = min(p.rating_points + 0.5, 10.0)
            p.rating_events = 1

        for p in state.away_players:
            p.rating_points = calculator.calculate(p)
            if away_clean and (p.is_gk or p.position in ("CB", "LB", "RB", "LWB", "RWB")):
                p.rating_points = min(p.rating_points + 0.5, 10.0)
            p.rating_events = 1

    # ── Tick processing ────────────────────────────────────────────────────

    def _process_tick(
        self,
        state: MatchState,
        h_tac: TacticalContext,
        a_tac: TacticalContext,
        h_name: str,
        a_name: str,
    ):
        """Process a single simulation tick."""
        # Dynamic event rate modified by tactics and weather
        base_rate = 0.25
        # High tempo = more events
        base_rate += (h_tac.tempo_modifier + a_tac.tempo_modifier) * 0.05
        # High pressing = more events
        base_rate += (h_tac.press_modifier + a_tac.press_modifier) * 0.03
        # Weather: rain = more turnovers = more events
        if self._match_context is not None:
            weather_pen = 0.0
            if hasattr(self._match_context, "weather_passing_penalty"):
                weather_pen = self._match_context.weather_passing_penalty()
            base_rate += weather_pen * 0.1
        base_rate = max(0.15, min(0.40, base_rate))

        if random.random() > base_rate:
            if state.ball_side == "home":
                state.home_possession_ticks += 1
            else:
                state.away_possession_ticks += 1
            return

        # Track possession
        if state.ball_side == "home":
            state.home_possession_ticks += 1
            att_tactics = h_tac
            def_tactics = a_tac
            att_name = h_name
            def_name = a_name
        else:
            state.away_possession_ticks += 1
            att_tactics = a_tac
            def_tactics = h_tac
            att_name = a_name
            def_name = h_name

        attackers = state.get_attacking_players()
        defenders = state.get_defending_players()
        if not attackers:
            return

        carrier = state.ball_carrier
        if carrier is None or not carrier.is_on_pitch or carrier.red_card:
            carrier = random.choice(attackers)
            state.ball_carrier = carrier

        # Pick nearest defender to the ball
        nearest_def = self._nearest_defender(carrier, defenders)

        # Decide action based on zone position
        action = self._choose_action(carrier, state, att_tactics)

        if action == "pass":
            self._do_pass(state, carrier, attackers, nearest_def,
                          att_tactics, def_tactics, att_name, def_name)
        elif action == "dribble":
            self._do_dribble(state, carrier, nearest_def, att_tactics,
                             att_name, def_name)
        elif action == "shot":
            self._do_shot(state, carrier, nearest_def, att_tactics,
                          att_name, def_name)
        elif action == "cross":
            self._do_cross(state, carrier, attackers, defenders,
                           att_tactics, def_tactics, att_name, def_name)
        elif action == "tackle":
            # Defender initiates
            if nearest_def:
                self._do_tackle(state, nearest_def, carrier, def_tactics,
                                att_name, def_name)

    def _choose_action(
        self, carrier: PlayerInMatch, state: MatchState, tactics: TacticalContext
    ) -> str:
        """Decide what the ball carrier does this tick.

        Only called on event ticks (filtered by the dynamic event gate in
        _process_tick), so these weights directly control action distribution.
        """
        col = state.ball_zone_col
        row = state.ball_zone_row

        # Adjust column for away team (mirror)
        effective_col = col if carrier.side == "home" else (5 - col)

        # In the final third: high chance of shot
        if effective_col >= 5:
            weights = {"shot": 0.40, "pass": 0.30, "dribble": 0.15, "cross": 0.15}
        elif effective_col >= 4:
            if row != 1:  # on a wing in attack
                weights = {"cross": 0.35, "pass": 0.30, "dribble": 0.20, "shot": 0.15}
            else:
                weights = {"pass": 0.35, "shot": 0.25, "dribble": 0.25, "cross": 0.15}
        elif effective_col >= 3:
            weights = {"pass": 0.50, "dribble": 0.25, "cross": 0.10,
                       "shot": 0.05, "tackle": 0.10}
        else:
            weights = {"pass": 0.60, "dribble": 0.15, "cross": 0.05,
                       "shot": 0.02, "tackle": 0.18}

        # Tactical modifiers
        risk = tactics.risk_modifier
        if risk > 0:
            weights["shot"] = weights.get("shot", 0) * (1 + risk)
            weights["dribble"] = weights.get("dribble", 0) * (1 + risk * 0.5)
        else:
            weights["pass"] = weights.get("pass", 0) * (1 + abs(risk))

        # ── Match context: tactical matchup influence ─────────────────
        if self._match_context is not None:
            # Tactical advantage
            tac_adv_home = getattr(self._match_context, "tactical_advantage_home", 0.0)
            if carrier.side == "home" and tac_adv_home > 0.05:
                weights["shot"] = weights.get("shot", 0) * (1.0 + tac_adv_home * 0.5)
                weights["dribble"] = weights.get("dribble", 0) * (1.0 + tac_adv_home * 0.3)
            elif carrier.side == "away" and tac_adv_home < -0.05:
                weights["shot"] = weights.get("shot", 0) * (1.0 + abs(tac_adv_home) * 0.5)
                weights["dribble"] = weights.get("dribble", 0) * (1.0 + abs(tac_adv_home) * 0.3)

            # Weather influences on action choice
            weather_pen = 0.0
            if hasattr(self._match_context, "weather_passing_penalty"):
                weather_pen = self._match_context.weather_passing_penalty()
            if weather_pen > 0:
                # Rain/bad weather: boost long ball/cross, reduce short passing
                weights["cross"] = weights.get("cross", 0) * (1.0 + weather_pen * 0.8)
                weights["pass"] = weights.get("pass", 0) * (1.0 - weather_pen * 0.3)

            # Pitch condition: heavy pitch reduces dribble weight
            pitch_pen = self._match_context.pitch_dribble_penalty()
            if pitch_pen > 0:
                weights["dribble"] = weights.get("dribble", 0) * (1.0 - pitch_pen * 4.0)

            # Home advantage: home team slightly more aggressive in final third
            home_adv = self._match_context.home_advantage
            if carrier.side == "home" and effective_col >= 4 and home_adv > 0:
                weights["shot"] = weights.get("shot", 0) * (1.0 + home_adv * 0.3)
                weights["cross"] = weights.get("cross", 0) * (1.0 + home_adv * 0.2)

        # ── Game state awareness ────────────────────────────────────────
        side = carrier.side
        goal_diff = (
            (state.home_goals - state.away_goals) if side == "home"
            else (state.away_goals - state.home_goals)
        )
        minute = state.current_minute

        if goal_diff < 0:
            # Losing: more attacking, more risk
            urgency = 1.0 + (0.02 * max(0, minute - 60))  # grows after 60'
            weights["shot"] = weights.get("shot", 0) * (1.15 * urgency)
            weights["dribble"] = weights.get("dribble", 0) * (1.10 * urgency)
            weights["cross"] = weights.get("cross", 0) * (1.10 * urgency)
            weights["pass"] = weights.get("pass", 0) * 0.90
            # Late equaliser pressure (after 75')
            if minute >= 75:
                weights["shot"] = weights.get("shot", 0) * 1.25
                weights["cross"] = weights.get("cross", 0) * 1.15
        elif goal_diff > 0:
            # Winning: more cautious
            weights["pass"] = weights.get("pass", 0) * 1.20
            weights["shot"] = weights.get("shot", 0) * 0.85
            weights["dribble"] = weights.get("dribble", 0) * 0.85

        # ── Momentum integration ────────────────────────────────────────
        momentum = state.get_momentum(side)
        if momentum > 0:
            # High momentum → slight attacking boost
            weights["shot"] = weights.get("shot", 0) * (1.0 + momentum * 0.20)
            weights["dribble"] = weights.get("dribble", 0) * (1.0 + momentum * 0.10)
        elif momentum < 0:
            # Negative momentum → more cautious
            weights["pass"] = weights.get("pass", 0) * (1.0 + abs(momentum) * 0.15)
            weights["tackle"] = weights.get("tackle", 0) * (1.0 + abs(momentum) * 0.10)

        actions = list(weights.keys())
        w = list(weights.values())
        return weighted_random_choice(actions, w)

    # ── Action handlers ────────────────────────────────────────────────────

    def _do_pass(self, state, carrier, attackers, nearest_def,
                 att_tac, def_tac, att_name, def_name):
        targets = [p for p in attackers if p != carrier and p.is_on_pitch]
        if not targets:
            return

        weights = []
        for t in targets:
            fwd_bonus = t.zone_col if carrier.side == "home" else (5 - t.zone_col)
            weights.append(max(fwd_bonus + 1.0, 0.5))
        receiver = weighted_random_choice(targets, weights)

        dist = zone_distance(
            (carrier.zone_col, carrier.zone_row),
            (receiver.zone_col, receiver.zone_row),
        )

        # Offside check on forward passes (~3% chance if receiver is in final third)
        rcol = receiver.zone_col if carrier.side == "home" else (5 - receiver.zone_col)
        if rcol >= 4 and dist >= 2 and random.random() < 0.03:
            state._inc(carrier.side, "offsides")
            receiver.offsides_count += 1
            self._turnover(state, def_name)
            state.commentary.append(
                self.commentary.offside(state.current_minute, receiver.name, att_name)
            )
            return

        # Track team pass
        state._inc(carrier.side, "passes")

        # Interception check
        if nearest_def:
            inter_result = resolve_interception(nearest_def, carrier, dist)
            if inter_result.success:
                state._inc(nearest_def.side, "interceptions")
                state._update_momentum(nearest_def.side, "tackle_won")
                state._update_momentum(carrier.side, "turnover")
                self._turnover(state, def_name)
                state.commentary.append(
                    self.commentary.interception(
                        state.current_minute, nearest_def.name,
                        carrier.name, def_name
                    )
                )
                return

        result = resolve_pass(carrier, receiver, nearest_def, dist, att_tac)
        if result.success:
            state._inc(carrier.side, "passes_completed")
            # Key pass check: receiver is in final third
            if rcol >= 4:
                carrier.key_passes += 1
                state._inc(carrier.side, "key_passes")
            state.ball_zone_col = receiver.zone_col
            state.ball_zone_row = receiver.zone_row
            state.ball_carrier = receiver
        else:
            self._turnover(state, def_name)

    def _do_dribble(self, state, carrier, nearest_def, att_tac, att_name, def_name):
        state._inc(carrier.side, "dribbles")
        result = resolve_dribble(carrier, nearest_def, att_tac)

        if result.is_foul:
            state._inc(nearest_def.side if nearest_def else carrier.side, "fouls")
            self._handle_foul(state, nearest_def, carrier, result,
                              att_name, def_name)
            return

        if result.success:
            state._inc(carrier.side, "dribbles_completed")
            state._update_momentum(carrier.side, "dribble_completed")
            if carrier.side == "home":
                new_col = min(carrier.zone_col + 1, 5)
            else:
                new_col = max(carrier.zone_col - 1, 0)
            state.ball_zone_col = new_col
            state.ball_zone_row = carrier.zone_row
            carrier.zone_col = new_col
            carrier.stamina_current -= FATIGUE_SPRINT_COST
        else:
            # Defender won the ball — track as tackle
            if nearest_def:
                state._inc(nearest_def.side, "tackles")
                state._inc(nearest_def.side, "tackles_won")
                state._update_momentum(nearest_def.side, "tackle_won")
            state._update_momentum(carrier.side, "turnover")
            self._turnover(state, def_name)

    def _do_shot(self, state, carrier, nearest_def, att_tac, att_name, def_name):
        opp_side = "away" if carrier.side == "home" else "home"
        gk = state.get_gk(opp_side)

        result = resolve_shot(
            carrier, gk, nearest_def,
            state.ball_zone_col, state.ball_zone_row, att_tac
        )

        # Track team stats
        state._inc(carrier.side, "shots")
        state._inc(carrier.side, "xg", result.xg_value)

        if result.detail in ("saved", "goal"):
            state._inc(carrier.side, "sot")
            state._update_momentum(carrier.side, "shot_on_target")
        if result.is_blocked:
            state._inc(carrier.side, "shots_blocked")
            if nearest_def:
                state._inc(nearest_def.side, "blocks")
            # Blocked shots from wing can give corner
            if state.ball_zone_row != 1 and random.random() < 0.35:
                self._do_corner(state, carrier.side, att_name, def_name)
        if result.hit_woodwork:
            state._inc(carrier.side, "woodwork")
            state.commentary.append(
                self.commentary.woodwork(
                    state.current_minute, carrier.name, att_name
                )
            )
            state.events.append({
                "minute": state.current_minute,
                "type": "woodwork", "player": carrier.name,
                "side": carrier.side,
            })
        if result.detail == "saved" and gk:
            state._inc(opp_side, "saves")
            state._update_momentum(opp_side, "save")
            state.commentary.append(
                self.commentary.save(
                    state.current_minute, gk.name, carrier.name,
                )
            )
            # Save can give corner
            if random.random() < 0.4:
                self._do_corner(state, carrier.side, att_name, def_name)

        # Big chances
        effective_col = state.ball_zone_col if carrier.side == "home" else (5 - state.ball_zone_col)
        if effective_col >= 4 and state.ball_zone_row == 1 and result.xg_value > 0.25:
            state._inc(carrier.side, "big_chances")
            if not result.success:
                state._inc(carrier.side, "big_chances_missed")
                if result.detail in ("saved", "off_target", "woodwork"):
                    state.commentary.append(
                        self.commentary.big_chance_missed(
                            state.current_minute, carrier.name, att_name
                        )
                    )

        if result.success:
            # GOAL!
            if carrier.side == "home":
                state.home_goals += 1
            else:
                state.away_goals += 1

            assister = self._find_potential_assister(state, carrier)
            assist_name = assister.name if assister else None
            if assister:
                assister.assists += 1
                assister.key_passes += 1
                assister.rating_points += 0.3
                assister.rating_events += 1

            state.events.append({
                "minute": state.current_minute,
                "type": "goal",
                "player": carrier.name,
                "player_id": carrier.player_id,
                "assist": assist_name,
                "assist_id": assister.player_id if assister else None,
                "side": carrier.side,
                "xg": result.xg_value,
            })
            state.commentary.append(
                self.commentary.goal(
                    state.current_minute, carrier.name, att_name,
                    assist_name=assist_name,
                    score_home=state.home_goals, score_away=state.away_goals,
                    home_name=att_name if carrier.side == "home" else def_name,
                    away_name=def_name if carrier.side == "home" else att_name,
                )
            )
            # Momentum: scorer gains, conceder loses
            opp_side = "away" if carrier.side == "home" else "home"
            state._update_momentum(carrier.side, "goal")
            state._update_momentum(opp_side, "concede")

            state.ball_side = "away" if carrier.side == "home" else "home"
            state.ball_zone_col = 3
            state.ball_zone_row = 1
            state.ball_carrier = None
        elif result.detail not in ("saved", "woodwork"):
            # Off target / blocked — turnover
            self._turnover(state, def_name)

    def _do_cross(self, state, carrier, attackers, defenders,
                  att_tac, def_tac, att_name, def_name):
        targets = [p for p in attackers if p != carrier and p.is_on_pitch
                   and not p.is_gk]
        if not targets:
            self._do_pass(state, carrier, attackers, None, att_tac, def_tac,
                          att_name, def_name)
            return

        target = weighted_random_choice(
            targets,
            [p.effective("heading_accuracy") + p.effective("jumping") for p in targets]
        )
        nearest_cb = self._nearest_defender(target, defenders)

        # Track cross
        state._inc(carrier.side, "crosses")
        cross_result = resolve_cross(carrier, target, nearest_cb, att_tac)
        if not cross_result.success:
            # Failed cross can give corner if deflected
            if nearest_cb and random.random() < 0.25:
                nearest_cb.clearances += 1
                state._inc(nearest_cb.side, "clearances")
                self._do_corner(state, carrier.side, att_name, def_name)
            self._turnover(state, def_name)
            return

        state._inc(carrier.side, "crosses_completed")

        # Header on goal
        opp_side = "away" if carrier.side == "home" else "home"
        gk = state.get_gk(opp_side)
        header_result = resolve_header(target, gk, nearest_cb, att_tac)

        # Track team stats
        state._inc(carrier.side, "shots")
        state._inc(carrier.side, "xg", header_result.xg_value)
        state._inc(carrier.side, "aerials_won")
        if nearest_cb:
            state._inc(nearest_cb.side, "aerials_lost")

        if header_result.detail in ("saved", "headed_goal"):
            state._inc(carrier.side, "sot")
        if header_result.hit_woodwork:
            state._inc(carrier.side, "woodwork")
            state.commentary.append(
                self.commentary.woodwork(
                    state.current_minute, target.name, att_name
                )
            )
        if header_result.detail == "saved" and gk:
            state._inc(opp_side, "saves")

        if header_result.success:
            if carrier.side == "home":
                state.home_goals += 1
            else:
                state.away_goals += 1

            carrier.assists += 1
            carrier.key_passes += 1
            carrier.rating_points += 0.3
            carrier.rating_events += 1

            state.events.append({
                "minute": state.current_minute,
                "type": "goal",
                "player": target.name,
                "player_id": target.player_id,
                "assist": carrier.name,
                "assist_id": carrier.player_id,
                "side": carrier.side,
                "xg": header_result.xg_value,
                "detail": "header",
            })
            state.commentary.append(
                self.commentary.header_goal(
                    state.current_minute, target.name, carrier.name, att_name,
                    state.home_goals, state.away_goals,
                    att_name if carrier.side == "home" else def_name,
                    def_name if carrier.side == "home" else att_name,
                )
            )
            # Momentum for headed goal
            cross_opp = "away" if carrier.side == "home" else "home"
            state._update_momentum(carrier.side, "goal")
            state._update_momentum(cross_opp, "concede")

            state.ball_side = "away" if carrier.side == "home" else "home"
            state.ball_zone_col = 3
            state.ball_zone_row = 1
            state.ball_carrier = None
        else:
            self._turnover(state, def_name)

    def _do_tackle(self, state, tackler, carrier, def_tac, att_name, def_name):
        state._inc(tackler.side, "tackles")
        result = resolve_tackle(tackler, carrier, def_tac)

        if result.is_foul:
            state._inc(tackler.side, "fouls")
            self._handle_foul(state, tackler, carrier, result, att_name, def_name)
            return

        if result.success:
            state._inc(tackler.side, "tackles_won")
            state._update_momentum(tackler.side, "tackle_won")
            old_side = state.ball_side
            new_side = "home" if old_side == "away" else "away"
            state.ball_side = new_side
            state.ball_carrier = tackler
            state.ball_zone_col = tackler.zone_col
            state.ball_zone_row = tackler.zone_row

            # ── Counter-attack check ──────────────────────────────────
            # After winning the ball, if we have fast forwards, try a counter
            new_attackers = state.get_attacking_players()
            new_defenders = state.get_defending_players()
            fast_forwards = [
                p for p in new_attackers
                if not p.is_gk and p.is_on_pitch
                and p.effective("pace") > 65
                and (p.zone_col >= 3 if tackler.side == "home" else p.zone_col <= 2)
            ]
            if fast_forwards and random.random() < 0.18:
                # Swap names: tackler's side is now attacking.
                # In the outer scope att_name is the *original* attacker's name
                # and def_name is the *original* defender's (tackler's) name.
                counter_att_name = def_name   # tackler's team now attacking
                counter_def_name = att_name   # original attacker now defending
                self._do_counter_attack(
                    state, tackler, new_attackers, new_defenders,
                    None, None, counter_att_name, counter_def_name,
                )

    # ── Set piece & counter-attack handlers ─────────────────────────────

    def _do_penalty(self, state, taker, gk, att_name, def_name):
        """Simulate a penalty kick."""
        att_side = taker.side
        opp_side = "away" if att_side == "home" else "home"

        state.commentary.append(
            f"{state.current_minute}' 🔴 PENALTY! {att_name} are awarded a penalty kick!"
        )

        # Momentum bonus applied to taker composure temporarily
        momentum = state.get_momentum(att_side)
        att_tac = TacticalContext()  # neutral for penalty

        result = resolve_penalty(taker, gk, att_tac)

        state._inc(att_side, "shots")
        state._inc(att_side, "xg", result.xg_value)
        state._inc(att_side, "big_chances")

        if result.detail in ("saved", "penalty_goal"):
            state._inc(att_side, "sot")
        if result.hit_woodwork:
            state._inc(att_side, "woodwork")
            state.commentary.append(
                self.commentary.woodwork(state.current_minute, taker.name, att_name)
            )
        if result.detail == "saved" and gk:
            state._inc(opp_side, "saves")
            state._update_momentum(opp_side, "save")
            state.commentary.append(
                f"{state.current_minute}' 🧤 PENALTY SAVED! {gk.name} dives the right way!"
            )
        if not result.success:
            state._inc(att_side, "big_chances_missed")

        if result.success:
            # Penalty goal
            if att_side == "home":
                state.home_goals += 1
            else:
                state.away_goals += 1

            state.events.append({
                "minute": state.current_minute,
                "type": "goal",
                "player": taker.name,
                "player_id": taker.player_id,
                "assist": None,
                "assist_id": None,
                "side": att_side,
                "xg": result.xg_value,
                "detail": "penalty",
            })
            state.commentary.append(
                f"{state.current_minute}' ⚽ GOAL! {taker.name} converts the penalty! "
                f"{att_name} {state.home_goals if att_side == 'home' else state.away_goals}"
                f"-{state.away_goals if att_side == 'home' else state.home_goals}"
            )
            state._update_momentum(att_side, "goal")
            state._update_momentum(opp_side, "concede")

        # Reset ball to centre
        state.ball_side = opp_side if result.success else att_side
        state.ball_zone_col = 3
        state.ball_zone_row = 1
        state.ball_carrier = None

    def _do_free_kick(self, state, taker, gk, nearest_def, att_name, def_name):
        """Simulate a direct free kick shot."""
        att_side = taker.side
        opp_side = "away" if att_side == "home" else "home"

        # Distance from goal based on zone
        effective_col = state.ball_zone_col if att_side == "home" else (5 - state.ball_zone_col)
        distance = max(1.0, 5.0 - effective_col)

        att_tac = TacticalContext()
        result = resolve_free_kick(taker, gk, nearest_def, distance, att_tac)

        state._inc(att_side, "shots")
        state._inc(att_side, "xg", result.xg_value)

        if result.detail in ("saved", "free_kick_goal"):
            state._inc(att_side, "sot")
            state._update_momentum(att_side, "shot_on_target")
        if result.is_blocked:
            state._inc(att_side, "shots_blocked")
            if nearest_def:
                state._inc(nearest_def.side, "blocks")
        if result.hit_woodwork:
            state._inc(att_side, "woodwork")
            state.commentary.append(
                self.commentary.woodwork(state.current_minute, taker.name, att_name)
            )
        if result.detail == "saved" and gk:
            state._inc(opp_side, "saves")
            state._update_momentum(opp_side, "save")
            state.commentary.append(
                self.commentary.save(state.current_minute, gk.name, taker.name)
            )
            # Save from free kick can give corner
            if random.random() < 0.35:
                state._inc(att_side, "corners")

        if result.success:
            if att_side == "home":
                state.home_goals += 1
            else:
                state.away_goals += 1

            state.events.append({
                "minute": state.current_minute,
                "type": "goal",
                "player": taker.name,
                "player_id": taker.player_id,
                "assist": None,
                "assist_id": None,
                "side": att_side,
                "xg": result.xg_value,
                "detail": "free_kick",
            })
            state.commentary.append(
                f"{state.current_minute}' ⚽ GOAL! What a free kick from {taker.name}! "
                f"Straight into the net!"
            )
            state._update_momentum(att_side, "goal")
            state._update_momentum(opp_side, "concede")
            state.ball_side = opp_side
            state.ball_zone_col = 3
            state.ball_zone_row = 1
            state.ball_carrier = None
        elif result.detail not in ("saved", "woodwork"):
            self._turnover(state, def_name)

    def _do_corner(self, state, side, att_name, def_name):
        """Simulate a corner kick set piece (~3-5% goal rate)."""
        att_side = side
        opp_side = "away" if att_side == "home" else "home"
        attackers = (state.home_players if att_side == "home" else state.away_players)
        defenders = (state.away_players if att_side == "home" else state.home_players)

        # Pick best crosser
        outfield_att = [p for p in attackers if p.is_on_pitch and not p.is_gk]
        outfield_def = [p for p in defenders if p.is_on_pitch and not p.is_gk]
        if not outfield_att:
            return

        crosser = max(outfield_att, key=lambda p: p.effective("crossing") + p.effective("curve"))

        # Pick best header target
        targets = [p for p in outfield_att if p != crosser]
        if not targets:
            return
        target = max(targets, key=lambda p: p.effective("heading_accuracy") + p.effective("jumping"))

        # Pick nearest CB defender
        nearest_cb = max(
            outfield_def,
            key=lambda d: d.effective("heading_accuracy") + d.effective("jumping"),
        ) if outfield_def else None

        gk = state.get_gk(opp_side)

        state._inc(att_side, "corners")
        state._update_momentum(att_side, "corner_won")

        state.commentary.append(
            self.commentary.corner(state.current_minute, att_name)
        )

        # Cross delivery
        cross_result = resolve_cross(crosser, target, nearest_cb, TacticalContext())
        state._inc(att_side, "crosses")
        if not cross_result.success:
            if nearest_cb and random.random() < 0.40:
                nearest_cb.clearances += 1
                state._inc(nearest_cb.side, "clearances")
            return

        state._inc(att_side, "crosses_completed")

        # Header attempt
        header_result = resolve_header(target, gk, nearest_cb, TacticalContext())

        state._inc(att_side, "shots")
        state._inc(att_side, "xg", header_result.xg_value)
        state._inc(att_side, "aerials_won")
        if nearest_cb:
            state._inc(nearest_cb.side, "aerials_lost")

        if header_result.detail in ("saved", "headed_goal"):
            state._inc(att_side, "sot")
        if header_result.hit_woodwork:
            state._inc(att_side, "woodwork")
        if header_result.detail == "saved" and gk:
            state._inc(opp_side, "saves")
            state._update_momentum(opp_side, "save")

        if header_result.success:
            if att_side == "home":
                state.home_goals += 1
            else:
                state.away_goals += 1

            crosser.assists += 1
            crosser.key_passes += 1
            crosser.rating_points += 0.3
            crosser.rating_events += 1

            state.events.append({
                "minute": state.current_minute,
                "type": "goal",
                "player": target.name,
                "player_id": target.player_id,
                "assist": crosser.name,
                "assist_id": crosser.player_id,
                "side": att_side,
                "xg": header_result.xg_value,
                "detail": "corner_header",
            })
            state.commentary.append(
                self.commentary.header_goal(
                    state.current_minute, target.name, crosser.name, att_name,
                    state.home_goals, state.away_goals,
                    att_name if att_side == "home" else def_name,
                    def_name if att_side == "home" else att_name,
                )
            )
            state._update_momentum(att_side, "goal")
            state._update_momentum(opp_side, "concede")
            state.ball_side = opp_side
            state.ball_zone_col = 3
            state.ball_zone_row = 1
            state.ball_carrier = None

    def _do_counter_attack(self, state, carrier, attackers, defenders,
                           att_tac, def_tac, att_name, def_name):
        """Simulate a counter-attack sequence.

        Counter-attacks use pace/acceleration heavily and face fewer
        defenders, resulting in higher xG chances.
        """
        att_side = carrier.side
        opp_side = "away" if att_side == "home" else "home"

        # Pick fast forwards as runners
        fast_runners = sorted(
            [p for p in attackers if p.is_on_pitch and not p.is_gk
             and p.effective("pace") > 55],
            key=lambda p: p.effective("pace") + p.effective("acceleration"),
            reverse=True,
        )[:3]

        if not fast_runners:
            return

        # Carrier sprints forward
        carrier.stamina_current -= FATIGUE_SPRINT_COST * 2

        state.commentary.append(
            f"{state.current_minute}' ⚡ Counter-attack! {att_name} break forward quickly!"
        )

        # The counter-attack runner (fastest forward or the carrier)
        runner = fast_runners[0] if fast_runners[0] != carrier else (
            fast_runners[1] if len(fast_runners) > 1 else carrier
        )

        # Fewer defenders caught back (simulate only 1-2)
        caught_back = [
            d for d in defenders if d.is_on_pitch and not d.is_gk
            and d.effective("pace") > 55
        ][:2]
        nearest_def = caught_back[0] if caught_back else None

        # Speed duel: can the runner beat the defenders?
        runner_speed = (
            runner.effective("pace") * 0.40
            + runner.effective("acceleration") * 0.30
            + runner.effective("dribbling") * 0.20
            + runner.effective("composure") * 0.10
        )

        def_speed = 0.0
        if nearest_def:
            def_speed = (
                nearest_def.effective("pace") * 0.35
                + nearest_def.effective("acceleration") * 0.30
                + nearest_def.effective("positioning") * 0.20
            )

        # Momentum bonus on counter
        momentum = state.get_momentum(att_side)
        runner_speed += momentum * 8.0

        breakaway = runner_speed > def_speed * 0.75

        if breakaway:
            # Runner is through — take a shot from close range
            gk = state.get_gk(opp_side)

            # Move ball to final third
            if att_side == "home":
                state.ball_zone_col = 5
            else:
                state.ball_zone_col = 0
            state.ball_zone_row = 1

            # Counter-attack xG boost: use finishing with less defensive pressure
            base = (
                runner.effective("finishing") * 0.35
                + runner.effective("composure") * 0.30
                + runner.effective("pace") * 0.15
                + runner.effective("shot_power") * 0.10
            )
            raw_xg = clamp(base / 99.0 * 0.70, 0.15, 0.55)

            runner.shots += 1
            state._inc(att_side, "shots")
            state._inc(att_side, "xg", raw_xg)
            state._inc(att_side, "big_chances")

            # On target?
            accuracy = clamp(base / 99.0, 0.30, 0.85)
            on_target = random.random() < accuracy

            if not on_target:
                if random.random() < 0.08:
                    runner.hit_woodwork += 1
                    state._inc(att_side, "woodwork")
                    state.commentary.append(
                        self.commentary.woodwork(
                            state.current_minute, runner.name, att_name
                        )
                    )
                    return
                runner.rating_events += 1
                state._inc(att_side, "big_chances_missed")
                self._turnover(state, def_name)
                return

            runner.shots_on_target += 1
            state._inc(att_side, "sot")
            state._update_momentum(att_side, "shot_on_target")

            # GK save attempt (reduced chance — 1v1)
            if gk:
                gk_quality = (
                    gk.effective("gk_reflexes") * 0.30
                    + gk.effective("gk_diving") * 0.20
                    + gk.effective("gk_positioning") * 0.30
                )
                save_chance = clamp(gk_quality / 99.0 * (1.0 - raw_xg * 0.4), 0.05, 0.50)
                if random.random() < save_chance:
                    gk.saves += 1
                    gk.rating_points += 0.20
                    gk.rating_events += 1
                    state._inc(opp_side, "saves")
                    state._update_momentum(opp_side, "save")
                    state.commentary.append(
                        self.commentary.save(
                            state.current_minute, gk.name, runner.name,
                        )
                    )
                    state._inc(att_side, "big_chances_missed")
                    return

            # COUNTER-ATTACK GOAL!
            runner.goals += 1
            runner.rating_points += 0.5
            runner.rating_events += 1
            if att_side == "home":
                state.home_goals += 1
            else:
                state.away_goals += 1

            # Carrier gets assist if different from runner
            assist_name = None
            if carrier != runner:
                carrier.assists += 1
                carrier.key_passes += 1
                carrier.rating_points += 0.3
                carrier.rating_events += 1
                assist_name = carrier.name

            state.events.append({
                "minute": state.current_minute,
                "type": "goal",
                "player": runner.name,
                "player_id": runner.player_id,
                "assist": assist_name,
                "assist_id": carrier.player_id if assist_name else None,
                "side": att_side,
                "xg": raw_xg,
                "detail": "counter_attack",
            })
            state.commentary.append(
                f"{state.current_minute}' ⚽ GOAL! {runner.name} finishes off a "
                f"brilliant counter-attack for {att_name}! "
                f"{state.home_goals}-{state.away_goals}"
            )
            state._update_momentum(att_side, "goal")
            state._update_momentum(opp_side, "concede")
            state.ball_side = opp_side
            state.ball_zone_col = 3
            state.ball_zone_row = 1
            state.ball_carrier = None
        else:
            # Counter slowed down — turnover
            state._update_momentum(att_side, "turnover")
            self._turnover(state, def_name)

    # ── Helpers ────────────────────────────────────────────────────────────

    def _turnover(self, state: MatchState, to_name: str):
        """Switch possession."""
        state.ball_side = "away" if state.ball_side == "home" else "home"
        state.ball_carrier = None

    def _handle_foul(self, state, fouler, victim, result, att_name, def_name):
        state._inc(fouler.side, "fouls")

        event = {
            "minute": state.current_minute,
            "type": "foul",
            "player": fouler.name,
            "player_id": fouler.player_id,
            "side": fouler.side,
        }

        if result.is_red:
            fouler.red_card = True
            fouler.is_on_pitch = False
            state._inc(fouler.side, "red_cards")
            event["type"] = "red_card"
            state.commentary.append(
                self.commentary.red_card(state.current_minute, fouler.name,
                                         victim.name, def_name)
            )
            state._update_momentum(fouler.side, "red_card")
        elif result.is_yellow:
            fouler.yellow_cards += 1
            state._inc(fouler.side, "yellow_cards")
            event["type"] = "yellow_card"
            if fouler.yellow_cards >= 2:
                fouler.red_card = True
                fouler.is_on_pitch = False
                state._inc(fouler.side, "red_cards")
                state.commentary.append(
                    self.commentary.second_yellow(state.current_minute,
                                                   fouler.name, def_name)
                )
                state._update_momentum(fouler.side, "red_card")
            else:
                state.commentary.append(
                    self.commentary.yellow_card(state.current_minute,
                                                fouler.name, victim.name, def_name)
                )
                state._update_momentum(fouler.side, "yellow_card")

        state.events.append(event)

        # ── Set piece resolution after foul ─────────────────────────────
        # Determine foul zone from victim's perspective
        victim_effective_col = (
            state.ball_zone_col if victim.side == "home"
            else (5 - state.ball_zone_col)
        )

        # Penalty: foul in the box (final third, central)
        if victim_effective_col >= 5 and state.ball_zone_row == 1:
            opp_side = "away" if victim.side == "home" else "home"
            gk = state.get_gk(opp_side)
            # Pick best penalty taker from attacking team
            attackers = state.get_attacking_players()
            taker = max(attackers, key=lambda p: p.effective("penalties")) if attackers else victim
            self._do_penalty(state, taker, gk, att_name, def_name)
            state._update_momentum(victim.side, "free_kick_won")
            return

        # Direct free kick in attacking zones (col 4-5)
        if victim_effective_col >= 4 and random.random() < 0.30:
            opp_side = "away" if victim.side == "home" else "home"
            gk = state.get_gk(opp_side)
            attackers = state.get_attacking_players()
            taker = max(
                attackers,
                key=lambda p: p.effective("free_kick_accuracy") + p.effective("curve"),
            ) if attackers else victim
            nearest_def = self._nearest_defender(taker, state.get_defending_players())
            self._do_free_kick(state, taker, gk, nearest_def, att_name, def_name)
            state._update_momentum(victim.side, "free_kick_won")
            return

        # Otherwise: victim keeps ball (regular free kick, no shot)
        state._update_momentum(victim.side, "free_kick_won")

    def _nearest_defender(
        self, reference: PlayerInMatch, defenders: list[PlayerInMatch]
    ) -> PlayerInMatch | None:
        """Find the defender closest to the reference player."""
        if not defenders:
            return None
        active = [d for d in defenders if d.is_on_pitch and not d.red_card and not d.is_gk]
        if not active:
            return None
        return min(
            active,
            key=lambda d: zone_distance(
                (reference.zone_col, reference.zone_row),
                (d.zone_col, d.zone_row)
            )
        )

    def _find_potential_assister(
        self, state: MatchState, scorer: PlayerInMatch
    ) -> PlayerInMatch | None:
        """Find a plausible assister (teammate near the scorer)."""
        teammates = state.get_attacking_players()
        candidates = [t for t in teammates if t != scorer and t.is_on_pitch
                      and not t.is_gk]
        if not candidates:
            return None
        # Weight by proximity and creative ability
        weights = []
        for t in candidates:
            dist = zone_distance(
                (scorer.zone_col, scorer.zone_row),
                (t.zone_col, t.zone_row)
            )
            w = max(1.0, (t.effective("vision") + t.effective("passing")) / 2.0
                    - dist * 10.0)
            weights.append(w)
        if all(w <= 0 for w in weights):
            return None
        weights = [max(w, 0.1) for w in weights]
        return weighted_random_choice(candidates, weights)

    def _assign_zones(
        self, state: MatchState,
        h_tac: TacticalContext, a_tac: TacticalContext,
    ):
        """Assign each player to a zone based on formation and game phase."""
        def assign_side(players: list[PlayerInMatch], tactics: TacticalContext,
                        side: str, has_ball: bool):
            zones = tactics.attacking_zones() if has_ball else tactics.defending_zones()
            outfield = [p for p in players if p.is_on_pitch and not p.is_gk
                        and not p.red_card]
            gks = [p for p in players if p.is_on_pitch and p.is_gk]

            # GK always at (0, 1) for home, (5, 1) for away
            for g in gks:
                g.zone_col = 0 if side == "home" else 5
                g.zone_row = 1

            for i, p in enumerate(outfield):
                if i < len(zones):
                    col, row = zones[i]
                    if side == "away":
                        col = 5 - col  # mirror for away
                    p.zone_col = col
                    p.zone_row = row

        assign_side(state.home_players, h_tac, "home",
                     state.ball_side == "home")
        assign_side(state.away_players, a_tac, "away",
                     state.ball_side == "away")

    def _apply_fatigue(self, state: MatchState, minute: int,
                       h_tac: TacticalContext = None, a_tac: TacticalContext = None):
        """Reduce stamina for all players on the pitch.

        High pressing and high tempo tactics drain stamina faster.
        Weather and pitch conditions add extra drain when match_context
        is available.
        """
        # Pre-compute tactical drain multipliers per side
        home_tac_mult = 1.0
        away_tac_mult = 1.0
        if h_tac is not None:
            # High pressing: 30% faster stamina loss
            home_tac_mult += h_tac.press_modifier * 0.30
            # High tempo: extra stamina cost
            home_tac_mult += h_tac.tempo_modifier * 0.15
        if a_tac is not None:
            away_tac_mult += a_tac.press_modifier * 0.30
            away_tac_mult += a_tac.tempo_modifier * 0.15

        # Weather/pitch extra drain
        weather_drain = 0.0
        if self._match_context is not None:
            # Weather fatigue multiplier (hot=1.35, heavy_rain=1.20, etc.)
            weather_mult = self._match_context.weather_fatigue_multiplier()
            weather_drain = FATIGUE_PER_MINUTE * (weather_mult - 1.0)

        all_players = state.home_players + state.away_players
        for p in all_players:
            if p.is_on_pitch and not p.is_gk:
                tac_mult = home_tac_mult if p.side == "home" else away_tac_mult
                drain = FATIGUE_PER_MINUTE * (100.0 / max(p.stamina, 30)) * tac_mult
                drain += weather_drain
                p.stamina_current = max(0.0, p.stamina_current - drain)

                # Players below 60 stamina start making more errors
                # Apply a fitness_mod penalty that feeds into effective()
                if p.stamina_current < 60.0:
                    error_penalty = (60.0 - p.stamina_current) / 60.0 * 0.15
                    p.fitness_mod = max(0.5, p.fitness_mod - error_penalty * 0.02)

                # Players below 30 stamina are basically walking
                if p.stamina_current < 30.0:
                    walk_penalty = (30.0 - p.stamina_current) / 30.0 * 0.25
                    p.fitness_mod = max(0.4, p.fitness_mod - walk_penalty * 0.03)

    def _check_injuries(self, state, minute, h_name, a_name):
        """Random injury checks."""
        all_players = state.home_players + state.away_players
        for p in all_players:
            if not p.is_on_pitch:
                continue
            chance = INJURY_BASE_CHANCE * (1.0 + (100 - p.stamina_current) / 100.0)
            if random.random() < chance:
                p.is_on_pitch = False
                team_name = h_name if p.side == "home" else a_name
                state.events.append({
                    "minute": minute,
                    "type": "injury",
                    "player": p.name,
                    "player_id": p.player_id,
                    "side": p.side,
                })
                state.commentary.append(
                    self.commentary.injury(minute, p.name, team_name)
                )
                # Force sub
                self._force_sub(state, p, minute, team_name)

    def _force_sub(self, state, injured: PlayerInMatch, minute, team_name):
        """Substitute an injured player."""
        subs = state.home_subs if injured.side == "home" else state.away_subs
        subs_made = (state.home_subs_made if injured.side == "home"
                     else state.away_subs_made)
        if subs_made >= state.max_subs or not subs:
            return
        # Find best sub for the position
        best_sub = None
        for s in subs:
            if s.position == injured.position:
                best_sub = s
                break
        if best_sub is None and subs:
            best_sub = subs[0]
        if best_sub:
            best_sub.is_on_pitch = True
            best_sub.zone_col = injured.zone_col
            best_sub.zone_row = injured.zone_row
            subs.remove(best_sub)
            if injured.side == "home":
                state.home_players.append(best_sub)
                state.home_subs_made += 1
            else:
                state.away_players.append(best_sub)
                state.away_subs_made += 1
            state.commentary.append(
                self.commentary.substitution(minute, injured.name,
                                              best_sub.name, team_name)
            )
            state.events.append({
                "minute": minute,
                "type": "substitution",
                "player": injured.name,
                "player_id": injured.player_id,
                "sub_in": best_sub.name,
                "sub_in_id": best_sub.player_id,
                "side": injured.side,
            })

    def _auto_subs(self, state, minute, h_name, a_name):
        """AI-controlled auto-subs for fatigued/poor-performing players."""
        for side, players, subs, name in [
            ("home", state.home_players, state.home_subs, h_name),
            ("away", state.away_players, state.away_subs, a_name),
        ]:
            subs_made = (state.home_subs_made if side == "home"
                         else state.away_subs_made)
            if subs_made >= state.max_subs or not subs:
                continue
            # Find most fatigued outfield player
            tired = [p for p in players if p.is_on_pitch and not p.is_gk
                     and p.stamina_current < 30]
            if not tired:
                continue
            if random.random() > 0.3:  # Don't sub every minute
                continue
            worst = min(tired, key=lambda p: p.stamina_current)
            best_sub = None
            for s in subs:
                if s.position == worst.position:
                    best_sub = s
                    break
            if not best_sub and subs:
                best_sub = subs[0]
            if best_sub:
                worst.is_on_pitch = False
                best_sub.is_on_pitch = True
                best_sub.zone_col = worst.zone_col
                best_sub.zone_row = worst.zone_row
                subs.remove(best_sub)
                players.append(best_sub)
                if side == "home":
                    state.home_subs_made += 1
                else:
                    state.away_subs_made += 1
                state.commentary.append(
                    self.commentary.substitution(minute, worst.name,
                                                  best_sub.name, name)
                )
                state.events.append({
                    "minute": minute,
                    "type": "substitution",
                    "player": worst.name,
                    "player_id": worst.player_id,
                    "sub_in": best_sub.name,
                    "sub_in_id": best_sub.player_id,
                    "side": side,
                })

    def _generate_scorecard(self, state: MatchState, minute: int) -> Scorecard:
        """Generate a 10-minute interval scorecard."""
        interval_start = minute - SCORECARD_INTERVAL + 1
        interval_events = [
            e for e in state.commentary
            if any(f"{m}'" in e or f"{m} " in e
                   for m in range(interval_start, minute + 1))
        ]

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
            events_text=interval_events[-5:],
            zone_heatmap_home=self.pitch.text_heatmap("home"),
            zone_heatmap_away=self.pitch.text_heatmap("away"),
        )

    # ── Weather & context methods ──────────────────────────────────────────

    def _weather_kickoff_commentary(self, state, h_name, a_name):
        """Generate weather-related commentary at start of the match."""
        if self._match_context is None:
            return

        # Use MatchContext's built-in kickoff commentary
        for line in self._match_context.kickoff_commentary():
            state.commentary.append(f"0' {line}")

        # Home advantage commentary
        if self._match_context.home_advantage > 0.05:
            state.commentary.append(
                f"0' The home crowd is roaring! {h_name} will look to "
                f"use this atmosphere to their advantage."
            )

    def _apply_weather_effects(self, state, minute):
        """Apply per-minute weather effects during the match."""
        if self._match_context is None:
            return

        from fm.engine.match_context import Weather

        weather = self._match_context.weather
        all_players = state.home_players + state.away_players
        on_pitch = [p for p in all_players if p.is_on_pitch and not p.is_gk]
        if not on_pitch:
            return

        # Rain/heavy rain: occasional slip causing turnover
        if weather in (Weather.RAIN, Weather.HEAVY_RAIN):
            slip_chance = 0.015 if weather == Weather.RAIN else 0.03
            if random.random() < slip_chance:
                victim = random.choice(on_pitch)
                state.commentary.append(
                    f"{minute}' {victim.name} slips on the wet surface! "
                    f"The ball runs loose."
                )
                if state.ball_carrier == victim:
                    state.ball_side = "away" if victim.side == "home" else "home"
                    state.ball_carrier = None

        # Snow: occasional error from reduced visibility
        elif weather == Weather.SNOW:
            if random.random() < 0.015:
                victim = random.choice(on_pitch)
                state.commentary.append(
                    f"{minute}' {victim.name} misjudges the ball in "
                    f"the snow. Loose ball!"
                )
                if state.ball_carrier == victim:
                    state.ball_side = "away" if victim.side == "home" else "home"
                    state.ball_carrier = None

        # Wind: rare commentary about conditions affecting play
        elif weather == Weather.WIND:
            if random.random() < 0.008:
                state.commentary.append(
                    f"{minute}' The wind carries a cross well away from "
                    f"its intended target."
                )

    def _check_morale_events(self, state, minute, h_name, a_name):
        """Check for morale-influenced events each minute.

        Low morale (morale_mod < -0.05): concentration lapses, arguing,
        lack of effort on defensive tracking.

        High morale (morale_mod > 0.05): extra effort on tackles, better
        composure, tracking back more.
        """
        if self._match_context is None:
            return

        all_players = state.home_players + state.away_players

        for p in all_players:
            if not p.is_on_pitch or p.is_gk:
                continue

            morale_mod = getattr(p, "morale_mod", 0.0)
            team_name = h_name if p.side == "home" else a_name

            # Low morale effects
            if morale_mod < -0.05:
                # Concentration loss: turnover chance
                if random.random() < abs(morale_mod) * 0.03:
                    if state.ball_carrier == p:
                        state.commentary.append(
                            f"{minute}' {p.name} loses concentration and "
                            f"gives the ball away cheaply."
                        )
                        state.ball_side = "away" if p.side == "home" else "home"
                        state.ball_carrier = None
                        state._update_momentum(p.side, "turnover")

                # Arguing with referee: extra yellow card chance
                if random.random() < abs(morale_mod) * 0.005:
                    if p.yellow_cards < 2 and not p.red_card:
                        p.yellow_cards += 1
                        state._inc(p.side, "yellow_cards")
                        state.commentary.append(
                            f"{minute}' {p.name} is booked for dissent! "
                            f"Frustration boiling over for {team_name}."
                        )
                        state.events.append({
                            "minute": minute,
                            "type": "yellow_card",
                            "player": p.name,
                            "player_id": p.player_id,
                            "side": p.side,
                            "detail": "dissent",
                        })
                        if p.yellow_cards >= 2:
                            p.red_card = True
                            p.is_on_pitch = False
                            state._inc(p.side, "red_cards")
                            state.commentary.append(
                                f"{minute}' Second yellow! {p.name} is sent off!"
                            )
                            state._update_momentum(p.side, "red_card")

            # High morale effects
            elif morale_mod > 0.05:
                # Extra effort on tackles: small temporary fitness boost
                if random.random() < morale_mod * 0.02:
                    p.fitness_mod = min(1.0, p.fitness_mod + 0.01)

                # Better composure in big chances (applied passively via
                # higher effective() values from fitness_mod)

                # Track back more: slightly slower stamina drain offset
                # (effectively handled by the fitness_mod bump above)
