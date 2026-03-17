"""Markov chain states for the V3 possession-based match engine.

Each possession chain walks through these states until hitting a terminal
state (goal, turnover, set piece awarded, penalty).  Transition probabilities
between states are computed dynamically by TransitionCalculator based on
team attributes, tactics, and match context.
"""
from __future__ import annotations

import enum


class ChainState(enum.Enum):
    GOAL_KICK = "goal_kick"
    BUILDUP_DEEP = "buildup_deep"
    BUILDUP_MID = "buildup_mid"
    PROGRESSION = "progression"
    CHANCE_CREATION = "chance_creation"
    SHOT = "shot"
    GOAL = "goal"
    CROSS = "cross"
    SET_PIECE_CORNER = "set_piece_corner"
    SET_PIECE_FK_DIRECT = "set_piece_fk_direct"
    SET_PIECE_FK_INDIRECT = "set_piece_fk_indirect"
    PENALTY = "penalty"
    TURNOVER = "turnover"
    COUNTER_ATTACK = "counter_attack"
    TRANSITION = "transition"
    LONG_BALL = "long_ball"
    PRESS_TRIGGERED = "press_triggered"


# Terminal states (possession ends)
TERMINAL_STATES = {
    ChainState.GOAL,
    ChainState.TURNOVER,
    ChainState.SET_PIECE_CORNER,
    ChainState.SET_PIECE_FK_DIRECT,
    ChainState.SET_PIECE_FK_INDIRECT,
    ChainState.PENALTY,
}

# States that lead to shots
SHOT_STATES = {ChainState.SHOT, ChainState.CROSS}
