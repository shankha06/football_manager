# ⚽ Player Stats Quick Reference

Fast lookup for all 80+ player attributes and their ranges.

---

## 📋 Attribute Categories at a Glance

| Category | Count | Range | Purpose |
|----------|-------|-------|---------|
| Technical Skills | 31 | 1-99 | In-match abilities |
| Personality | 13 | 1-99 | Character/decision-making |
| Hidden | 3 | 1-99 | Derived, non-visible |
| Dynamic State | 7 | 0-100 | Real-time match-affecting |
| Mental (Non-Technical) | 7 | 1-99 | Composure, positioning, reactions |
| Physical Profile | 5 | Varies | Height, weight, foot, weak foot |
| Contract/Financial | 9 | Currency | Wages, bonuses, clauses |
| Psychological State | 5 | 0-100 | Happiness, trust, loyalty, morale |
| Season Trackers | 3 | Count | Goals, assists, minutes |
| Match Performance | 24 | Varies | Per-match detailed stats |
| Goalkeeper-Specific | 6 | 1-99 | GK abilities only |
| Work Rates | 2 | Text | Attacking/defensive effort |

---

## 🎯 Core Ability Scales

### Overall Rating System
```
Display Scale: 1-99
Backend Scale: 1-200 (internal calculations)
Relationship: overall ≈ (current_ability / 2) + 0.5

Examples:
50 overall = ~100 internal (average player)
75 overall = ~150 internal (elite)
99 overall = ~200 internal (world-class)
```

### Potential Development
```
potential_ability: 1-200 (ceiling)
current_ability: 1-200 (current level)

Players develop when:
- Young (age 16-28): +0.5-1.5 potential per season
- Peak (28-32): Flat
- Declining (32+): -1-2 potential per season

Growth boosted by:
- Promises fulfilled: +5
- Manager youth_development 80+: +1
- Regular playing time: +1
- Training focus on development: +0.5
```

---

## 🏃 Technical Skills (All 1-99 Scale)

### Attacking (6 attributes)
| Skill | Usage | Soft Cap |
|-------|-------|----------|
| **Shooting** | Overall finishing ability | CF/ST: 85+ |
| **Finishing** | Clear chance conversion | ST: 90+ |
| **Shot Power** | Distance accuracy | Varies |
| **Long Shots** | 25+ yard accuracy | Wingers/CM: 70+ |
| **Volleys** | Half-volley finishing | ST: 75+ |
| **Penalties** | Spot kick success | Forward/Midfield |

### Passing & Vision (7 attributes)
| Skill | Usage | Soft Cap |
|-------|-------|----------|
| **Passing** | Overall pass quality | CM: 85+, GK: 70+ |
| **Vision** | Chance spotting | CAM/CM: 80+ |
| **Short Passing** | 5-15 yard accuracy | Midfielder: 85+ |
| **Long Passing** | 20+ yard accuracy | CM/Defense: 80+ |
| **Crossing** | Wing deliver accuracy | Winger/RB: 80+ |
| **Free Kick Accuracy** | Direct FK shots | Midfielder: 75+ |
| **Curve** | Ball bending | Winger/FK taker: 75+ |

### Dribbling (4 attributes)
| Skill | Usage | Soft Cap |
|-------|-------|----------|
| **Dribbling** | 1v1 vs defender | Winger: 85+, Forward: 80+ |
| **Agility** | Quick direction change | Winger: 80+ |
| **Balance** | Ball control under pressure | Winger: 80+ |
| **Ball Control** | Touch quality | Winger: 85+, Forward: 80+ |

### Defensive (7 attributes)
| Skill | Usage | Soft Cap |
|-------|-------|----------|
| **Defending** | Core defensive position | CB: 85+, FB: 80+ |
| **Marking** | Tracking opponents | CB: 80+, Midfielder: 75+ |
| **Standing Tackle** | Direct tackle success | CB: 80+, CDM: 78+ |
| **Sliding Tackle** | Emergency defensive | CB: 75+, FB: 75+ |
| **Interceptions** | Reading play ahead | CB: 80+, CDM: 75+ |
| **Heading Accuracy** | Header accuracy & power | CB: 75+, Striker: 75+ |
| **Jumping** | Aerial leap | CB: 75+, Striker: 75+ |

