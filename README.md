# Geo-Intel Map

**A geopolitical cascade intelligence platform for political science education**

Geo-Intel Map connects real-world conflict events to international relations theory through
multi-stage causal chain analysis. Designed for political science students and researchers,
it transforms raw geopolitical data into structured, theory-linked insights at doctoral-entry level (81% avg, 2026-06 evaluation).

## Key Features

- **6-Sector Intelligence Dashboard** — Maritime, Energy, Technology, Indo-Pacific, Gray Zone, Cyber
- **Cascade Analysis Engine** — 22 YAML rules, multi-stage causal chains (depth 4), 76+ verified links
- **8-Stage Geopolitical Reasoning** — Facts → Alliance Diffusion scoring → Escalation risk
- **Insight Analyst** — Natural language query → 10-source parallel retrieval → Gemini 2.5 Flash SSE
- **IA-Engine-C** — §19-D confidence scoring (0–100) with [PROVISIONAL] / [TEMPORAL_REVERSAL] auto-detection
- **252,409 ACLED conflict events** as historical baseline (41 countries, 12 months)
- **10 Parallel Data Sources** — SIPRI, EIA, COW, Kiel Tracker, CSIS Cyber, ACLED, cascade links, country profiles, briefings, alliance graph
- **Briefing Library** — 57 documents (38 briefings from CSIS / INSS / RAND / ECFR / War on the Rocks / Foreign Affairs)
- **Theory Library** — 19 IR theories with 7-axis metadata (Waltz levels, DIME, Snyder posture)
- **Country Intelligence Panel** — Per-country geopolitical profile: macro indicators, trade dependency, sanctions, theory connections

## Educational Value

| Theory | Scholar | Application |
|--------|---------|-------------|
| Weaponized Interdependence | Farrell & Newman (2019) | Semiconductor supply chain → TSMC cascade |
| Resource Weaponization | Hirschman (1945) | Hormuz tension → Oil price cascade |
| Alliance Dilemma | Snyder | Diffusion_Score ≥ 80 = Entrapment risk |
| Hybrid Warfare | Hoffman | Gray zone escalation auto-detection |
| Offshore Balancing | Mearsheimer | US strategic priority reallocation detection |

## Insight Engine Quality (2026-06-04 Evaluation)

| Dimension | Pre-update | Post-update | Change |
|-----------|-----------|-------------|--------|
| Theoretical accuracy | 73% | 87% | +14%p |
| Causal rigor | 40% | 65% | +25%p |
| Data grounding | 25% | **87%** | **+62%p** |
| Hypothesis clarity | 45% | 75% | +30%p |
| Academic contribution | 62% | 80% | +18%p |
| **Overall** | **53%** | **81%** | **+28%p** |

Target: 90%+ (doctoral level) via IA-Engine-D (Granger auto-verification pipeline)

## Architecture

```
Real-time Intel (GDELT/RSS/ReliefWeb)
  → Token-Zero Tagging (CAMEO mapper, no LLM)
  → 3-Stage Fact Verification (ACLED / RSS cross / FIRMS sensor)
  → Event Normalization (7-axis metadata)
  → Cascade Engine (22 YAML rules, chainable depth 4)
  → 8-Stage Reasoning (actor profile → alliance diffusion → escalation)

Insight Analyst Query
  → Entity Parser (deterministic, Token-Zero)
  → 10-Source Parallel Retrieval
  → Gemini 2.5 Flash SSE (fast / deep / verify modes)
  → IA-Engine-C §19-D Confidence Scorer
  → [PROVISIONAL] / [TEMPORAL_REVERSAL] auto-labels
```

## Tech Stack

- **Backend**: FastAPI (Python 3.12), SQLite, APScheduler
- **Frontend**: Vanilla JS ES6, Leaflet, Cytoscape.js, vis-timeline
- **AI**: Gemini 2.5 Flash (SSE streaming, thinking mode)
- **Data**: ACLED, GDELT, NASA FIRMS, AISStream, OpenSky, SIPRI, EIA, COW, Kiel Institute, CSIS

## Getting Started

```bash
# Backend
cd backend
source .venv/bin/activate
uvicorn main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend
python3 -m http.server 3000
# Open http://localhost:3000
```

## Data Sources

| Source | Type | Records / Coverage |
|--------|------|--------------------|
| ACLED | Conflict events (baseline) | 252,409 (41 countries) |
| GDELT + GKG | Real-time conflict + tone | Live, 15-min cycle |
| SIPRI | Military expenditure | 15 countries × 5 years |
| COW Alliance | Alliance formations | 44 active pairs |
| Kiel Institute | Ukraine support tracker | 19 donor countries |
| EIA | Energy stats + chokepoints | 19 countries + 6 chokepoints |
| CSIS Cyber DB | Significant cyber incidents | 20 incidents (2015–2024) |
| NASA FIRMS | Fire/hotspots | Live, 6-hour cycle |
| AISStream | Naval AIS | Live |
| OpenSky | Military ADS-B | Live |

## Development Roadmap

- [x] Phase 0: Foundation (FastAPI + Leaflet + Event model)
- [x] Phase 1: MVP (5 layers + first Cascade rule)
- [x] Phase 2: Core differentiation (realtime + 11 rules + causal graph)
- [x] Phase 3: Learning tool (Theory Library + Sandbox + 8-stage reasoning)
- [x] Phase 4: Data enrichment (SIPRI + COW + Kiel + EIA + CSIS + 38 briefings)
- [x] Phase 5: Reasoning intelligence (multi-agent + Diffusion score + Insight Analyst)
- [x] Phase 6 (current, v6.0.0): IA-Engine-C confidence scoring + §19-D + temporal reversal detection
- [ ] Phase 7: IA-Engine-D — Granger auto-verification pipeline (H1/H0 → r, p-value injection)
- [ ] Phase 8: Competing theory prediction-deviation comparison (doctoral level)

## License

MIT License
