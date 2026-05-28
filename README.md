# 🌍 Geo-Intel Map

**An open-source geopolitical intelligence tool for political science education**

Geo-Intel Map is a cascade analysis platform that connects real-world conflict events 
to international relations theory. Designed for political science students and researchers, 
it transforms raw geopolitical data into structured, theory-linked learning experiences.

## 🔑 Key Features

- **5-Sector Intelligence Dashboard** — Maritime, Energy, Technology, Military, Gray Zone
- **Cascade Analysis Engine** — Multi-stage causal chain tracking (event → indicator → event), 15 rules, depth 4
- **8-Stage Geopolitical Reasoning** — Automated reasoning from facts to alliance diffusion
- **232,533 ACLED conflict events** as historical baseline (41 countries, 12 months)
- **Trade Dependency Matrix** — WITS data (6,116 records, 16 countries, 3 commodities)
- **FRED Macro Indicators** — WTI, VIX, exchange rates (3,757 records)
- **Theory Library** — 29 IR theories linked to live events (Weaponized Interdependence, Alliance Dilemma, A2/AD, etc.)
- **Country Intelligence Panel** — Per-country geopolitical profile with macro indicators, trade dependency, sanctions, and theory connections

## 🎓 Educational Value

This tool bridges the gap between IR theory and real-world data:

| Theory | Scholar | Live Application |
|--------|---------|-----------------|
| Weaponized Interdependence | Farrell & Newman (2019) | Semiconductor supply chain → TSMC cascade |
| Resource Weaponization | Hirschman (1945) | Hormuz tension → Oil price cascade |
| Alliance Dilemma | Snyder | Japan/Korea entrapment scoring via WITS |
| Levels of Analysis | Waltz | CAMEO actor type auto-tagging |

## 🏗️ Architecture
Real-time Intelligence (GDELT/RSS)
→ Token-Zero Tagging (CAMEO mapper, no LLM)
→ 3-Stage Fact Verification (baseline / RSS cross / physical sensor)
→ Event Normalization (single Event model)
→ Cascade Engine (YAML rulebook, chainable)
→ 3-View Visualization (Map / Sandbox Lab / Reasoning Panel)
→ Theory Library (29 .md files, 7-axis metadata)

## 🛠️ Tech Stack

- **Backend**: FastAPI (Python 3.12), SQLite, APScheduler
- **Frontend**: Vanilla JS ES6, Leaflet, Cytoscape.js, vis-timeline
- **Data**: ACLED, GDELT, NASA FIRMS, AISStream, OpenSky, FRED, WITS/UN Comtrade
- **Analysis**: Cascade Engine (YAML rules), 8-stage reasoning pipeline

## 🚀 Getting Started

```bash
# 1. Activate virtual environment
source backend/.venv/bin/activate

# 2. Run backend
cd backend
uvicorn main:app --reload --port 8000

# 3. Open frontend
open frontend/index.html
```

## 📊 Data Sources

| Source | Type | Records |
|--------|------|---------|
| ACLED | Conflict events (baseline) | 232,533 |
| GDELT | Real-time conflict | Live |
| FRED | Macro indicators | 3,757 |
| WITS/UN Comtrade | Trade dependency | 6,116 |
| NASA FIRMS | Fire/hotspots | Live |
| AISStream | Naval AIS | Live |
| OpenSky | Military ADS-B | Live |

## 📖 Development Roadmap

- [x] Phase 0: Foundation
- [x] Phase 1: MVP (5 layers + first Cascade rule)
- [x] Phase 2: Core differentiation (realtime + rulebook + causal graph)
- [x] Phase 3: Learning tool completion (in progress, v3.18.0)
- [ ] Phase 4: Statistical validation + multi-agent automation

## 📄 License

MIT License
