"""Event resolution engine.

Every match action (pass, shot, dribble, tackle, cross, header) is resolved
by comparing the relevant attributes of the attacking and defending players,
applying tactical modifiers, and rolling against the computed probability.
"""
from __future__ import annotations

import random
from dataclasses import dataclass

from fm.engine.match_state import PlayerInMatch
from fm.engine.tactics import TacticalContext
from fm.utils.helpers import clamp


@dataclass
class ResolutionResult:
    """Outcome of an event resolution."""
    success: bool
    xg_value: float = 0.0
    is_foul: bool = False
    is_yellow: bool = False
    is_red: bool = False
    hit_woodwork: bool = False
    is_blocked: bool = False
    detail: str = ""


def resolve_pass(
    passer: PlayerInMatch,
    receiver: PlayerInMatch,
    nearest_defender: PlayerInMatch | None,
    distance: float,
    tactics: TacticalContext,
    sabotage_penalty: float = 0.0,
) -> ResolutionResult:
    """Resolve a pass attempt.

    Args:
        distance: zone-distance between passer and receiver (0-5).
    """
    base = (
        passer.effective("short_passing") * 0.25
        + (passer.effective("vision") - sabotage_penalty * 99.0) * 0.35
        + (passer.effective("composure") - sabotage_penalty * 99.0) * 0.15
        + passer.effective("passing") * 0.10
        + passer.effective("ball_control") * 0.15
    )
    # Long passes use different weighting
    if distance >= 3:
        base = (
            passer.effective("long_passing") * 0.30
            + passer.effective("vision") * 0.40
            + passer.effective("composure") * 0.15
            + passer.effective("passing") * 0.05
            + passer.effective("shot_power") * 0.10  # power for distance
        )

    distance_penalty = distance * 4.0

    pressure = 0.0
    if nearest_defender:
        pressure = (
            nearest_defender.effective("interceptions") * 0.30
            + nearest_defender.effective("positioning") * 0.20
            + nearest_defender.effective("reactions") * 0.10
        )

    tactical_bonus = tactics.passing_modifier * 20.0  # scale to attr range
    tempo_penalty = abs(tactics.tempo_modifier) * 5.0  # extreme tempo = harder

    # --- Chemistry Bonus ---
    chemistry_bonus = 0.0
    if receiver.player_id in passer.chemistry_partners:
        strength = passer.chemistry_partners[receiver.player_id]
        # +0.02 to +0.08 extra success chance
        chemistry_bonus = (strength / 100.0) * 0.08

    success_chance = clamp(
        (base - distance_penalty - pressure * 0.5 + tactical_bonus - tempo_penalty) / 99.0 + chemistry_bonus,
        0.10, 0.95
    )

    passer.passes_attempted += 1
    success = random.random() < success_chance
    if success:
        passer.passes_completed += 1
        passer.rating_points += 0.02
        passer.rating_events += 1
    else:
        passer.rating_points -= 0.01
        passer.rating_events += 1

    return ResolutionResult(success=success)


def resolve_dribble(
    dribbler: PlayerInMatch,
    defender: PlayerInMatch | None,
    tactics: TacticalContext,
) -> ResolutionResult:
    """Resolve a dribble attempt past a defender."""
    dribbler.dribbles_attempted += 1

    base = (
        dribbler.effective("dribbling") * 0.30
        + dribbler.effective("agility") * 0.20
        + dribbler.effective("ball_control") * 0.20
        + dribbler.effective("balance") * 0.10
        + dribbler.effective("pace") * 0.10
    )

    challenge = 0.0
    is_foul = False
    is_yellow = False
    is_red = False

    if defender:
        challenge = (
            defender.effective("standing_tackle") * 0.30
            + defender.effective("physical") * 0.15
            + defender.effective("reactions") * 0.15
            + defender.effective("aggression") * 0.10
        )
        risk = tactics.risk_modifier
        base += risk * 8.0

        foul_chance = clamp(
            (defender.effective("aggression") * 0.4
             - defender.effective("standing_tackle") * 0.3) / 99.0
            + 0.05 + tactics.press_modifier * 0.05,
            0.02, 0.20
        )
        if random.random() < foul_chance:
            is_foul = True
            if is_foul:
                defender.fouls_committed += 1
                dribbler.fouls_won += 1
            card_roll = random.random()
            if card_roll < 0.03:
                is_red = True
            elif card_roll < 0.25:
                is_yellow = True

    success_chance = clamp((base - challenge * 0.5) / 99.0, 0.10, 0.85)
    success = random.random() < success_chance

    if success:
        dribbler.dribbles_completed += 1
        dribbler.rating_points += 0.05
        dribbler.rating_events += 1
    if defender and not success and not is_foul:
        defender.tackles_won += 1
        defender.tackles_attempted += 1
        defender.rating_points += 0.05
        defender.rating_events += 1

    return ResolutionResult(
        success=success, is_foul=is_foul, is_yellow=is_yellow, is_red=is_red
    )