### Physical (4 attributes)
| Skill | Usage | Soft Cap |
|-------|-------|----------|
| **Pace** | Overall speed rating | Winger/ST: 85+ |
| **Acceleration** | 0-100m explosive | Winger: 85+, FB: 80+ |
| **Sprint Speed** | 30m+ top speed | Forward: 85+, Winger: 85+ |
| **Stamina** | 90-min fatigue resist | Midfielder: 85+, Forward: 80+ |
| **Strength** | Physical power duels | CB: 80+, CDM: 75+ |

### Mental Game (3 attributes)
| Skill | Usage | Soft Cap |
|-------|-------|----------|
| **Composure** | Pressure/decision-making | Midfielder: 80+ |
| **Reactions** | Split-second response | GK: 85+, Forward: 75+ |
| **Positioning** | Tactical awareness | CB: 80+, GK: 85+ |

### Work Rates (2 qualitative)
| Rate | Options | Effect |
|------|---------|--------|
| **Attacking** | Low/Medium/High | Run frequency forward |
| **Defensive** | Low/Medium/High | Pressure on ball |

### Goalkeeper-Specific (6, GK only, 1-99)
| GK Skill | Key For | Soft Cap |
|----------|---------|----------|
| **GK Diving** | Shot-stopping saves | 80+ |
| **GK Handling** | Cross catching/punches | 80+ |
| **GK Kicking** | Distribution accuracy | 75+ |
| **GK Positioning** | Sweeper positioning | 80+ |
| **GK Reflexes** | Reaction speed | 85+ |
| **GK Speed** | Distribution tempo | 70+ |

---

## 🧠 Mental Attributes (1-99)

| Attribute | Low (<40) | Average (40-60) | High (80+) |
|-----------|-----------|-----------------|-----------|
| **Leadership** | No captain role | Squad member | Can lead, morale x1.5 |
| **Temperament** | Red card risk 1.2x | Normal | Very calm, 0.8x reds |
| **Professionalism** | Discipline problems | Normal attendance | Perfect conduct |
| **Determination** | Easily depressed | Standard motivation | Comeback resilience |
| **Ambition** | Content anywhere | Typical goals | Demands top clubs |
| **Loyalty** | Quick transfer | Stable | Stays through adversity |
| **Pressure Handling** | Form -8 in stress | Normal impact | Form -2 only |
| **Adaptability** | New position -5 | Standard | No penalty |
| **Versatility** | Position-locked | 1-2 positions | 2-3 positions effective |
| **Dirtiness** | Rarely fouls | Normal fouls | Yellow cards x1.3 |
| **Flair** | Basic play | Mixed style | Showboating, skill moves |
| **Important Matches** | Form -8 finals | Normal | Form +5 finals |
| **Consistent** | Form wildly varies | Predictable | Very reliable |

---

## 🎭 Psychological State (Real-Time, 0-100)

| Stat | Excellent | Good | Average | Poor | Critical |
|------|-----------|------|---------|------|----------|
| **Happiness** | 80+ +2 form | 65-79 normal | 50-64 | 35-49 -2 form | <35 transfers |
| **Morale** | 80+ bonus | 65-79 normal | 50-64 | 45-49 warning | <45 red alert |
| **Form** | 80+ xG +15% | 65+ normal | 50-64 | 35-49 xG -10% | <35 xG -20% |
| **Trust/Manager** | 80+ believes tactics | 50-79 neutral | <50 doubts tactics | — | — |
| **Loyalty to Manager** | 80+ accepts bench | 50-79 neutral | <50 morale -3 | — | — |

