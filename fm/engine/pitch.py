"""18-zone pitch model for the match engine.

The pitch is divided into a 6×3 grid (columns × rows).
Columns represent depth (GK → final third), rows represent channels (left/center/right).
Each zone tracks which players are currently in it and computes control scores.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fm.engine.match_state import PlayerInMatch

# ── Zone column labels (depth on the pitch) ────────────────────────────────
class ZoneCol(IntEnum):
    GK_AREA = 0        # Goalkeeper box
    DEFENSE = 1        # Defensive third
    DEEP_MID = 2       # Deep midfield / DM area
    MIDFIELD = 3       # Central midfield
    ATTACK = 4         # Attacking midfield / space behind defence
    FINAL_THIRD = 5    # Final third / box

# ── Zone row labels (lateral channels) ─────────────────────────────────────
class ZoneRow(IntEnum):
    LEFT = 0
    CENTER = 1
    RIGHT = 2

# Number of cols/rows
N_COLS = 6
N_ROWS = 3


@dataclass
class Zone:
    """One of the 18 pitch zones."""
    col: int
    row: int
    home_players: list[PlayerInMatch] = field(default_factory=list)
    away_players: list[PlayerInMatch] = field(default_factory=list)

    @property
    def coord(self) -> tuple[int, int]:
        return (self.col, self.row)

    @property
    def is_wing(self) -> bool:
        return self.row in (ZoneRow.LEFT, ZoneRow.RIGHT)

    @property
    def is_central(self) -> bool:
        return self.row == ZoneRow.CENTER

    @property
    def is_final_third(self) -> bool:
        return self.col == ZoneCol.FINAL_THIRD

    @property
    def is_box(self) -> bool:
        return self.col == ZoneCol.FINAL_THIRD and self.row == ZoneRow.CENTER

    @property
    def is_defensive(self) -> bool:
        return self.col <= ZoneCol.DEFENSE

    def home_control(self) -> float:
        """Aggregate control score for the home team in this zone."""
        return sum(_player_zone_strength(p) for p in self.home_players)

    def away_control(self) -> float:
        return sum(_player_zone_strength(p) for p in self.away_players)

    def control_ratio(self, attacking_side: str) -> float:
        """Return 0.0-1.0 how much the attacking side controls this zone."""
        if attacking_side == "home":
            att, defe = self.home_control(), self.away_control()
        else:
            att, defe = self.away_control(), self.home_control()
        total = att + defe
        if total == 0:
            return 0.5
        return att / total

    def clear(self):
        self.home_players.clear()
        self.away_players.clear()


def _player_zone_strength(p: PlayerInMatch) -> float:
    """How much a player contributes to zone control."""
    base = (p.positioning + p.reactions + p.stamina_current * 0.5) / 3.0
    return max(base, 1.0)


class Pitch:
    """The 6×3 zone grid representing the football pitch.

    For the HOME team, column 0 is their GK area and column 5 is the
    opponent's final third.  For the AWAY team it's mirrored.
    """

    def __init__(self):
        self.zones: list[list[Zone]] = [
            [Zone(col=c, row=r) for r in range(N_ROWS)]
            for c in range(N_COLS)
        ]

    def get(self, col: int, row: int) -> Zone:
        return self.zones[col][row]

    def mirror_col(self, col: int) -> int:
        """Mirror a column index (away team sees the pitch reversed)."""
        return N_COLS - 1 - col

    def adjacent(self, col: int, row: int) -> list[tuple[int, int]]:
        """Return coordinates of zones adjacent to (col, row)."""
        neighbours = []
        for dc, dr in [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1),
                        (-1, 1), (1, -1), (1, 1)]:
            nc, nr = col + dc, row + dr
            if 0 <= nc < N_COLS and 0 <= nr < N_ROWS:
                neighbours.append((nc, nr))
        return neighbours

    def clear_all(self):
        """Remove all player references from every zone."""
        for col_zones in self.zones:
            for z in col_zones:
                z.clear()

    def place_players(self, players: list[PlayerInMatch], side: str):
        """Place a list of players into their assigned zones."""
        for p in players:
            z = self.get(p.zone_col, p.zone_row)
            if side == "home":
                z.home_players.append(p)
            else:
                z.away_players.append(p)

    def danger_rating(self, col: int, row: int, attacking_side: str) -> float:
        """How dangerous this zone is for creating a scoring chance.

        Returns 0.0-1.0.  Higher near the goal, boosted by control ratio.
        """
        # Column-based danger: higher in final third / box
        col_danger = {
            ZoneCol.GK_AREA: 0.0,
            ZoneCol.DEFENSE: 0.05,
            ZoneCol.DEEP_MID: 0.10,
            ZoneCol.MIDFIELD: 0.15,
            ZoneCol.ATTACK: 0.30,
            ZoneCol.FINAL_THIRD: 0.55,
        }
        base = col_danger.get(col, 0.1)
        # Central is more dangerous than wings
        if row == ZoneRow.CENTER:
            base *= 1.3
        control = self.get(col, row).control_ratio(attacking_side)
        return min(base * control * 2.0, 1.0)

    def text_heatmap(self, side: str) -> str:
        """Produce an ASCII heatmap of zone control for a side."""
        header = "  GK   DEF  DMID  MID  ATT  FIN"
        lines = [header]
        labels = ["L", "C", "R"]
        for r in range(N_ROWS):
            row_str = f"{labels[r]} "
            for c in range(N_COLS):
                z = self.get(c, r)
                ctrl = z.control_ratio(side)
                # Use block chars for intensity
                if ctrl > 0.7:
                    ch = "██"
                elif ctrl > 0.5:
                    ch = "▓▓"
                elif ctrl > 0.3:
                    ch = "▒▒"
                else:
                    ch = "░░"
                row_str += f" {ch}  "
            lines.append(row_str)
        return "\n".join(lines)