def resolve_shot(
    shooter: PlayerInMatch,
    gk: PlayerInMatch | None,
    nearest_defender: PlayerInMatch | None,
    zone_col: int,
    zone_row: int,
    tactics: TacticalContext,
    sabotage_penalty: float = 0.0,
) -> ResolutionResult:
    """Resolve a shot on goal.

    Returns:
        ResolutionResult with xg_value set.
        success=True means GOAL.
    """
    # Base shooting quality
    is_close = zone_col >= 4 and zone_row == 1     # central final third / box
    is_long_range = zone_col <= 3

    if is_close:
        base = (
            shooter.effective("finishing") * 0.30
            + (shooter.effective("composure") - sabotage_penalty * 99.0) * 0.35
            + shooter.effective("positioning") * 0.20
            + shooter.effective("shot_power") * 0.15
        )
    else:
        base = (
            shooter.effective("long_shots") * 0.25
            + shooter.effective("shot_power") * 0.30
            + shooter.effective("curve") * 0.15
            + (shooter.effective("composure") - sabotage_penalty * 99.0) * 0.20
            + (shooter.effective("vision") - sabotage_penalty * 99.0) * 0.10  # sensing goal position
        )

    # Risk/mentality modifier
    base += tactics.risk_modifier * 10.0

    # Defender blocking
    block_chance = 0.0
    if nearest_defender:
        block_chance = clamp(
            (nearest_defender.effective("marking") * 0.3
             + nearest_defender.effective("positioning") * 0.3) / 99.0,
            0.05, 0.40
        )

    # xG calculation
    distance_factor = max(1.0, (5 - zone_col)) * 0.15
    centrality = 1.0 if zone_row == 1 else 0.65
    raw_xg = clamp(
        (base / 99.0) * centrality * (1.0 - distance_factor) * (1.0 - block_chance * 0.5),
        0.01, 0.75
    )

    # Is this a big chance? (close range, central, high xG)
    is_big_chance = is_close and raw_xg > 0.25
    if is_big_chance:
        shooter.big_chances += 1

    # Blocked?
    if random.random() < block_chance * 0.6:
        shooter.shots += 1
        shooter.shots_blocked += 1
        shooter.rating_events += 1
        if nearest_defender:
            nearest_defender.blocks += 1
        return ResolutionResult(success=False, xg_value=raw_xg, detail="blocked", is_blocked=True)

    # On target? (real football: ~33-37% of all shots are on target)
    # Close range shots are more accurate, long range less
    if is_close:
        accuracy = clamp(base / 99.0 * 0.60, 0.30, 0.60)
    else:
        accuracy = clamp(base / 99.0 * 0.35, 0.08, 0.35)
    on_target = random.random() < accuracy
    shooter.shots += 1

    if not on_target:
        # ~8% of off-target shots hit the woodwork
        woodwork = random.random() < 0.08
        if woodwork:
            shooter.hit_woodwork += 1
            shooter.rating_events += 1
            return ResolutionResult(success=False, xg_value=raw_xg, detail="woodwork", hit_woodwork=True)
        shooter.rating_events += 1
        if is_big_chance:
            shooter.big_chances_missed += 1
        return ResolutionResult(success=False, xg_value=raw_xg, detail="off_target")

    shooter.shots_on_target += 1

    # GK save attempt
    if gk:
        gk_quality = (
            gk.effective("gk_reflexes") * 0.30
            + gk.effective("gk_diving") * 0.25
            + gk.effective("gk_positioning") * 0.25
            + gk.effective("gk_handling") * 0.10
        )
        # GK save: real football ~68-70% of on-target shots are saved
        # High xG shots (close range) harder to save, low xG (long range) easier
        save_chance = clamp(gk_quality / 99.0 * (1.0 - raw_xg * 0.5) + 0.12, 0.18, 0.74)
        if random.random() < save_chance:
            gk.saves += 1
            gk.rating_points += 0.15
            gk.rating_events += 1
            shooter.rating_events += 1
            if is_big_chance:
                shooter.big_chances_missed += 1
            return ResolutionResult(success=False, xg_value=raw_xg, detail="saved")

    # GOAL!
    shooter.goals += 1
    shooter.rating_points += 0.5
    shooter.rating_events += 1
    return ResolutionResult(success=True, xg_value=raw_xg, detail="goal")