### Form Calculation (EWMA)
```
form = 0.4 * last_match_rating + 0.6 * previous_form
Example progression:
Match rating 7.0 → form 65: new = 0.4(7) + 0.6(65) = 2.8 + 39 = 41.8
```

---

## 🏥 Dynamic State (Match-Affecting)

| State | Range | What It Does | Recovery |
|-------|-------|-------------|----------|
| **Fitness** | 0-100 | Fatigue penalty to pace/stamina | +10 per rest day |
| **Injured Weeks** | 0-52 | Days/weeks unavailable | -0.5 weeks/day rest |
| **Suspended Matches** | 0-5 | Red card bans | -1 after each fixture |
| **Yellow Cards (Season)** | 0+ | Accumulation toward bans | Trigger ban at 10 |
| **Red Cards (Season)** | 0+ | Automatic 3-5 match ban | -10 morale per red |
| **Match Sharpness** | 0-100 | Regular player? | +15 per start |
| **Team Chemistry** | 0-100 | Squad connection | +3 per week training |
| **Tactical Familiarity** | 0-100 | Position comfort | +5 per start in spot |

---

## 🎖️ Personality Categories & Effects

### Leadership Tier
- **80+**: Can be captain, +1.5x morale to squad from wins
- **50-79**: Squad member, normal morale
- **<50**: Weak personality, -1 morale to squad from losses

### Temperament Tier (Red Card Risk)
- **80+**: Very calm, red card chance 0.8x
- **50-79**: Normal discipline
- **30-49**: Hot-headed, red card chance 1.2x

### Professionalism Tier
- **80+**: Perfect conduct, never misses training
- **50-79**: Normal discipline
- **<40**: Conduct issues, team morale -2

---

## 📊 Season Accumulators (Reset at Season End)

| Stat | Type | Usage |
|------|------|-------|
| **Goals Season** | Counter | Used for highlights, form triggers |
| **Assists Season** | Counter | Used for performance metrics |
| **Minutes Season** | Counter | Workload assessment, rotation |
| **Appearances Season** | Derived | Number of matches played |
| **Avg Rating Season** | Derived | Average of all match ratings |

Final stats saved to `PlayerStats` table, then accumulators reset.

---

## ⚔️ Match Performance (Per-Match Stats)

### Attacking (8 attributes)
```
goals, assists, shots, shots_on_target, key_passes, 
through_balls, xG (expected goals), xa (expected assists)
```

### Passing (4 attributes)
```
passes_attempted, passes_completed, crosses_attempted, crosses_completed
Accuracy = completed / attempted
```

### Defensive (7 attributes)
```
tackles_attempted, tackles_won, interceptions, clearances, blocks,
fouls_committed, fouls_won
```

### Aerial (2 attributes)
```
aerials_won, aerials_lost
```

### Discipline (3 attributes)
```
yellow_cards, red_card (bool), fouls_committed
```

### Physical (2 attributes)
```
distance_covered_km, touches
```

### Goalkeeper-Specific (2 attributes, GK only)
```
saves, clean_sheet (bool)
```

---

## 🔗 Stat Interconnection Quick Map

```
Goal Scored
├→ form +2-4 (scorer only)
├→ morale +3-5 (scorer) / team +0.5-1
├→ rating +1.5 (scorer)
├→ confidence boost (next match +2 form)
└→ friend networks: friends +1 morale each

Loss
├→ morale -5 to -8 (squad)
├→ form -2 to -4 (squad)
├→ fan_happiness -3 (club-wide)
├→ board_confidence -5 (coach eval)
└→ momentum -0.25 (team psychological state)

Red Card
├→ form -20 (player)
├→ morale -8 (player) / team -5
├→ suspended_matches = 3-5
├→ red_cards_season += 1
└→ cascades: team spirit -8, friend networks -2 morale

Injury (Moderate, 6 weeks)
├→ form -8 (can't play) / +recovery each week
├→ morale -5/day (benched)
├→ fitness 100→75% on return
├→ injury_proneness plays: reinjury_window 2-4 weeks
└→ cascades: friend networks -3, squad spirit -8

Long Benching (5+ matches)
├→ match_sharpness -5/match benched
├→ morale -3/day benched
├→ form -0.5/day
├→ consecutive_benched counter ++
└→ if 8+ matches benched: transfer_request triggers

Win (Squad)
├→ morale +2-5
├→ form +1-2 (EWMA slightly positive)
├→ momentum +0.1-0.15
├→ trust_in_manager +3 (if manager is good)
└→ cascades: team spirit +5

Comeback Win (down 2+ goals @ min 70)
├→ form +8-12 (all squad)
├→ morale +15 (all squad) 
├→ momentum +0.40 (team)
├→ squad_spirit +12
└→ cascades: fan_favorite, narrative arc triggered
```

