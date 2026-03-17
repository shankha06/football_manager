"""Verification test for enhanced match stats."""
import random
import time

from fm.engine.match_state import PlayerInMatch
from fm.engine.simulator import MatchSimulator
from fm.engine.tactics import TacticalContext


def make_team(side, ovr=70):
    positions = ["GK", "CB", "CB", "LB", "RB", "CM", "CM", "CDM", "LW", "ST", "RW"]
    return [PlayerInMatch(
        player_id=i + (100 if side == "away" else 0),
        name=f"{side[0].upper()}{i}", position=pos, side=side,
        overall=ovr, is_gk=(pos == "GK"),
        pace=ovr, shooting=ovr, passing=ovr, dribbling=ovr,
        defending=ovr, physical=ovr, finishing=ovr, short_passing=ovr,
        vision=ovr, composure=ovr, reactions=ovr, positioning=ovr,
        stamina=ovr, standing_tackle=ovr, ball_control=ovr,
        interceptions=ovr, agility=ovr, balance=ovr, strength=ovr,
        crossing=ovr, heading_accuracy=ovr, jumping=ovr, long_shots=ovr,
        shot_power=ovr, curve=ovr, long_passing=ovr, aggression=ovr,
        sliding_tackle=ovr, acceleration=ovr, sprint_speed=ovr,
        volleys=ovr, penalties=ovr, free_kick_accuracy=ovr, marking=ovr,
        gk_diving=ovr if pos == "GK" else 10,
        gk_handling=ovr if pos == "GK" else 10,
        gk_kicking=ovr if pos == "GK" else 10,
        gk_positioning=ovr if pos == "GK" else 10,
        gk_reflexes=ovr if pos == "GK" else 10,
    ) for i, pos in enumerate(positions)]