def resolve_cross(
    crosser: PlayerInMatch,
    target: PlayerInMatch | None,
    defender: PlayerInMatch | None,
    tactics: TacticalContext,
) -> ResolutionResult:
    """Resolve a cross into the box."""
    crosser.crosses_attempted += 1

    base = (
        crosser.effective("crossing") * 0.40
        + crosser.effective("curve") * 0.15
        + crosser.effective("vision") * 0.15
    )

    base += tactics.width_modifier * 12.0

    defend_quality = 0.0
    if defender:
        defend_quality = (
            defender.effective("heading_accuracy") * 0.20
            + defender.effective("jumping") * 0.20
            + defender.effective("positioning") * 0.15
        )

    success_chance = clamp((base - defend_quality * 0.4) / 99.0, 0.15, 0.75)
    success = random.random() < success_chance
    if success:
        crosser.crosses_completed += 1

    return ResolutionResult(success=success)


def resolve_header(
    header_player: PlayerInMatch,
    gk: PlayerInMatch | None,
    defender: PlayerInMatch | None,
    tactics: TacticalContext,
) -> ResolutionResult:
    """Resolve a header on goal after a cross."""
    base = (
        header_player.effective("heading_accuracy") * 0.35
        + header_player.effective("jumping") * 0.25
        + header_player.effective("positioning") * 0.15
        + header_player.effective("strength") * 0.10
    )

    # Headers from crosses: real football ~7-8% of headed shots score
    # Close-range headers (e.g. 6-yard box) should have higher xG
    raw_xg = clamp(base / 99.0 * 0.55, 0.03, 0.55)

    # Aerial duel
    header_player.aerials_won += 1
    if defender:
        def_quality = (
            defender.effective("heading_accuracy") * 0.25
            + defender.effective("jumping") * 0.25
            + defender.effective("strength") * 0.15
        )
        if def_quality > base * 0.8:
            defender.aerials_won += 1
            header_player.aerials_lost += 1
        else:
            defender.aerials_lost += 1
        base -= def_quality * 0.35

    on_target_chance = clamp(base / 99.0, 0.15, 0.70)
    on_target = random.random() < on_target_chance

    header_player.shots += 1

    if not on_target:
        # Woodwork chance on headers too
        if random.random() < 0.06:
            header_player.hit_woodwork += 1
            header_player.rating_events += 1
            return ResolutionResult(success=False, xg_value=raw_xg, detail="woodwork", hit_woodwork=True)
        header_player.rating_events += 1
        return ResolutionResult(success=False, xg_value=raw_xg, detail="headed_wide")

    header_player.shots_on_target += 1

    if gk:
        save_quality = (
            gk.effective("gk_reflexes") * 0.25
            + gk.effective("gk_handling") * 0.25
            + gk.effective("gk_positioning") * 0.25
        )
        save_chance = clamp(save_quality / 99.0 * 0.7, 0.10, 0.60)
        if random.random() < save_chance:
            gk.saves += 1
            gk.rating_points += 0.15
            gk.rating_events += 1
            return ResolutionResult(success=False, xg_value=raw_xg, detail="saved")

    header_player.goals += 1
    header_player.rating_points += 0.5
    header_player.rating_events += 1
    return ResolutionResult(success=True, xg_value=raw_xg, detail="headed_goal")


