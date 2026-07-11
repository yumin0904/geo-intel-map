# 데이터 출처 목록 (Data Provenance) — geo-intel-map IA-Engine

> IA-Engine이 분석에 사용하는 데이터 소스의 출처·버전·인용 정보를 한곳에 모은 문서.
> **단일 진실 공급원:** 각 항목의 버전·연도는 `backend/data/external/*.csv` (및 `data/trade/*.csv`) seed 파일의 헤더 주석에서 가져온 것이다. seed를 갱신하면 이 문서도 함께 갱신한다.
> 신뢰 수준: **(A) 정량 데이터셋** = 1차 통계 DB / **(B) 질적·큐레이션** = 2차 가공·해석 포함 / **(C) 실시간 커넥터** = API 수집.
> 소스 전수의 기계 가독 진실원은 `backend/config/source_roster.yaml` — 이 문서는 사람용 설명.
> 최종 확인: 2026-07-09.

---

## (A) 정량 데이터셋 — 정형 통계 (seed CSV)

### 분쟁·안보
- **ACLED** — Armed Conflict Location & Event Data Project. *ACLED data* [Data set]. https://acleddata.com
  - 용도: 지역별 분쟁 이벤트 건수·유형. (커넥터 `connectors/acled.py` + 벌크 적재)
- **COW Inter-State / Intra-State Wars** (v4.0) — Correlates of War Project. https://correlatesofwar.org
  - seed: `cow_wars_seed.csv` · 용도: 전쟁 선례 시계열, 전투 사망자 추정.
- **HIIK Conflict Barometer 2024** — Heidelberg Institute for International Conflict Research. https://hiik.de/en/conflict-barometer/
  - seed: `hiik_conflict_seed.csv` · 강도 척도 1(분쟁)~5(전쟁).
- **CNS North Korea Missile Test Database** — James Martin Center for Nonproliferation Studies (NTI 호스팅). https://www.nti.org/analysis/articles/cns-north-korea-missile-test-database/
  - 적재 스크립트: `scripts/nk_missile_ingest.py` → `event_archive`(source_type='missile_test'). 1984년부터 북한 미사일 발사 전수 큐레이션. ACLED가 폐쇄국가 북한을 커버 못 해(korean_peninsula 이벤트 98%가 남한 시위) 도입된 대안 — 구조적 미관측 데이터갭 해소용, NTI 갱신 주기에 종속(source_roster.yaml `cns_nk_missile`).

### 거버넌스·정치체제
- **V-Dem (Varieties of Democracy)** v14 (2024) — V-Dem Institute, University of Gothenburg. https://v-dem.net
  - seed: `vdem_seed.csv` · 지표: `v2x_libdem` 자유민주주의 지수(0~1).
- **Polity5** — Center for Systemic Peace. https://www.systemicpeace.org/polityproject.html
  - seed: `polity5_seed.csv` · 지표: polity score −10~+10.
- **World Bank — Worldwide Governance Indicators (WGI)** 2022 — World Bank Open Data. https://data.worldbank.org/indicator
  - seed: `world_bank_seed.csv` · 지표: 정치안정·법치 등(−2.5~+2.5).

### 군사·동맹
- **SIPRI Military Expenditure Database** (Yearbook 2024) — Stockholm International Peace Research Institute. https://www.sipri.org/databases/milex
  - seed: `sipri_milex_seed.csv` · 지표: 국방비 %GDP, USD(2022 불변가).
- **SIPRI Arms Transfers Database** (TIV, 2020–2024) — SIPRI. https://www.sipri.org/databases/armstransfers
  - seed: `sipri_arms_seed.csv` · 지표: TIV(무기 이전 표준화 지수).
- **COW Formal Alliances** (v4.1) — Correlates of War Project. https://correlatesofwar.org
  - seed: `cow_alliances_seed.csv` · 동맹 유형: defense/neutrality/nonaggression/consultation.

### 경제·에너지
- **Kiel Ukraine Support Tracker** (Release 21, 2025-03) — Kiel Institute for the World Economy. https://www.ifw-kiel.de/topics/war-against-ukraine/ukraine-support-tracker/
  - seed: `kiel_ukraine_support_seed.csv` · 단위: EUR bn (약정+전달 합산).
- **FRED (Federal Reserve Economic Data)** — Federal Reserve Bank of St. Louis. https://fred.stlouisfed.org
  - seed: `fred_seed.csv` · 주요 거시 시계열(CPI 등).
- **EIA International Energy Statistics** (+ IEA WEO 2023) — U.S. Energy Information Administration. https://www.eia.gov/international/
  - seed: `eia_energy_seed.csv` · 지표: 원유 생산량(mbpd) 등.
- **World Bank WITS / UN Comtrade — 무역 의존도** — https://wits.worldbank.org
  - seed: `data/trade/wits_trade_detailed.csv`, `wits_trade_world.csv` · (정확 버전·연도 `[확인]`).

### 사이버·기술
- **CSIS Significant Cyber Incidents Database** — CSIS Strategic Technologies Program. https://www.csis.org/programs/strategic-technologies-program/significant-cyber-incidents
  - seed: `csis_cyber_seed.csv`(2015–2024 선별), `csis_cyber_extended_seed.csv`(2006–2024 확장 + 피해액 추정).
- **ITU ICT Development Index (IDI) 2023** — International Telecommunication Union. https://www.itu.int/en/ITU-D/Statistics/Pages/IDI/
  - seed: `itu_ict_seed.csv` · 0~100 종합 지수.
- **반도체·핵심기술 시장 데이터** — SIA(Semiconductor Industry Association), CSIS, TechInsights, Statista (2023–2024).
  - seed: `semi_market_seed.csv` · 파운드리 점유율·핵심광물·수출통제 등.