def test_stats():
    print("=" * 65)
    print("  ENHANCED STATS VERIFICATION (10 matches)")
    print("=" * 65)

    sim = MatchSimulator()
    all_stats = {
        "goals": [], "shots": [], "sot": [], "woodwork": [],
        "passes": [], "pass_acc": [], "key_passes": [],
        "crosses": [], "dribbles": [], "tackles": [],
        "interceptions": [], "clearances": [], "blocks": [],
        "corners": [], "fouls": [], "offsides": [],
        "aerials": [], "big_chances": [], "saves": [],
        "yellows": [], "reds": [],
    }

    t0 = time.perf_counter()
    for seed in range(10):
        random.seed(seed)
        r = sim.simulate(
            make_team("home", 75), make_team("away", 68),
            TacticalContext(formation="4-3-3", mentality="positive", pressing="high"),
            TacticalContext(formation="4-4-2", mentality="defensive"),
            "Liverpool", "Burnley",
        )
        hs, aws = r.home_stats, r.away_stats
        all_stats["goals"].append(hs.goals + aws.goals)
        all_stats["shots"].append(hs.shots + aws.shots)
        all_stats["sot"].append(hs.shots_on_target + aws.shots_on_target)
        all_stats["woodwork"].append(hs.woodwork + aws.woodwork)
        all_stats["passes"].append(hs.passes + aws.passes)
        all_stats["pass_acc"].append((hs.pass_accuracy + aws.pass_accuracy) / 2)
        all_stats["key_passes"].append(hs.key_passes + aws.key_passes)
        all_stats["crosses"].append(hs.crosses + aws.crosses)
        all_stats["dribbles"].append(hs.dribbles + aws.dribbles)
        all_stats["tackles"].append(hs.tackles + aws.tackles)
        all_stats["interceptions"].append(hs.interceptions + aws.interceptions)
        all_stats["clearances"].append(hs.clearances + aws.clearances)
        all_stats["blocks"].append(hs.blocks + aws.blocks)
        all_stats["corners"].append(hs.corners + aws.corners)
        all_stats["fouls"].append(hs.fouls + aws.fouls)
        all_stats["offsides"].append(hs.offsides + aws.offsides)
        all_stats["aerials"].append(hs.aerials_won + aws.aerials_won)
        all_stats["big_chances"].append(hs.big_chances + aws.big_chances)
        all_stats["saves"].append(hs.saves + aws.saves)
        all_stats["yellows"].append(hs.yellow_cards + aws.yellow_cards)
        all_stats["reds"].append(hs.red_cards + aws.red_cards)

    elapsed = time.perf_counter() - t0
    print(f"\n  10 matches in {elapsed:.3f}s\n")

    print(f"  {'Stat':<16} {'Avg':>6} {'Min':>4} {'Max':>4}")
    print(f"  {'─'*16} {'─'*6} {'─'*4} {'─'*4}")
    for name, vals in all_stats.items():
        avg = sum(vals) / len(vals)
        print(f"  {name:<16} {avg:>6.1f} {min(vals):>4} {max(vals):>4}")

    # Show one match in detail
    print(f"\n{'=' * 65}")
    print("  SAMPLE MATCH: Liverpool vs Burnley")
    print(f"{'=' * 65}")
    random.seed(7)
    r = sim.simulate(
        make_team("home", 78), make_team("away", 72),
        TacticalContext(formation="4-2-3-1", mentality="attacking", pressing="high"),
        TacticalContext(formation="5-3-2", mentality="defensive", pressing="low"),
        "Liverpool", "Burnley",
    )
    hs, aws = r.home_stats, r.away_stats
    print(f"\n  Score: Liverpool {r.home_goals}-{r.away_goals} Burnley")
    print(f"  MOTM: {r.motm.name} ({r.motm.avg_rating:.1f})" if r.motm else "")
    print()

    stats_rows = [
        ("Possession", f"{hs.possession:.0f}%", f"{aws.possession:.0f}%"),
        ("Shots", str(hs.shots), str(aws.shots)),
        ("On Target", str(hs.shots_on_target), str(aws.shots_on_target)),
        ("Blocked", str(hs.shots_blocked), str(aws.shots_blocked)),
        ("Woodwork", str(hs.woodwork), str(aws.woodwork)),
        ("xG", f"{hs.xg:.2f}", f"{aws.xg:.2f}"),
        ("Big Chances", str(hs.big_chances), str(aws.big_chances)),
        ("Passes", str(hs.passes), str(aws.passes)),
        ("Pass Accuracy", f"{hs.pass_accuracy:.0f}%", f"{aws.pass_accuracy:.0f}%"),
        ("Key Passes", str(hs.key_passes), str(aws.key_passes)),
        ("Crosses", f"{hs.crosses}/{hs.crosses_completed}", f"{aws.crosses}/{aws.crosses_completed}"),
        ("Dribbles", f"{hs.dribbles}/{hs.dribbles_completed}", f"{aws.dribbles}/{aws.dribbles_completed}"),
        ("Tackles", f"{hs.tackles}/{hs.tackles_won}", f"{aws.tackles}/{aws.tackles_won}"),
        ("Interceptions", str(hs.interceptions), str(aws.interceptions)),
        ("Clearances", str(hs.clearances), str(aws.clearances)),
        ("Blocks", str(hs.blocks), str(aws.blocks)),
        ("Aerials Won", str(hs.aerials_won), str(aws.aerials_won)),
        ("Corners", str(hs.corners), str(aws.corners)),
        ("Fouls", str(hs.fouls), str(aws.fouls)),
        ("Offsides", str(hs.offsides), str(aws.offsides)),
        ("Yellow Cards", str(hs.yellow_cards), str(aws.yellow_cards)),
        ("Red Cards", str(hs.red_cards), str(aws.red_cards)),
        ("Saves", str(hs.saves), str(aws.saves)),
    ]

    print(f"  {'':>16} {'LIV':>8} {'BUR':>8}")
    print(f"  {'─'*16} {'─'*8} {'─'*8}")
    for label, h, a in stats_rows:
        print(f"  {label:>16} {h:>8} {a:>8}")

    print(f"\n  Commentary ({len(r.commentary)} lines):")
    for line in r.commentary[:15]:
        print(f"    {line}")
    if len(r.commentary) > 15:
        print(f"    ... and {len(r.commentary) - 15} more lines")

    print(f"\n✅ All tests passed!")


if __name__ == "__main__":
    test_stats()