def resolve_tackle(
    tackler: PlayerInMatch,
    ball_carrier: PlayerInMatch,
    tactics: TacticalContext,
) -> ResolutionResult:
    """Resolve a tackle attempt (defender initiating)."""
    tackler.tackles_attempted += 1

    tackle_quality = (
        tackler.effective("standing_tackle") * 0.30
        + tackler.effective("reactions") * 0.15
        + tackler.effective("aggression") * 0.15
        + tackler.effective("physical") * 0.10
    )
    tackle_quality += tactics.press_modifier * 10.0

    evade_quality = (
        ball_carrier.effective("dribbling") * 0.25
        + ball_carrier.effective("agility") * 0.20
        + ball_carrier.effective("balance") * 0.15
    )

    success_chance = clamp((tackle_quality - evade_quality * 0.4) / 99.0, 0.15, 0.70)
    success = random.random() < success_chance

    is_foul = False
    is_yellow = False
    is_red = False
    foul_chance = clamp(
        (tackler.effective("aggression") * 0.3
         - tackler.effective("standing_tackle") * 0.2) / 99.0
        + 0.05,
        0.03, 0.18
    )
    if random.random() < foul_chance:
        is_foul = True
        tackler.fouls_committed += 1
        ball_carrier.fouls_won += 1
        card_roll = random.random()
        if card_roll < 0.02:
            is_red = True
        elif card_roll < 0.22:
            is_yellow = True

    if success and not is_foul:
        tackler.tackles_won += 1
        tackler.rating_points += 0.05
        tackler.rating_events += 1

    return ResolutionResult(
        success=success and not is_foul,
        is_foul=is_foul,
        is_yellow=is_yellow,
        is_red=is_red,
    )


def resolve_interception(
    interceptor: PlayerInMatch,
    passer: PlayerInMatch,
    pass_distance: float,
) -> ResolutionResult:
    """Check if a pass gets intercepted by a nearby defender."""
    intercept_quality = (
        interceptor.effective("interceptions") * 0.40
        + interceptor.effective("positioning") * 0.25
        + interceptor.effective("reactions") * 0.20
    )

    pass_quality = (
        passer.effective("passing") * 0.30
        + passer.effective("vision") * 0.20
    )

    # Longer passes are easier to intercept
    distance_bonus = pass_distance * 3.0

    chance = clamp(
        (intercept_quality + distance_bonus - pass_quality) / 200.0,
        0.02, 0.30
    )
    success = random.random() < chance

    if success:
        interceptor.interceptions_made += 1
        interceptor.rating_points += 0.08
        interceptor.rating_events += 1

    return ResolutionResult(success=success)