### 다지표 큐레이션
- **Our World in Data — 군사비·핵탄두** (2015–2023, 원천: SIPRI/FAS) — https://ourworldindata.org
  - seed: `owid_seed.csv`.

---

## (B) 질적·보고서 (분석에 인용 시 개별 서지 표기)

2차 가공·해석이 포함된 자료는 사용할 때마다 **개별 APA7 서지**로 표기한다(예: 본 발표의 CSIS·War on the Rocks 보고서 → `presentation/presentation_russia_ukraine.md` 참고문헌 절). 데이터셋 단위로 일괄 인용하지 않는다.

---

## (C) 실시간 커넥터 (API 수집 — 적재 시점 데이터)

| 소스 | 커넥터 | 용도 |
|------|--------|------|
| GDELT (Events / GKG) | `connectors/gdelt_connector.py`, `gdelt_gkg.py` | 실시간 사건·테마·톤 (Token-Zero CAMEO 매핑) |
| ReliefWeb (UN OCHA) | `connectors/reliefweb.py` | 인도적 위기·분쟁 보고 |
| NASA FIRMS (VIIRS) | `connectors/nasa_firms.py` | 위성 열점/화재 |
| OpenSky Network | `connectors/opensky.py` | 군용기 ADS-B |
| AISStream.io | `connectors/aisstream.py` | 군함/상선 AIS |
| yfinance / 시장지표 | `connectors/yfinance_adapter.py` | 시장 오버레이(주가·선물) |
| 제재(GSDB/UN) | `connectors/sanctions_connector.py` | 제재 레이어 |
| 외교부 LOD (IFANS) | `connectors/mofa_lod.py` | 한국 시각 발간자료(SPARQL) |
| GovInfo.gov CPD | `connectors/govinfo_connector.py` | 미 대통령 성명·기자회견·의회 연설 원문(1차 사료) → `govinfo_releases`. 스케줄러 12시간 주기(`jobs/press_releases_job.py::run_govinfo_batch`) |
| 외교부 보도자료 (공공데이터포털 15141564) | `connectors/mofa_press.py` | 한국 정부 1차 사료, 22,483건 전체 적재 → `mofa_press_releases`. 스케줄러 미등록 — CLI 수동 실행(`python3 -m connectors.mofa_press`), 주기 미확인 |
| CSIS Beyond Parallel 북한 도발 DB | `connectors/bp_provocations_connector.py` | 북한 도발 사건·유형층(1958~, CNS 단종 병렬 후속 — 채택위 07-11) → `bp_provocations`. launchd 일 2회 수집잡 내 배선(`jobs/press_releases_job.py::run_bp_provocations_batch`). ⚠️ CNS와 접합 금지(로스터 노트) |
| NKNews + 38 North | `connectors/nk_news_connector.py` | 북한 전문 뉴스·학술 분석 → `nk_press_releases`. 스케줄러 6시간 주기(`jobs/press_releases_job.py::run_nk_press_batch`) |
| UN News | `connectors/un_news_connector.py` | UN 공식 뉴스(다자 시각, 이중결정 검정 보강) → `un_news_releases`. 스케줄러 6시간 주기(`jobs/press_releases_job.py::run_un_news_batch`) |
| Atlantic Council + Arms Control Assoc | `connectors/policy_think_tank_connector.py` | 워싱턴 외교안보 싱크탱크 정책 분석 → `policy_releases`. 스케줄러 6시간 주기(`jobs/press_releases_job.py::run_policy_think_tank_batch`) |
| GDELT 국가급 일간 카운트 (BigQuery) | `scripts/load_gdelt_bq.py` | 2015~현재 국가×일 와이드 집계(총계·시위 root14·물리분쟁 quad4·언어분쟁 quad3·mentions·Goldstein) → `gdelt_country_daily`. 수동 백필(온디맨드 재실행, ~28GB 스캔/회, ADC 사용자 계정·프로젝트 geo-intel-gdelt-2026). ⚠️ §18-A: 국가급 이상 전용 + Hammond-Weidmann 보도편향 [한계] 의무 (판례 20260709-data-audit-committee 웨이브2) |

**제외 판단(커넥터 아님, 실측 근거):**
- `connectors/news_cross_validator.py` — GDELT 1단계 통과 이벤트의 RSS 교차검증 유틸리티. 자체 DB 테이블을 생성하지 않고 기존 국제뉴스 RSS를 재사용해 confidence_score만 보정(GDELT Stage 2). 독립 소스가 아니라 검증 로직.
- `connectors/gemini_translator.py` — 수집 시점이 아닌 사용자 열람 시점 on-demand 번역 래퍼(Gemini API). 데이터 수집이 아니라 기존 수집물의 후처리.

---

## 인용 규칙

1. **발표·보고서에서 데이터 수치를 쓸 때** → 해당 슬라이드/문단 하단에 APA7 저자-연도 약식 `(기관, 연도)` 표기, 전체 서지는 참고문헌 절에 모음.
2. **버전·연도 갱신 시** → seed CSV 헤더를 먼저 고치고, 이 문서를 동기화(헤더가 SSOT).
3. **(B) 질적 자료** → 데이터셋 일괄 인용 금지, 사용처마다 개별 서지.
4. **검증 원칙(§19)** → 2차 자료는 인용 전 원문 실재·수치 일치 확인. 미확인 항목은 `[UNVERIFIED]` 표기.

> 생성 메모: 본 문서는 `backend/data/external/*.csv`와 `data/trade/*.csv`의 헤더 주석에서 도출되었다.
> 향후 `scripts/`에 헤더→마크다운 자동 추출 스크립트를 두면 수기 동기화 부담을 없앨 수 있다(선택).
