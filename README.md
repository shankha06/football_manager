<div align="center">

```
 ████████╗███████╗███╗   ███╗    ██╗   ██╗██████╗
 ╚══██╔══╝██╔════╝████╗ ████║    ██║   ██║╚════██╗
    ██║   █████╗  ██╔████╔██║    ██║   ██║ █████╔╝
    ██║   ██╔══╝  ██║╚██╔╝██║    ╚██╗ ██╔╝ ╚═══██╗
    ██║   ██║     ██║ ╚═╝ ██║     ╚████╔╝ ██████╔╝
    ╚═╝   ╚═╝     ╚═╝     ╚═╝      ╚═══╝  ╚═════╝
       FOOTBALL  MANAGER  v3
```

### *Manage. Compete. Dominate.*

**A deep football management simulation with Markov chain match engine, ML models, and browser UI**

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18-61DAFB?style=for-the-badge&logo=react&logoColor=black)](https://react.dev)
[![scikit-learn](https://img.shields.io/badge/scikit--learn-ML-F7931E?style=for-the-badge&logo=scikitlearn&logoColor=white)](https://scikit-learn.org)
[![SQLite](https://img.shields.io/badge/SQLite-DB-003B57?style=for-the-badge&logo=sqlite&logoColor=white)](#)

<br>

<img src="https://img.shields.io/badge/Players-18,350-2196F3?style=flat-square" />
<img src="https://img.shields.io/badge/Clubs-365-4CAF50?style=flat-square" />
<img src="https://img.shields.io/badge/Leagues-18-FF9800?style=flat-square" />
<img src="https://img.shields.io/badge/Engine-V3%20Markov%20Chain-F44336?style=flat-square" />
<img src="https://img.shields.io/badge/ML%20Models-3-9C27B0?style=flat-square" />

---

> *Every decision ripples. Every match tells a story.*

</div>

<br>

> [!IMPORTANT]
> **V3 is a complete rewrite** from the terminal TUI. The game now runs as a **FastAPI backend + React frontend** in your browser, powered by a **Markov chain possession engine**, **ML-based xG model**, and a **consequence system** where every decision cascades.

---

## What's New in V3

| Feature | V2 (TUI) | V3 (Browser) |
|:--------|:----------|:-------------|
| **Match Engine** | Possession-chain with tick events | Markov chain (16 states, dynamic transition matrix) |
| **Shot Resolution** | Formula-based xG | ML logistic regression (12 features) |
| **Psychology** | Basic morale | Momentum spikes, snowball windows, crowd pressure, big-match anxiety |
| **Consequences** | None | 8 event types with cascading effects (promises, trust, team spirit) |
| **Injuries** | Simple weeks counter | 12 types, recovery curves, setback risk, reinjury windows |
| **Form** | Rolling average | EWMA with minute-adjusted weights |
| **UI** | Terminal (Textual TUI) | React + Tailwind (dark theme, charts, live WebSocket match) |
| **API** | None | FastAPI with 11 REST routers + WebSocket for live matches |
| **Valuations** | Static formula | Random forest ML model |
| **Tactical Scoring** | Basic matchup | Zone overloads, style counters, player suitability scoring |

---

## Quick Start

### Prerequisites

- **Python 3.10+**
- **[uv](https://docs.astral.sh/uv/)** package manager
- **Node.js 18+** (for frontend)

### Install & Run

```bash
# Clone
git clone https://github.com/your-username/football-manager.git
cd football-manager

# Install Python dependencies
uv sync

# Start the API server (backend)
uv run python -m fm --api
```

In a second terminal:

```bash
# Install frontend dependencies
cd frontend
npm install --legacy-peer-deps

# Start the React dev server
npm run dev
```

Open **http://localhost:5173** in your browser.

> [!NOTE]
> **First game creation** downloads EA FC 24 player data via KaggleHub and seeds 18 leagues, 365 clubs, 10K+ players, and generates fixtures. This takes ~30-60 seconds.

### Alternative: Terminal TUI (Legacy)

The original terminal interface still works:

```bash
uv run python -m fm
```

### Train ML Models (Optional)

Pre-train the xG, match predictor, and valuation models:

```bash
uv run python -m fm --train
```

Models are trained automatically on first use if not pre-trained.

---

## Architecture

```
football_manager/
├── fm/
│   ├── __main__.py              # Entry: --api, --train, or TUI
│   │
│   ├── engine/                  # ── Match simulation ──
│   │   ├── chain_states.py      #   16 Markov chain states
│   │   ├── transition_calculator.py  #   Dynamic probability matrix builder
│   │   ├── possession_chain.py  #   V3 Markov chain engine (~300 chains/match)
│   │   ├── psychology.py        #   Momentum, snowball, crowd pressure
│   │   ├── resolver_v3.py       #   ML xG-powered shot resolution
│   │   ├── match_engine.py      #   V2 possession-chain engine (legacy)
│   │   ├── simulator.py         #   V1 tick-based engine (legacy)
│   │   ├── ml/                  #   ML models
│   │   │   ├── xg_model.py      #     Logistic regression xG (12 features)
│   │   │   ├── match_predictor.py #   GradientBoosting match outcome
│   │   │   ├── valuation_model.py #   RandomForest player valuation
│   │   │   └── tactical_scorer.py #   Rules-based tactical effectiveness
│   │   └── ...
│   │
│   ├── core/                    # ── V3 infrastructure ──
│   │   ├── event_bus.py         #   Pub/sub for consequence propagation
│   │   ├── game_state.py        #   In-memory cache with dirty tracking
│   │   └── consequence_engine.py #  8 cascading consequence handlers
│   │
│   ├── world/                   # ── Game world systems ──
│   │   ├── season.py            #   Season progression & matchday orchestration
│   │   ├── injury_model.py      #   12 injury types with recovery curves
│   │   ├── form_tracker.py      #   EWMA form calculation
│   │   ├── consequence_registry.py # Event-to-chain mappings
│   │   ├── transfer_market.py, morale.py, finance.py, ...
│   │   └── ...
│   │
│   ├── api/                     # ── FastAPI backend ──
│   │   ├── app.py               #   Application factory + CORS
│   │   ├── dependencies.py      #   DI: session, game state, season manager
│   │   ├── routers/             #   11 REST endpoint routers
│   │   ├── schemas/             #   Pydantic v2 request/response models
│   │   └── websocket/           #   Live match WebSocket
│   │
│   ├── db/                      # ── Data layer ──
│   │   ├── models.py            #   31 SQLAlchemy ORM models
│   │   ├── repositories.py      #   Repository pattern with eager loading
│   │   └── ingestion.py         #   EA FC 24 data pipeline
│   │
│   └── ui/                      # ── Terminal TUI (legacy) ──
│       └── app.py
│
├── frontend/                    # ── React frontend ──
│   ├── src/
│   │   ├── pages/               #   10 page components
│   │   ├── components/          #   Shared components (Layout, etc.)
│   │   ├── store/               #   Zustand state management
│   │   ├── api/                 #   Typed Axios API client
│   │   ├── hooks/               #   WebSocket hook for live match
│   │   └── types/               #   TypeScript types
│   └── ...
│
├── tests/                       # Test suites
│   ├── test_engine_v3.py        #   Markov chain + psychology tests
│   ├── test_ml_models.py        #   xG, match predictor, valuation tests
│   ├── test_consequences.py     #   Consequence system tests
│   └── test_api/                #   API endpoint tests
│
└── data/models/                 # Trained ML model files (.joblib)
```

---

## Key Systems

### Markov Chain Match Engine (V3)

Each match simulates ~300-350 possession chains distributed across 90 minutes. Each chain walks through 16 states (GOAL_KICK, BUILDUP_DEEP, PROGRESSION, CHANCE_CREATION, SHOT, GOAL, etc.) with probabilities dynamically adjusted by:

- **Team attributes** (defensive, midfield, attacking averages)
- **Tactics** (pressing, mentality, tempo, width, passing style)
- **Tactical interactions** (high press vs short passing, counter vs high line)
- **Zone control** (3v2 midfield overloads boost progression)
- **Match context** (momentum, fatigue, morale)

Matrix is recomputed every 15 game-minutes.

### ML Models

| Model | Type | Features | Purpose |
|:------|:-----|:---------|:--------|
| **xG** | Logistic Regression | 12 (distance, angle, body part, defender proximity, ...) | Shot → goal probability |
| **Match Predictor** | Gradient Boosting (50 trees) | 8 (team strength, form, home advantage, tactics) | P(home win/draw/away win) |
| **Valuation** | Random Forest (100 trees) | 9 (age, overall, potential, position, minutes, ...) | Player market value |

### Consequence System

Every decision cascades:

| Trigger | Effect |
|:--------|:-------|
| Player dropped 3+ times | Happiness -10, trust -5, friends morale drop |
| Fan favorite sold | Fan happiness -10, friend morale -5 to -15 |
| Promise broken | Happiness -25, trust -20, may request transfer |
| Captain injured | Team spirit -8, squad morale -3 |
| Financial overspend (3+ MD) | Transfer embargo; 6+ MD: board ultimatum |
| Overtraining | Injury proneness +20 for 4 weeks |

---

## Testing

```bash
# Run all V3 tests
uv run python -m pytest tests/test_engine_v3.py tests/test_ml_models.py tests/test_consequences.py tests/test_api/ -v

# Run everything (including legacy tests)
uv run python -m pytest tests/ -v
```

---

## Tech Stack

| Layer | Technology |
|:------|:-----------|
| **Backend** | Python 3.10+, FastAPI, SQLAlchemy 2.0, SQLite |
| **Frontend** | React 18, TypeScript, Tailwind CSS, Zustand, Recharts |
| **ML** | scikit-learn, joblib |
| **Match Engine** | Markov chains, NumPy, optional CUDA (CuPy) |
| **Data** | EA FC 24 via KaggleHub (18,350 players) |
| **Real-time** | WebSocket for live match commentary |

---

<div align="center">

**Built with obsessive attention to the beautiful game**

<sub>90+ files | 45K+ lines | 31 models | 3 ML models | 18 leagues | 365 clubs | 10K+ players</sub>

*Strategize. Build. Conquer.*

</div>