---

## ✅ Stat Modification Checklist

### By Match Events
- ✅ Goal: rating +1.5, form +3, morale +4
- ✅ Assist: rating +1.2, form +2, morale +3
- ✅ Clean sheet: rating +0.5, form stable (good), morale +2
- ✅ Yellow card: rating -0.5, morale -1
- ✅ Red card: rating -5, form -20, morale -8, suspended_matches += 3-5
- ✅ Mistake (conceded goal): rating -1, form -2, morale -2

### By Manager Actions
- ✅ Promotion to first team: happiness +15
- ✅ Demotion to bench: happiness -15, morale -8
- ✅ Captain assignment: leadership matters, morale +5
- ✅ Position change: tactical_familiarity -10, morale -2
- ✅ Broken promise: loyalty -30, morale -15, form -8

### By Consequences
- ✅ Teammate injured: friend morale -3, team spirit -8
- ✅ Big match upcoming: form +1-5 (if big_match 80+)
- ✅ Short turnaround: fitness -20, stamina -5, injury risk +0.10
- ✅ Derby match: fouls +20%, cards +0.2x
- ✅ Home advantage: form +2, composure +2
- ✅ Away penalty: form -3, positioning -1

---

## 📝 Common Scenarios & Stat Changes

### "Player Losing Form" (5-Match Slump)
```
Match 1: rating 6.5 → form 60
Match 2: rating 5.8 → form (0.4*5.8 + 0.6*60) = 38.3
Match 3: rating 5.2 → form (0.4*5.2 + 0.6*38.3) = 25.9
Morale dropping: -2 per match = 50 → 40 (warning)
After 5 matches: form <30, triggers "poor form" mode
Squad notices: form average -5 team stat
```

### "Injury Crisis" (3 injuries in 1 week)
```
Club spirit: -8 * 3 = -24 (squad depressed)
Fitness budget: 3 players @ 75% recovery = 25% workload increase
Form: Squad form average -12 (teammates covering)
Friend networks: 15 friends of injured get -2 morale each
Media: Injury crisis news story triggers
Result: Team form downward spiral 5-8 matchdays
```

### "Trust Broken" (Promise Not Fulfilled)
```
Promise: "You'll start 30+ matches" (made matchday 1)
Reality: Started 18 matches by matchday 30 (deadline)
Broken trigger:
├→ loyalty_to_manager -30 (was 70, now 40)
├→ trust_in_manager -15 (was 65, now 50)
├→ morale -15 (was 70, now 55)
├→ form -8 (now unhappy performer)
├→ happiness -20 (was 75, now 55)
└→ transfer_request: TRUE

Side effects:
- Friend networks: best friends get -3 morale  
- Board: reputation -5 (poor management)
- Next match: form penalty -5 compounded
Recovery: Would need 3-4 wins + new promise to recover
```

---

## 🎯 Target Stats by Position

### Striker (ST/CF)

| Attribute | Target | Priority |
|-----------|--------|----------|
| Shooting | 85+ | ⭐⭐⭐ |
| Finishing | 90+ | ⭐⭐⭐ |
| Sprint Speed | 80+ | ⭐⭐⭐ |
| Acceleration | 80+ | ⭐⭐⭐ |
| Strength | 75+ | ⭐⭐ |
| Heading Accuracy | 75+ | ⭐⭐ |
| Stamina | 75+ | ⭐⭐ |
| Dribbling | 75+ | ⭐ |