def resolve_penalty(
    taker: PlayerInMatch,
    gk: PlayerInMatch | None,
    tactics: TacticalContext,
) -> ResolutionResult:
    """Penalty kick - ~76% conversion rate.

    Uses the taker's penalties, composure and shot_power attributes
    against the GK's gk_diving and gk_reflexes.
    """
    # Base quality from penalty taker
    base = (
        taker.effective("penalties") * 0.35
        + taker.effective("composure") * 0.30
        + taker.effective("shot_power") * 0.20
        + taker.effective("finishing") * 0.15
    )

    raw_xg = 0.76  # standard penalty xG

    # On target? Penalties are almost always on target
    accuracy = clamp(base / 99.0, 0.80, 0.98)
    on_target = random.random() < accuracy
    taker.shots += 1

    if not on_target:
        # Missed penalty — off target or hit woodwork
        if random.random() < 0.15:
            taker.hit_woodwork += 1
            taker.rating_points -= 0.15
            taker.rating_events += 1
            return ResolutionResult(
                success=False, xg_value=raw_xg, detail="woodwork",
                hit_woodwork=True,
            )
        taker.rating_points -= 0.20
        taker.rating_events += 1
        taker.big_chances += 1
        taker.big_chances_missed += 1
        return ResolutionResult(
            success=False, xg_value=raw_xg, detail="off_target",
        )

    taker.shots_on_target += 1

    # GK save attempt
    if gk:
        gk_quality = (
            gk.effective("gk_diving") * 0.40
            + gk.effective("gk_reflexes") * 0.30
            + gk.effective("gk_positioning") * 0.15
        )
        # Penalty save: ~17-20% of on-target pens saved (real: 76-77% conversion)
        save_chance = clamp(gk_quality / 99.0 * 0.38, 0.08, 0.24)
        if random.random() < save_chance:
            gk.saves += 1
            gk.rating_points += 0.30
            gk.rating_events += 1
            taker.rating_points -= 0.15
            taker.rating_events += 1
            taker.big_chances += 1
            taker.big_chances_missed += 1
            return ResolutionResult(
                success=False, xg_value=raw_xg, detail="saved",
            )

    # GOAL!
    taker.goals += 1
    taker.big_chances += 1
    taker.rating_points += 0.40
    taker.rating_events += 1
    return ResolutionResult(success=True, xg_value=raw_xg, detail="penalty_goal")


def resolve_free_kick(
    taker: PlayerInMatch,
    gk: PlayerInMatch | None,
    nearest_defender: PlayerInMatch | None,
    distance: float,
    tactics: TacticalContext,
) -> ResolutionResult:
    """Direct free kick attempt.

    Args:
        distance: notional distance from goal (lower = closer).  Typically
                  1.0 for edge-of-box, 2.0+ for further out.
    """
    base = (
        taker.effective("free_kick_accuracy") * 0.35
        + taker.effective("curve") * 0.25
        + taker.effective("shot_power") * 0.20
        + taker.effective("composure") * 0.10
    )

    # Distance penalty — further out is harder
    distance_factor = clamp(distance * 0.10, 0.0, 0.40)

    # Raw xG for a direct free kick (typically 0.04-0.12)
    raw_xg = clamp(
        (base / 99.0) * 0.20 * (1.0 - distance_factor),
        0.02, 0.15,
    )

    # Wall / block chance
    wall_block = 0.25
    if nearest_defender:
        wall_block += clamp(
            nearest_defender.effective("positioning") / 99.0 * 0.10,
            0.0, 0.15,
        )

    if random.random() < wall_block:
        taker.shots += 1
        taker.shots_blocked += 1
        taker.rating_events += 1
        if nearest_defender:
            nearest_defender.blocks += 1
        return ResolutionResult(
            success=False, xg_value=raw_xg, detail="blocked",
            is_blocked=True,
        )

    # On target?
    accuracy = clamp(base / 99.0 * 0.6, 0.10, 0.55)
    on_target = random.random() < accuracy
    taker.shots += 1

    if not on_target:
        if random.random() < 0.10:
            taker.hit_woodwork += 1
            taker.rating_events += 1
            return ResolutionResult(
                success=False, xg_value=raw_xg, detail="woodwork",
                hit_woodwork=True,
            )
        taker.rating_events += 1
        return ResolutionResult(
            success=False, xg_value=raw_xg, detail="off_target",
        )

    taker.shots_on_target += 1

    # GK save
    if gk:
        gk_quality = (
            gk.effective("gk_diving") * 0.30
            + gk.effective("gk_reflexes") * 0.30
            + gk.effective("gk_positioning") * 0.20
        )
        save_chance = clamp(gk_quality / 99.0 * 0.65, 0.15, 0.70)
        if random.random() < save_chance:
            gk.saves += 1
            gk.rating_points += 0.15
            gk.rating_events += 1
            return ResolutionResult(
                success=False, xg_value=raw_xg, detail="saved",
            )

    # GOAL from free kick!
    taker.goals += 1
    taker.rating_points += 0.50
    taker.rating_events += 1
    return ResolutionResult(success=True, xg_value=raw_xg, detail="free_kick_goal")
