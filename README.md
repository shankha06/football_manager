<div align="center">

<br>

#  ⚽ Football Manager

### *Manage. Compete. Dominate.*

<sub>A deep football management simulation with Markov chain match engine,<br>
ML-powered models, advanced psychology system, and a modern reactive browser UI.</sub>

<br>

<!-- Tech Badges -->
[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-61DAFB?style=for-the-badge&logo=react&logoColor=black)](https://react.dev)
[![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?style=for-the-badge&logo=typescript&logoColor=white)](https://www.typescriptlang.org)
[![Scikit-learn](https://img.shields.io/badge/scikit--learn-F7931E?style=for-the-badge&logo=scikitlearn&logoColor=white)](https://scikit-learn.org)
[![SQLite](https://img.shields.io/badge/SQLite-003B57?style=for-the-badge&logo=sqlite&logoColor=white)](https://sqlite.org)
[![NumPy](https://img.shields.io/badge/NumPy-013243?style=for-the-badge&logo=numpy&logoColor=white)](https://numpy.org)

<br>

<!-- Feature Badges -->
[![Markov Chains](https://img.shields.io/badge/Markov_Chains-FF6B6B?style=flat-square&labelColor=gray&color=FF6B6B)](###)
[![18K+ Players](https://img.shields.io/badge/18K%2B_Players-1E90FF?style=flat-square&labelColor=gray)](###)
[![365 Clubs](https://img.shields.io/badge/365_Clubs-32CD32?style=flat-square&labelColor=gray)](###)
[![18 Leagues](https://img.shields.io/badge/18_Leagues-FFD700?style=flat-square&labelColor=gray)](###)
[![3 ML Models](https://img.shields.io/badge/3_ML_Models-FF1493?style=flat-square&labelColor=gray)](###)
[![WebSocket Live](https://img.shields.io/badge/WebSocket_Live-00CED1?style=flat-square&labelColor=gray)](###)

<br>

<!-- License & Stats -->
[![License: MIT](https://img.shields.io/badge/License-MIT-brightgreen?style=flat-square)](LICENSE)
[![Code Style: Black](https://img.shields.io/badge/code%20style-black-000000?style=flat-square)](https://github.com/psf/black)
[![Maintained](https://img.shields.io/badge/Maintained%3F-yes-brightgreen?style=flat-square)](###)

<br>

---

</div>

<br>

> **⚡ V3 is a complete architectural rewrite.** Browser-based with FastAPI + React, powered by a 16-state Markov chain possession engine, ML xG model, and fully integrated **Match Situation Engine** for cascading consequences.

<br><br>

## 🌟 Core Features

<table>
<tr>
<td width="50%">

### ⚙️ Markov Chain Engine
- 16-state possession chains
- ~300 chains per match
- Dynamic transition matrix (15m recalc)
- Tactics-based probability updates
- Zone control integration
- Momentum & fatigue factors

</td>
<td width="50%">

### 🤖 ML Intelligence
- **xG Model**: Logistic regression (12 features)
- **Match Predictor**: Gradient boosting (50 trees)
- **Valuations**: Random forest (100 trees)
- EA FC 24 training data
- Real-time probability updates

</td>
</tr>
<tr>
<td width="50%">

### 💥 Consequence System
- 8 cascading event types
- Friend morale networks
- Transfer request triggers
- Board ultimatum logic
- Financial embargo system
- Ripple effect propagation

</td>
<td width="50%">

### 🧠 Psychology Engine
- Momentum spikes & decay
- Snowball window detection
- Crowd pressure modeling
- Big-match anxiety tracking
- Form via EWMA (minute-weighted)
- Player personality types

</td>
</tr>
</table>

<br>

## 🚀 What Changed in V3

| 📊 Category | V2 (Terminal) | V3 (Browser) |
|:--|:--|:--|
| 🎮 Engine | Tick-based possession | Markov chains (16-state) |
| 🎯 Shots | Formula xG | ML logistic regression |
| 😊 Psychology | Basic morale | Momentum, snowball, anxiety |
| 🔗 Consequences | None | 8 cascade types + 40+ match situations |
| 🤕 Injuries | Weeks counter | 12 types + recovery curves |
| 📊 Form | Rolling average | EWMA (dynamic weighted) |
| 🖥️ Interface | Text TUI | React + Tailwind + WS |
| 📡 Backend | FSM logic | FastAPI + RestAPI + WS |
| 💰 Valuations | Static formula | Random forest ML |
| 🎯 Tactics | Basic matchup | Zone overloads + counters |

<br>

## 🎯 Quick Start

### 📋 Prerequisites

| Tool | Version | Purpose |
|:--|:--|:--|
| 🐍 **Python** | 3.10+ | Backend runtime |
| 📦 **uv** | Latest | Package manager |
| 🟩 **Node.js** | 18+ | Frontend tooling |
| 🎨 **Git** | Latest | Version control |

### ⚡ Installation & Setup

```bash
# Clone repository
git clone https://github.com/your-username/football-manager.git
cd football-manager

# Install dependencies
uv sync
```

### 🏃 Run the Application

```bash
# Terminal 1 — Start API server (port 8000)
uv run python -m fm --api

# Terminal 2 — Start React dev server (port 5173)
cd frontend
npm install --legacy-peer-deps
npm run dev
```

**Open Browser → http://localhost:5173**

> [!NOTE]
> 🔄 **First Run**: Automatically downloads EA FC 24 dataset via KaggleHub and seeds all leagues, clubs, players. ⏱️ ~30-60 seconds.

### 💻 Alternative: Terminal Mode

```bash
uv run python -m fm
```

### 🧠 Train ML Models (Optional)

```bash
# Train all models (xG, match predictor, valuation)
uv run python -m fm --train
```

> Models auto-train on first use if not pre-trained.

<br>

## 🏗️ System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    ⚽ Football Manager                       │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  🖥️ React SPA Frontend (Port 5173)                   │  │
│  │  ├─ Match Live Dashboard                            │  │
│  │  ├─ Club Management UI                              │  │
│  │  ├─ Transfer Market                                 │  │
│  │  ├─ Player Development                              │  │
│  │  └─ Performance Analytics                           │  │
│  └──────────────────────────────────────────────────────┘  │
│           │ WebSocket (Real-time Events) │                 │
│           ▼                               ▼                 │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  📡 FastAPI Backend (Port 8000)                      │  │
│  │  ├─ 11 REST API Routers                             │  │
│  │  ├─ WebSocket Live Match Feed                       │  │
│  │  └─ Event Bus (Pub/Sub)                             │  │
│  └──────────────────────────────────────────────────────┘  │
│           │                    │                            │
│           ▼                    ▼                            │
│  ┌──────────────────────┐  ┌──────────────────────┐        │
│  │ 🎮 Game Engine       │  │ 💾 Data Layer        │        │
│  │ ├─ Markov Chain      │  │ ├─ SQLAlchemy ORM    │        │
│  │ ├─ Match Simulator   │  │ ├─ 31 Models         │        │
│  │ ├─ Psychology System │  │ ├─ Repositories      │        │
│  │ └─ xG Resolution     │  │ └─ SQLite DB         │        │
│  ├─ 🤖 ML Models       │  └──────────────────────┘        │
│  │ ├─ xG Predictor      │                                  │
│  │ ├─ Match Prediction  │  🌍 World Systems                │
│  │ └─ Valuations        │  ├─ Transfer Market              │
│  └──────────────────────┘  ├─ Injury Tracking              │
│                             ├─ Form/Morale                 │
│                             ├─ Season Progression           │
│                             └─ Finance Management           │
└─────────────────────────────────────────────────────────────┘
```

<br>

## 📁 Project Structure

```
fm/
├── 🎮 engine/                    # Match simulation core
│   ├── chain_states.py           #   16 Markov states
│   ├── transition_calculator.py  #   Dynamic matrix
│   ├── possession_chain.py       #   Engine v3 (~300/match)
│   ├── psychology.py             #   Momentum & crowding
│   ├── resolver_v3.py            #   ML xG resolution
│   ├── 🤖 ml/
│   │   ├── xg_model.py
│   │   ├── match_predictor.py
│   │   └── valuation_model.py
│   └── ...
│
├── ⚡ core/                       # V3 infrastructure & consequences
│   ├── event_bus.py              #   Pub/sub system (40+ events)
│   ├── game_state.py             #   State management
│   ├── consequence_engine.py     #   Base consequence orchestrator
│   ├── cascading_consequences.py #   6-system cascade engine
│   └── match_situations.py       #   ✨ NEW: 40+ real-life match scenarios
│
├── 🌍 world/                      # Game world
│   ├── season.py, cup.py         #   Calendar & progression
│   ├── injury_model.py           #   12 injury types
│   ├── form_tracker.py           #   EWMA tracking
│   ├── transfer_market.py        #   Transfers & bids
│   ├── morale.py, finance.py     #   Economy & psychology
│   └── ...
│
├── 📡 api/                        # FastAPI backend
│   ├── app.py                    #   App factory
│   ├── routers/                  #   11 REST routers
│   ├── schemas/                  #   Pydantic models
│   └── websocket/                #   WS handlers
│
├── 💾 db/                         # Data persistence
│   ├── models.py                 #   31 ORM models
│   ├── repositories.py           #   Repository pattern
│   └── ingestion.py              #   EA FC 24 pipeline
│
└── 🖥️ ui/                         # Terminal TUI (legacy)

frontend/                          # ⚛️ React + TypeScript
├── src/pages/                    #   10 page components
├── src/components/               #   Shared UI components
├── src/store/                    #   Zustand state
├── src/api/                      #   Axios client
├── src/hooks/                    #   Custom hooks
└── src/types/                    #   TS interfaces

tests/                             # 🧪 Comprehensive test suite
├── test_engine_v3.py
├── test_ml_models.py
├── test_consequences.py
└── test_api/
```

<br>

<details open>
<summary>
<strong>🤖 ML Models Breakdown</strong>
</summary>

<br>

| Model | Algorithm | Input Features | Output | Accuracy |
|:--|:--|:--|:--|:--|
| **⚽ xG Predictor** | Logistic Regression | 12 (shot distance, angle, body part, defenders nearby, pressure, ...) | P(goal) | ~87% |
| **💪 Match Predictor** | Gradient Boosting (50 trees) | 8 (team strength, form, home advantage, tactics, ...) | P(H/D/A) | ~73% |
| **💰 Player Valuation** | Random Forest (100 trees) | 9 (age, rating, potential, position, minutes, wage, ...) | Market Value | 82% MAE |

**Data Source**: EA FC 24 (KaggleHub) • **Training**: scikit-learn • **Serialization**: joblib

</details>

<details>
<summary>
<strong>💥 Consequence System (8 Cascade Types)</strong>
</summary>

<br>

| # | Trigger Event | Immediate Effect | Cascade | Propagation |
|:--|:--|:--|:--|:--|
| 1️⃣ | Player dropped 3+ times | Happiness -10 | Friends morale -5 to -10 | Spreads to squad cliques |
| 2️⃣ | Fan favorite sold | Fan happiness -10 | Friend morale -5 to -15 | Squad-wide impact |
| 3️⃣ | Promise broken | Happiness -25, trust -20 | May request transfer | Affects recruitment |
| 4️⃣ | Captain injured | Team spirit -8 | Squad morale -3 | Defense coordination -5% |
| 5️⃣ | 3+ MD overspend | Warning issued | Transfer embargo (6 MD) | Recruitment lockdown |
| 6️⃣ | 6+ MD overspend | Board ultimatum | Forced sales / salary cuts | Financial restructuring |
| 7️⃣ | Overtraining (4+ weeks) | Injury proneness +20 | Injury risk x2.0 | "Burnout" phase |
| 8️⃣ | Win streak (3+) | Confidence +15 | Momentum multiplier x1.3 | Snowball window |

</details>

<details>
<summary>
<strong>🏥 Injury System (12 Types)</strong>
</summary>

<br>

| Injury Type | Duration (Base) | Setback Risk | Recovery Curve | Training Impact |
|:--|:--|:--|:--|:--|
| 🦵 Muscle Strain | 2-4 weeks | 15% | Linear | -40% intensity |
| 🦴 Fracture | 4-8 weeks | 10% | S-curve | -60% intensity |
| 🧠 Concussion | 1-2 weeks | 20% | Steep | Complete rest |
| 🦗 Hamstring | 3-6 weeks | 25% | S-curve | -50% intensity |
| 🤕 Bruise | 1-3 days | 5% | Immediate | -20% intensity |
| 🫀 Heart Issue | 6-12 weeks | 40% | Long recovery | Doctor clearance |
| 😣 Fatigue | 3-7 days | 0% | Quick | Rest required |
| 🧬 ACL Tear | 8-12 months | 60% | Very long | Rehabilitation phase |
| 🦴 Dislocation | 2-4 weeks | 30% | S-curve | -45% intensity |
| 🤐 Jaw | 2-3 weeks | 10% | Linear | Protective gear |
| 👁️ Eye | 1-7 days | 5% | Quick | -10% sharpness |
| 😞 Psychological | 1-4 weeks | 35% | Variable | -30% form decay |

</details>

<details>
<summary>
<strong>⚽ 40+ Real-Life Match Situations (Short & Long-Term Impacts)</strong>
</summary>

<br>

> **NEW SYSTEM**: `MatchSituationEngine` models 40+ authentic football scenarios with cascading consequences affecting psychology, form, morale, and transfer dynamics.

### 🔴 Disciplinary Drama (2-4 MD effects)

| Situation | Short-Term Impact | Medium-Term (1-3 MD) | Long-Term (4+ MD) |
|:--|:--|:--|:--|
| **Red Card (Violent)** | Momentum -0.25, Formation -15% xG | Friends lose 5-15 morale, Captain loses trust | Reputation -10, Discipline -15, Transfer request |
| **Red Card (Reckless)** | Momentum -0.20, Player missing 1-2 matches | Squad unrest, Manager trust -5 | Stigma, worse form momentum |
| **Early Red (Before min 20)** | Formation destroyed -35%, xG -40% | Defensive unit form -15, Team spirit -12 | Player benched, expectations +25 |
| **Disputed Penalty** | Crowd fury, Referee controversy | Squad focus scattered | Media pressure spiral |
| **VAR Controversy** | Momentum swing (large), Crowd impact | Media criticism, Manager frustration | Board confidence review |

### ⚽ On-Pitch Performance Drama (1-2 MD recovery)

| Situation | Short-Term Impact | Medium-Term | Long-Term |
|:--|:--|:--|:--|
| **Goalkeeper Error** | Momentum -0.20, xG deficit 15% | Form crater -12, Morale -10 | Possible benching, Discipline -5 |
| **Missed Penalty** | Momentum -0.30, Confidence crash -25 | Form -15, Squad morale -3 | Loses penalty-taking duties |
| **Own Goal** | Massive momentum shift to opposition | Player form -10, Reputation hit | Transfer requests possible |
| **Defensive Collapse (3+ goals in 15min)** | Formation destroyed, Panic factor -25 | Defensive unit form -10, Spirit -10 | Tactical changes, Lineup review |
| **Set Piece Failure** | Opposition xG advantage, Momentum | Formation confidence -8 | Tactical adjustment |
| **Set Piece Success** | Own xG boost, Momentum surge | Tactical reputation +5 | Team belief surge |

### 🔥 Momentum & Psychological (3-5 MD ripple effects)

| Situation | Short-Term Impact | Medium-Term | Long-Term |
|:--|:--|:--|:--|
| **Late Goal (87-90min)** | Momentum +0.35 (comeback), Crowd +15 | Player confidence +12, Form +6 | Squad morale +2-5 each |
| **Comeback Victory (2+ goal deficit)** | Momentum +0.40, Belief x2.0 | All squad morale +15, Form +8 | Narrative arc begins: "Resilient" |
| **Upset Victory** | Momentum surge, Underdog boost | Squad morale +12, Form +10 | Tactical reputation +8 for manager |
| **Clean Sheet (normal)** | Defensive confidence +12 | Defense form +8, Spirit +3 | GK form +6 |
| **Clean Sheet (after injury crisis)** | Extra resilience factor | Defense form +8 (+5 bonus), Spirit +5 | Squad belief surge |
| **Easy Win (3+ goal margin)** | Squad euphoria, Momentum spike | All players morale +8, Form +6 | Board confidence +8 |
| **Narrow Loss (1-goal defeat)** | Frustration, Momentum -15 | Squad form -3, Morale -5 | Replay of match in media |

### 👥 Player Performance Arcs (Multi-match narratives)

| Situation | Short-Term | Medium-Term (1-3 MD) | Long-Term (4+ MD) |
|:--|:--|:--|:--|
| **Young Player Debut** | Confidence +8, Development +5 | Form +3-15ⁱ, Morale+4-12ⁱ | ⁱIf breakout: potential +3, playtime expectations +20 |
| **Scoring Run (3+ in 3 MD)** | Hot streak multiplier x2.0, Confidence surge | Form +15, Morale +12, Market value x1.2 | Transfer interest +40, Agent interest |
| **Goal Drought (5+ MD)** | Shooting confidence -20 | Form -12, Finishing -8, Substitution more often | 8+ MD: Transfer request triggered |
| **Veteran Performance (age 33+)** | Leadership surge +15, Experience factor | Squad morale +6 (juniors especially) | Leadership/captain boost +5 |
| **First Match Back (post-injury)** | Limited confidence, Form caution | Gradual restoration if no setback | Return to form trajectory |
| **Recurring Injury (same player, same type)** | Recovery extended x1.3 (capped 12 weeks) | Morale -15, Confidence -10 | Injury proneness +10, Chronic illness flag |

### 🏆 Competition & Contextual (2-4 MD effects, some longer)

| Situation | Short-Term Impact | Medium-Term | Long-Term |
|:--|:--|:--|:--|
| **Derby/Rivalry Match Win** | Morale +8, Form +6, Spirit +5 | Squad celebration, Bragging rights | Historical record in head-to-head |
| **Derby/Rivalry Match Loss** | Morale -8-10, Form -5-6, Spirit -5 | Squad depression, Media criticism | Revenge motivation for next derby |
| **Unbeaten Run Broken** | Shock, Momentum collapse -0.25 | Form dip -8, Confidence -12 | Narrative: "But how?" |
| **Historic Record Broken (beat/broken)** | Euphoria or devastation | Legendary status if beaten OR regret | Long-term narrative impact |
| **Title Race Blow (loss to rival)** | Grand implications (xG now worse) | Squad paranoia, Form struggle | Transfer market implications |
| **Cup Elimination (by rival)** | Playoff exit frustration | Form dips, Transfer requests | Champions League impact (EU leagues) |
| **European Competition Exit** | Squad disappointment | Form -5-10, Morale -8 | Contract frustration, Top players leave |

### 🏥 Health & Fitness Cascades (1-2 weeks immediate, 4+ MD long-term)

| Situation | Short-Term Impact | Medium-Term | Long-Term |
|:--|:--|:--|:--|
| **Short Turnaround (2-3 days between matches)** | Stamina -20%, Fatigue -15 | Injury risk +8 for all | Recovery time needed |
| **Multiple Injuries (3+ starters out)** | Formation collapse, xG -25 | Defense/midfield reorganization, Form struggle | Cascading panic (morale -5 all) |
| **Illness Outbreak (2+ players)** | Squad availability crisis, Contagion risk | Additional players at risk | Morale impact (virus panic) |
| **Weather Extreme (heavy rain/snow/heat)** | Technical play -15%, Ball control -10 | Fatigue +10%, Injury risk +5 | Recovery needed next 2 days |
| **Travel Fatigue (long distance away match)** | Fitness -15%, Coordination -10 | Recovery day needed | Form dip -2-3 if immediate turnaround |

### 🎯 Tactical & Management (Immediate 1-match, some 3+ MD)

| Situation | Short-Term Impact | Medium-Term | Long-Term |
|:--|:--|:--|:--|
| **Tactical Masterclass (unexpected formation works)** | xG +20%, Formation advantage | Team belief +10, Morale +8 | Tactical reputation +8 for manager |
| **Manager Outplayed (underperformance)** | Formation struggles, xG -15 | Board confidence -5, Squad doubt grows | Sacking probability review |
| **Substitution Drama (star player hooked)** | Emotional moment, Squad shock | Substituted player morale -8-12, Captain -5 | Transfer request risk if repeated |
| **Formation Change (mid-match tactical shift)** | xG adjustment (positive or brutal) | Squad adaptability +/- 5 | Tactical flexibility narrative |
| **Player Fight (dressing room altercation)** | Immediate red card or suspension | Squad hierarchy shift, Friend groups affected | Long-term rift, Transfer requests |

### 📊 **Cascading Narrative Examples**

#### 🔴 **The Red Card Spiral**
```
Match 1: Player sent off (violent)
├─ Short-term: Momentum -0.25, Team loses xG advantage
├─ MD 1-3: Friends lose 5-15 morale, Team talks ineffective
├─ MD 4-8: Reputation hits transfer market, Discipline -15
└─ MD 9+: Transfer request if discipline < 40, Exit rumored
```

#### 🟢 **The Comeback Hero Arc**
```
Match 1: Score late goal in 90th min (comeback win)
├─ Short-term: Momentum +0.35, Crowd euphoria
├─ MD 1-3: Player form +6, Entire squad +2-5 morale each
├─ MD 4-8: Confidence surge continues, "Resilient" narrative
└─ MD 9+: Transfer offers spike, Agent interest rises
```

#### 🟡 **The Drought Crisis**
```
Match 1-5: Scorer without goals → Drought begins
├─ MD 1-3: Confidence crash -20, Form -15, Special treatment
├─ MD 4-6: Substitutions increase, Penalty duties lost
├─ MD 7-8: Media criticism mounts, Squad doubts
└─ MD 9+: Transfer request, Exit window speculation
```

#### ⚪ **The Injury Cascade**
```
Match 1: Star defender injured (recurring ACL)
├─ Short-term: Defensive unit scrambles, xG -20
├─ MD 1-3: Backup defender form -8, Squad morale -10
├─ MD 4-8: Extended recovery (x1.3 multiplier = longer)
├─ MD 9+: Chronic injury flag set, Transfer implications
└─ Long-term: Player confidence stays low even on return
```

</details>

<br>

## 📚 Tech Stack

<table>
<tr>
<td width="50%">

### 🔧 Backend
[![Python Badge](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://python.org)
[![FastAPI Badge](https://img.shields.io/badge/FastAPI-005571?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![SQLAlchemy Badge](https://img.shields.io/badge/SQLAlchemy-2.0-d42e2d?logo=python)](https://www.sqlalchemy.org)
[![SQLite Badge](https://img.shields.io/badge/SQLite-003B57?logo=sqlite&logoColor=white)](https://sqlite.org)
[![Pydantic Badge](https://img.shields.io/badge/Pydantic-v2-1f180f?logo=python)](https://docs.pydantic.dev)

</td>
<td width="50%">

### ⚛️ Frontend
[![React Badge](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)](https://react.dev)
[![TypeScript Badge](https://img.shields.io/badge/TypeScript-5-3178C6?logo=typescript&logoColor=white)](https://www.typescriptlang.org)
[![Tailwind Badge](https://img.shields.io/badge/Tailwind_CSS-3-38b2ac?logo=tailwind-css&logoColor=white)](https://tailwindcss.com)
[![Zustand Badge](https://img.shields.io/badge/Zustand-4-623cc1?logo=javascript)](https://github.com/pmndrs/zustand)
[![Recharts Badge](https://img.shields.io/badge/Recharts-2-8884d8?logo=javascript)](https://recharts.org)

</td>
</tr>
<tr>
<td width="50%">

### 🤖 ML & Engine
[![scikit-learn Badge](https://img.shields.io/badge/scikit--learn-1.3-F7931E?logo=scikitlearn&logoColor=white)](https://scikit-learn.org)
[![NumPy Badge](https://img.shields.io/badge/NumPy-1.24-013243?logo=numpy&logoColor=white)](https://numpy.org)
[![Joblib Badge](https://img.shields.io/badge/Joblib-1.3-c34c70?logo=python)](https://joblib.readthedocs.io)
[![CuPy Badge](https://img.shields.io/badge/CuPy-Optional_CUDA-76B900?logo=nvidia)](https://docs.cupy.dev)

</td>
<td width="50%">

### 📊 Data & Real-time
[![EA FC 24 Badge](https://img.shields.io/badge/EA_FC_24-18K%2B_Players-FF0000?logo=data:image/svg%2bxml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCI+PHRleHQgeD0iNiIgeT0iMTgiIGZpbGw9IndoaXRlIiBmb250LXNpemU9IjE2Ij7wn4+7PC90ZXh0Pjwvc3ZnPg==)](http://kagglehub.com)
[![WebSocket Badge](https://img.shields.io/badge/WebSocket-Live_Events-00CED1?logo=python)](https://developer.mozilla.org/en-US/docs/Web/API/WebSocket)

</td>
</tr>
</table>

<br>

## 🧪 Testing & Quality Assurance

```bash
# Run all tests with coverage
uv run pytest --cov=fm --cov-report=html --cov-report=term-missing

# Run tests in parallel (pytest-xdist)
uv run pytest -n auto

# V3-specific test suite
uv run pytest tests/test_engine_v3.py \
  tests/test_ml_models.py \
  tests/test_consequences.py \
  tests/test_v3_match_situations_integration.py \
  tests/test_api/ -v --tb=short

# Watch mode (automatic rerun on changes)
uv run pytest-watch tests/ -- -v

# Performance profiling
uv run pytest tests/test_engine_v3.py --profile
```

**Coverage**: ~85% | **Test Files**: 15+ | **Test Cases**: 200+ | **Execution**: ~15 seconds

<br>

## 📈 Performance Metrics

| Metric | Value | Baseline |
|:--|:--|:--|
| ⚡ Match Simulation | ~200ms | Per 90 minutes |
| 🎯 Shot Resolution | ~2ms | Per shot (n=~20/match) |
| 🧠 Psychology Update | ~15ms | Per cycle |
| 💾 Game State Serialize | ~5ms | Per frame |
| 📡 WebSocket Latency | <50ms | Live feed |
| 🤖 ML Prediction | ~1ms | Per shot |

<br>

---

<div align="center">

<br>

## 🎓 Key Innovations

<table>
<tr>
<td align="center" width="33%">

### 🎲 Markov Chain Engine
Realistic possession-based match simulation with dynamic transition matrices recalculated in real-time based on game state, tactics, and momentum.

</td>
<td align="center" width="33%">

### 🧬 Consequence Propagation
Every managerial decision cascades through the squad. Friend networks, morale connections, and financial constraints create emergent gameplay systems.

</td>
<td align="center" width="33%">

### 📊 ML-Powered Realism
Real EA FC 24 data trained via scikit-learn. xG model, match predictor, and valuations all grounded in actual football statistics.

</td>
</tr>
</table>

<br>

## 🔗 External Resources

[![Markov Chains](https://img.shields.io/badge/Learn-Markov_Chains-ff9999?style=flat)](https://en.wikipedia.org/wiki/Markov_chain)
[![Expected Goals](https://img.shields.io/badge/Learn-Expected_Goals-99ccff?style=flat)](https://www.statsinsider.com/tutorial/xg-expected-goals)
[![scikit-learn](https://img.shields.io/badge/Library-scikit--learn-F7931E?style=flat&logo=scikitlearn)](https://scikit-learn.org)
[![FastAPI](https://img.shields.io/badge/Framework-FastAPI-005571?style=flat&logo=fastapi)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/Framework-React_18-61DAFB?style=flat&logo=react)](https://react.dev)

<br>

## 📊 Project Statistics

```
📁 Project Size:
  • 90+ Python files
  • 45K+ lines of code
  • 31 SQLAlchemy ORM models
  • 3 production ML models
  • 11 REST API routers
  • 10+ React pages
  • 200+ test cases

🌍 Data Coverage:
  • 18 Leagues
  • 365 Clubs
  • 18,350 Players
  • 365+ Matchdays per season

⚙️ Computing:
  • ~300 possession chains/match
  • 16 Markov states
  • 12+ injury types
  • 8 consequence cascades
```

<br>

## 📝 License & Attribution

[![MIT License](https://img.shields.io/badge/License-MIT-brightgreen?style=for-the-badge)](LICENSE)

This project is released under the MIT License. See [LICENSE](LICENSE) for details.

**Data Attribution**: EA FC 24 dataset via [KaggleHub](https://kagglehub.com)

<br>

## 🤝 Contributing

Contributions are welcome! Areas of interest:
- 🎮 Additional match engine features
- 🤖 Improved ML models & accuracy
- 🖥️ UI/UX enhancements
- 📊 Analytics dashboard expansion
- 🧪 Additional test coverage

<br>

---

<sub>⚽ **Built with obsessive attention to the beautiful game.**</sub>

<sub>A passion project for football simulation enthusiasts. Questions? Open an issue or reach out! ⚡</sub>

<br>

[![Back to Top](https://img.shields.io/badge/-Back_to_Top-000?style=flat)](###-football-manager)

</div>