### Winger (RW/LW)

| Attribute | Target | Priority |
|-----------|--------|----------|
| Dribbling | 85+ | ⭐⭐⭐ |
| Crossing | 80+ | ⭐⭐⭐ |
| Pace | 85+ | ⭐⭐⭐ |
| Agility | 80+ | ⭐⭐ |
| Shot Power | 75+ | ⭐ |
| Shooting | 70+ | ⭐ |

### Center Back (CB)

| Attribute | Target | Priority |
|-----------|--------|----------|
| Defending | 85+ | ⭐⭐⭐ |
| Marking | 80+ | ⭐⭐⭐ |
| Heading Accuracy | 80+ | ⭐⭐⭐ |
| Strength | 80+ | ⭐⭐⭐ |
| Positioning | 80+ | ⭐⭐ |
| Jumping | 75+ | ⭐⭐ |

### Midfielder (CM)

| Attribute | Target | Priority |
|-----------|--------|----------|
| Passing | 85+ | ⭐⭐⭐ |
| Stamina | 85+ | ⭐⭐⭐ |
| Composure | 80+ | ⭐⭐ |
| Positioning | 80+ | ⭐ |
| Vision | 75+ | ⭐ |

### Goalkeeper (GK)

| Attribute | Target | Priority |
|-----------|--------|----------|
| GK Diving | 85+ | ⭐⭐⭐ |
| GK Positioning | 85+ | ⭐⭐⭐ |
| GK Reflexes | 85+ | ⭐⭐⭐ |
| GK Handling | 80+ | ⭐⭐ |
| Composure | 80+ | ⭐⭐ |
| GK Kicking | 75+ | ⭐ |

---

## 🔄 Stat Decay & Growth Cycles

### Age-Based Potential Growth
```
16-22: Youth phase
  - Potential growth: +1-2/season
  - Training accelerates: +1.5
  - Poor training halts: 0 growth
  
23-28: Peak phase
  - Potential growth: +0.2-0.5/season or stagnant
  - Current ability can exceed potential if
    manager is excellent (potential_ability +0.1/season)
  
29-32: Plateau
  - Potential + current ability stable
  
33+: Decline phase
  - Potential growth: -1-2/season
  - Physical decay: -1-2 attributes/season
  - Mental stable (experience bonus)
```

### Dynamic Stat Decay (Per 38-Match Season)
```
High-usage player (35+ matches):
- Fitness: Ends season 15-20 points lower
- fatigue accumulation + some fitness recovery each rest

Low-usage player (5-10 matches):
- Match sharpness: -30-40 points (atrophy)
- Takes 6-8 starts to recover

Injured long-term (out 6+ weeks):
- Form: -15-20 points for season after return
- Recovery: +2-3 form per start (slow rebuild)
```

---

## 🎬 Quick Tips for Stat Reading

1. **Form <40?** Player is struggling. Consider:
   - Injury recovery (return fitness to 80+)
   - Morale crisis (broken promise? benched too long?)
   - Position mismatch (tactical familiarity too low)

2. **Morale dropping?** Check:
   - Playing time (consecutive_benched counter)
   - Promises (is one broken?)
   - Injuries (friends affected)
   - Squad results (team form affects individuals)

3. **Wants Transfer:*** Triggered when happiness <35 OR loyalty <40 OR many games benched. Can reverse by:
   - Increasing minutes
   - Fulfilling a promise
   - New contract
   - Squad wins/morale rise

4. **Personality Matters:** Low professionalism + high dirtiness player will get carded frequently. Manage playing time or change instructions (closing_down=low).

5. **Chemistry Building:** team_chemistry grows from:
   - Training together (weeks)
   - Match wins together
   - Shared rest days
   - Friend relationships on squad

