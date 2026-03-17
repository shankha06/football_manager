"""Player roles and positional play logic.

Defines roles that influence player positioning (zone offsets) and 
action selection biases within the Match Engine.
"""
from __future__ import annotations
from enum import Enum, auto
from dataclasses import dataclass
from typing import Dict, Tuple

class PlayerRole(str, Enum):
    # Goalkeepers
    GK_TRADITIONAL = "GK"
    SWEEPER_GK = "SK"

    # Defenders
    CENTRE_BACK = "CB"
    LIBERO = "LIB"
    FULL_BACK = "FB"
    WING_BACK = "WB"
    INVERTED_WB = "IWB"
    INVERTED_FB = "IFB"

    # Midfielders
    DEFENSIVE_MID = "DM"
    DEEP_PLAYMAKER = "DLP"
    BOX_TO_BOX = "BBM"
    CENTRE_MID = "CM"
    BALL_WINNER = "BWM"
    ATTACKING_MID = "AM"
    ADV_PLAYMAKER = "AP"

    # Attackers / Wingers
    WINGER = "W"
    INVERTED_WINGER = "IW"
    INSIDE_FORWARD = "IF"
    STRIKER = "ST"
    FALSE_9 = "F9"
    TARGET_MAN = "TM"
    POACHER = "P"

@dataclass
class RoleMovement:
    """Offsets to apply to a player's base zone based on attacking/defending."""
    # (col_offset, row_offset)
    attack_offset: Tuple[int, int] = (0, 0)
    defend_offset: Tuple[int, int] = (0, 0)
    
    # Action biases for PlayerDecisionEngine
    # action_name -> weight_modifier
    action_biases: Dict[str, int] = None

# Registry of role-based movements and biases
ROLE_METADATA: Dict[PlayerRole, RoleMovement] = {
    PlayerRole.INVERTED_WB: RoleMovement(
        attack_offset=(1, 1), # Move forward and inside
        action_biases={"pass": 15, "cross": -10, "stay_narrow": 20}
    ),
    PlayerRole.INVERTED_FB: RoleMovement(
        attack_offset=(0, 1), # Tuck inside to form a back 3
        action_biases={"pass": 10, "stay_narrow": 15}
    ),
    PlayerRole.LIBERO: RoleMovement(
        attack_offset=(2, 0), # Push into midfield
        action_biases={"through_ball": 10, "long_ball": 5}
    ),
    PlayerRole.FALSE_9: RoleMovement(
        attack_offset=(-1, 0), # Drop deeper from striker spot
        action_biases={"pass": 15, "through_ball": 10, "shot": -5}
    ),
    PlayerRole.INSIDE_FORWARD: RoleMovement(
        attack_offset=(1, 1), # Cut inside towards goal
        action_biases={"shot": 10, "dribble": 8, "cross": -15}
    ),
    PlayerRole.BOX_TO_BOX: RoleMovement(
        attack_offset=(1, 0), # Support attack
        action_biases={"shot": 5, "run_in_behind": 5}
    ),
}

def get_role_offset(role: PlayerRole, is_attacking: bool) -> Tuple[int, int]:
    """Get the (col, row) offset for a given role and phase."""
    meta = ROLE_METADATA.get(role)
    if not meta:
        return (0, 0)
    return meta.attack_offset if is_attacking else meta.defend_offset

def get_role_biases(role: PlayerRole) -> Dict[str, int]:
    """Get the decision engine biases for a role."""
    meta = ROLE_METADATA.get(role)
    return meta.action_biases if meta and meta.action_biases else {}
