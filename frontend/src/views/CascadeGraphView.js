/**
 * CascadeGraphView.js — Cascade 인과 그래프 패널 (Cytoscape.js 기반)
 *
 * CLAUDE.md 3.4: "인과 그래프 뷰: Cytoscape.js, 한 이벤트의 상하위 노드 트리"
 *
 * 데이터 흐름:
 *   EventBus('cascade:loaded') → 집계 그래프 구성 (API 이중 호출 없음)
 *   EventBus('marker:click')   → 해당 region 노드 강조 + 패널 자동 열기
 *
 * 시각화 구조 (집계 양분 그래프):
 *   좌측 노드 — 분쟁 지역(region): 타원, 빨강  ← 원인
 *   우측 노드 — 시장 지표(ticker): 다이아몬드, 황금  ← 결과
 *   엣지      — 인과 룰: 평균 등락률 + 링크 수 표시
 *
 * 집계 전략:
 *   24개 개별 이벤트 노드 대신 region/ticker로 집계해 12개 이하 노드를 만든다.
 *   "어떤 지역의 분쟁이 어떤 시장 지표로 전이되는가"를 한눈에 파악하는 것이 목적.
 *   Farrell & Newman의 Weaponized Interdependence — 상호의존 네트워크 구조를 시각화.
 */

/* global cytoscape */

import { THEORY_DB, RULE_LABEL } from '../panels/TheoryPanel.js';

// region_code → 표시용 한국어 레이블
const REGION_LABEL = {
  bab_el_mandeb:    '바브엘만데브\n(홍해)',
  ukraine:          '우크라이나',
  middle_east:      '중동',
  south_china_sea:  '남중국해',
  suez:             '수에즈',
  hormuz:           '호르무즈',
  taiwan_strait:    '대만해협',
  north_korea:      '북한',
  korean_peninsula: '한반도',
};

// ticker → 표시용 레이블
const TICKER_LABEL = {
  'CL=F':  '원유\n(WTI)',
  'ZW=F':  '밀선물\n(ZW=F)',
  'GLD':   '금 ETF',
  'ITA':   '방산\nETF',
  'NG=F':  'LNG\n선물',
  'ZIM':   '해운주\n(ZIM)',
  'TSM':   'TSMC',
  'SOXX':  '반도체\nETF',
  'KRW=X': '원/달러',
  '^KS11': '코스피',
  'TIP':   '물가연동채\n(TIP)',
  'INTC':  '인텔\n(CHIPS Act)',
  'QQQ':   '나스닥\n(QQQ)',
};

// region → 이론 태그 (Cytoscape 노드 클릭 시 TheoryPanel에 전달)
const REGION_THEORY_TAGS = {
  bab_el_mandeb:    ['SLOC_disruption', 'gray_zone', 'resource_weaponization'],
  ukraine:          ['conventional_warfare', 'food_security'],
  middle_east:      ['resource_weaponization', 'safe_haven'],
  south_china_sea:  ['A2AD', 'gray_zone'],
  suez:             ['SLOC_disruption', 'gray_zone'],
  hormuz:           ['SLOC_disruption', 'resource_weaponization'],
  taiwan_strait:    ['A2AD', 'techno_nationalism'],
  north_korea:      ['asymmetric_warfare'],
  korean_peninsula: ['gray_zone', 'asymmetric_warfare'],
};

// ── Cytoscape 색상 상수 ───────────────────────────────────────────────
// CSS 변수를 Cytoscape 스타일에서 직접 쓸 수 없으므로 상수로 추출한다.
const C_CONFLICT        = '#c0392b';   // 분쟁 지역 노드 — 위협 연상 빨강
const C_CONFLICT_BORDER = '#e74c3c';
const C_MARKET          = '#b7950b';   // 시장 지표 노드 — 경제 연상 황금
const C_MARKET_BORDER   = '#ffe566';
const C_EDGE            = '#ffe566';   // 인과 화살표 — CascadeLayer 화살표와 동일 노랑
const C_HIGHLIGHT       = '#00e5ff';   // 하이라이트 — 파란 선택 강조
const C_BG              = '#0d1117';   // 그래프 배경 (--color-bg)

// depth별 체인 노드 색상 (Snyder 동맹 딜레마 — 연루 강도 시각화)
// depth=1: 흰 테두리 (1차 충격), depth=2: 노랑 (2차 전이), depth=3: 주황 (3차 파급)
const C_CHAIN_DEPTH = {
  1: { border: '#ffffff', bg: '#b7950b' },   // 기본 market 색 유지 + 흰 테두리
  2: { border: '#ffe566', bg: '#5d4037' },   // 갈색 배경 + 노랑 테두리
  3: { border: '#ff9800', bg: '#6d2600' },   // 진한 주황 배경 + 주황 테두리
};

const CYTOSCAPE_STYLE = [
  // 분쟁 지역 노드 (원인 — 그래프 좌측)
  {
    selector: 'node[type = "conflict"]',
    style: {
      'background-color': C_CONFLICT,
      'border-color':     C_CONFLICT_BORDER,
      'border-width':     2,
      'label':            'data(label)',
      'color':            '#fff',
      'font-size':        '10px',
      'font-weight':      'bold',
      'text-valign':      'center',
      'text-halign':      'center',
      'text-wrap':        'wrap',
      'text-max-width':   '75px',
      'width':            '90px',
      'height':           '52px',
      'shape':            'ellipse',
    },
  },
  // 시장 지표 노드 (결과 — 그래프 우측)
  {
    selector: 'node[type = "market"]',
    style: {
      'background-color': C_MARKET,
      'border-color':     C_MARKET_BORDER,
      'border-width':     2,
      'label':            'data(label)',
      'color':            '#fff',
      'font-size':        '10px',
      'font-weight':      'bold',
      'text-valign':      'center',
      'text-halign':      'center',
      'text-wrap':        'wrap',
      'text-max-width':   '65px',
      'width':            '80px',
      'height':           '52px',
      'shape':            'diamond',
    },
  },
  // 인과 엣지 — 기본 (상관도 보통)
  {
    selector: 'edge',
    style: {
      'width':                2,
      'line-color':           C_EDGE,
      'target-arrow-color':   C_EDGE,
      'target-arrow-shape':   'triangle',
      'curve-style':          'bezier',
      'label':                'data(label)',
      'font-size':            '9px',
      'color':                '#bbb',
      'text-background-color':   C_BG,
      'text-background-opacity': 0.85,
      'text-background-padding': '2px',
      'text-wrap':               'wrap',
      'text-max-width':          '70px',
    },
  },
  // 상관도 높을수록 엣지 굵게 (학습 포인트: 통계적 유의미성)
  { selector: 'edge[score > 0.5]', style: { 'width': 3 } },
  { selector: 'edge[score > 0.8]', style: { 'width': 5 } },
  // 다단계 체인 depth별 노드 색상 구분 (CLAUDE.md §11-A: Cascade 룰 체이닝)
  // depth=2: 노랑 테두리 — TSMC하락→인텔상승(CHIPS Act) 같은 2차 전이
  {
    selector: 'node[depth = 2]',
    style: {
      'background-color': C_CHAIN_DEPTH[2].bg,
      'border-color':     C_CHAIN_DEPTH[2].border,
      'border-width':     3,
    },
  },
  // depth=3: 주황 테두리 — 방산ETF상승 같은 3차 파급 효과
  {
    selector: 'node[depth = 3]',
    style: {
      'background-color': C_CHAIN_DEPTH[3].bg,
      'border-color':     C_CHAIN_DEPTH[3].border,
      'border-width':     4,
    },
  },
  // 체인 엣지 (depth≥2) — 점선으로 일반 인과 엣지와 구분
  { selector: 'edge[depth > 1]', style: { 'line-style': 'dashed', 'line-dash-pattern': [6, 4] } },
  // 마커 클릭 시 — 해당 region 노드 + 연결 하이라이트
  {
    selector: '.hl-node',
    style: {
      'border-color':   C_HIGHLIGHT,
      'border-width':   4,
      'overlay-color':  C_HIGHLIGHT,
      'overlay-opacity': 0.15,
    },
  },
  {
    selector: '.hl-edge',
    style: {
      'line-color':           C_HIGHLIGHT,
      'target-arrow-color':   C_HIGHLIGHT,
      'width':                5,
    },
  },
  { selector: '.dimmed', style: { 'opacity': 0.15 } },
];

// DOM 참조 — 파일 상단 const (CLAUDE.md JS 원칙)
const PANEL_EL        = document.getElementById('cascade-graph-panel');
const COUNT_EL        = document.getElementById('cascade-graph-count');
const CY_EL           = document.getElementById('cascade-graph-cy');
const FIT_EL          = document.getElementById('cascade-graph-fit');
const FULLSCREEN_EL   = document.getElementById('cascade-graph-fullscreen');
const INNER_THEORY_EL = document.getElementById('cascade-graph-inner-theory');

export class CascadeGraphView {
  /** @param {EventBus} eventBus */
  constructor(eventBus) {
    this._eventBus     = eventBus;
    this._cy           = null;   // Cytoscape 인스턴스 (첫 open 시 초기화)
    this._isOpen       = false;
    this._isFullscreen = false;
    this._elements     = [];     // 집계된 그래프 elements 캐시

    FIT_EL.addEventListener('click', () => this._fitAll());
    FULLSCREEN_EL.addEventListener('click', () => this._toggleFullscreen());

    // 타임라인 제거 후 패널을 기본 open 상태로 유지
    this._open();

    // cascade:loaded — CascadeLayer가 이미 한 API 호출을 재사용 (이중 호출 방지)
    eventBus.on('cascade:loaded', data => this._onCascadeLoaded(data));

    // marker:click — 분쟁 마커 클릭 시 해당 region 노드 강조 + 자동 열기
    eventBus.on('marker:click', ev => this._onMarkerClick(ev));

    // marker:close — 하이라이트 초기화
    eventBus.on('marker:close', () => this._resetHighlight());
  }

  // ── 데이터 핸들러 ─────────────────────────────────────────────────

  _onCascadeLoaded(data) {
    const linkCount = (data.links ?? []).length;
    this._elements  = this._buildElements(data);

    COUNT_EL.textContent = `${linkCount}개 링크 · ${this._elements.filter(e => !e.data.source).length}개 노드`;

    if (this._cy) {
      // 이미 초기화된 경우 데이터 교체 후 레이아웃 재실행
      this._cy.elements().remove();
      this._cy.add(this._elements);
      this._runLayout();
    }
  }

  /**
   * links + events → Cytoscape 집계 elements 변환
   *
   * region(원인) → ticker(결과) 양분 그래프를 만든다.
   * 같은 (region, ticker) 쌍의 링크가 여러 개면 집계해 하나의 엣지로 표현.
   * 집계값: 평균 상관도(avgScore), 평균 등락률(avgPct), 링크 수(count)
   */
  _buildElements(data) {
    const links = data.links ?? [];

    // link.id → link 인덱스 (체인 부모 역참조용)
    const linkById = new Map(links.map(l => [l.id, l]));

    // depth=1 집계용
    const regionMap = new Map();  // region → { count }
    const tickerMap = new Map();  // `ticker::depth` → { count, maxDepth }
    // `region::ticker` → { count, totalScore, pctSum, rule_id }
    const edgeMap   = new Map();
    // 체인 엣지: `srcTicker::dstTicker::depth` → { count, totalScore, pctSum, rule_id, depth }
    const chainEdgeMap = new Map();

    for (const link of links) {
      const depth  = link.depth ?? 1;
      const ticker = link.evidence?.ticker;
      if (!ticker) continue;

      if (depth === 1) {
        // 1단계: 분쟁지역 → 시장 지표 (기존 로직)
        const region = link.evidence?.region;
        if (!region) continue;

        if (!regionMap.has(region)) regionMap.set(region, { count: 0 });
        regionMap.get(region).count++;

        const tKey = `${ticker}::1`;
        if (!tickerMap.has(tKey)) tickerMap.set(tKey, { count: 0, depth: 1 });
        tickerMap.get(tKey).count++;

        const eKey = `${region}::${ticker}`;
        if (!edgeMap.has(eKey)) {
          edgeMap.set(eKey, { count: 0, totalScore: 0, pctSum: 0, rule_id: link.rule_id ?? '', rule_name: link.rule_name ?? '' });
        }
        const e = edgeMap.get(eKey);
        e.count++;
        e.totalScore += link.correlation_score ?? 0;
        e.pctSum     += link.evidence?.pct_change ?? 0;

      } else {
        // 2단계 이상: 이전 ticker → 이 ticker (체인 엣지)
        // parent_link_id를 따라 올라가 직전 단계의 ticker를 찾는다.
        const parentLink = linkById.get(link.parent_link_id);
        const srcTicker  = parentLink?.evidence?.ticker;
        if (!srcTicker) continue;

        const tKey = `${ticker}::${depth}`;
        if (!tickerMap.has(tKey)) tickerMap.set(tKey, { count: 0, depth });
        tickerMap.get(tKey).count++;

        const cKey = `${srcTicker}::${ticker}::${depth}`;
        if (!chainEdgeMap.has(cKey)) {
          chainEdgeMap.set(cKey, { count: 0, totalScore: 0, pctSum: 0, rule_id: link.rule_id ?? '', rule_name: link.rule_name ?? '', depth });
        }
        const ce = chainEdgeMap.get(cKey);
        ce.count++;
        ce.totalScore += link.correlation_score ?? 0;
        ce.pctSum     += link.evidence?.pct_change ?? 0;
      }
    }

    const elements = [];

    // 분쟁 지역 노드 (depth=1 원인 노드)
    for (const [region, info] of regionMap) {
      elements.push({
        data: {
          id:    `r_${region}`,
          label: REGION_LABEL[region] ?? region,
          type:  'conflict',
          depth: 0,
          region,
          count: info.count,
        },
      });
    }

    // 시장 지표 노드 (depth별로 별도 노드 ID)
    for (const [tKey, info] of tickerMap) {
      const [ticker] = tKey.split('::');
      elements.push({
        data: {
          id:    `t_${tKey}`,           // "t_TSM::1", "t_INTC::2" 등 depth 포함
          label: TICKER_LABEL[ticker] ?? ticker,
          type:  'market',
          depth: info.depth,
          ticker,
          count: info.count,
        },
      });
    }

    let idx = 0;

    // depth=1 인과 엣지 (지역 → 시장)
    for (const [key, info] of edgeMap) {
      const [region, ticker] = key.split('::');
      const avgScore = info.totalScore / info.count;
      const avgPct   = info.pctSum / info.count;
      const pctStr   = `${avgPct > 0 ? '+' : ''}${avgPct.toFixed(1)}%`;
      const nameShort = (info.rule_name || info.rule_id).slice(0, 10);
      elements.push({
        data: {
          id:        `e_${idx++}`,
          source:    `r_${region}`,
          target:    `t_${ticker}::1`,
          rule_id:   info.rule_id,
          rule_name: info.rule_name,
          score:     Math.round(avgScore * 100) / 100,
          label:     `${nameShort}\n${pctStr}`,
          count:     info.count,
          depth:     1,
        },
      });
    }

    // depth≥2 체인 엣지 (시장 → 시장, 점선)
    for (const [key, info] of chainEdgeMap) {
      const [srcTicker, dstTicker] = key.split('::');
      const avgScore  = info.totalScore / info.count;
      const avgPct    = info.pctSum / info.count;
      const pctStr    = `${avgPct > 0 ? '+' : ''}${avgPct.toFixed(1)}%`;
      const nameShort = (info.rule_name || info.rule_id).slice(0, 10);
      elements.push({
        data: {
          id:        `e_${idx++}`,
          source:    `t_${srcTicker}::${info.depth - 1}`,
          target:    `t_${dstTicker}::${info.depth}`,
          rule_id:   info.rule_id,
          rule_name: info.rule_name,
          score:     Math.round(avgScore * 100) / 100,
          label:     `${nameShort}\n${pctStr}`,
          count:     info.count,
          depth:     info.depth,
        },
      });
    }

    return elements;
  }

  // ── 마커 연동 ─────────────────────────────────────────────────────

  _onMarkerClick(ev) {
    // 분쟁 이벤트가 아니면 무시 (기지 마커, 케이블 등은 source_type 없음)
    if (!ev || ev.source_type !== 'conflict') return;

    const region = ev.region_code;
    if (!region) return;

    // 해당 region에 cascade 활성 링크가 있을 때만 패널 자동 열기
    const hasNode = this._elements.some(el => el.data?.id === `r_${region}`);
    if (!hasNode) return;

    if (!this._isOpen) this._open();
    this._highlightRegion(region);
  }

  _highlightRegion(region) {
    if (!this._cy) return;

    this._resetHighlight();

    const regionNode = this._cy.getElementById(`r_${region}`);
    if (regionNode.length === 0) return;

    // region에서 시작해 다단계 체인 전체를 DFS로 수집
    // successors()는 방향 그래프에서 도달 가능한 모든 후속 노드+엣지를 반환한다.
    const chainEles = regionNode.successors();
    regionNode.addClass('hl-node');
    chainEles.nodes().addClass('hl-node');
    chainEles.edges().addClass('hl-edge');

    // 나머지 요소는 희미하게
    this._cy.elements().not('.hl-node, .hl-edge').addClass('dimmed');

    // 강조된 전체 체인으로 뷰 이동 (부드럽게)
    this._cy.animate({
      fit: { eles: regionNode.union(chainEles), padding: 40 },
      duration: 350,
      easing:   'ease-in-out-cubic',
    });
  }

  _resetHighlight() {
    if (!this._cy) return;
    this._cy.elements().removeClass('hl-node hl-edge dimmed');
  }

  // ── 패널 열기/닫기 ────────────────────────────────────────────────

  _toggle() {
    this._isOpen ? this._close() : this._open();
  }

  _open() {
    this._isOpen = true;
    PANEL_EL.classList.add('is-open');

    if (!this._cy) {
      // CSS transition(250ms) 완료 후 Cytoscape 초기화 — 컨테이너가 완전히 펼쳐진 뒤
      // 레이아웃을 계산해야 노드 배치가 올바르게 된다.
      setTimeout(() => this._initCytoscape(), 270);
    } else {
      setTimeout(() => {
        this._cy.resize();
        this._cy.fit(undefined, 20);
      }, 270);
    }
  }

  _close() {
    if (this._isFullscreen) this._exitFullscreen();
    this._isOpen = false;
    PANEL_EL.classList.remove('is-open');
  }

  // ── 내부 이론 패널 (전체화면 전용) ──────────────────────────────

  /**
   * 전체화면 내부 우측 패널에 이론 카드를 렌더링한다.
   * 글로벌 TheoryPanel 대신 사용하므로 marker:click을 emit하지 않는다.
   * 기존 TheoryPanel의 CSS 클래스(theory-card, theory-panel__body 등)를 재사용.
   */
  _showInternalTheory(region) {
    const tags     = REGION_THEORY_TAGS[region] ?? [];
    const theories = tags.map(t => THEORY_DB[t]).filter(Boolean);
    const label    = REGION_LABEL[region] ?? region;

    // 이 region에서 출발하는 엣지들 — cascade 확인 배지에 사용
    const regionEdges = this._elements.filter(el =>
      el.data?.source === `r_${region}` && el.data?.target
    );

    const cardsHTML = theories.length
      ? theories.map(t => this._buildMiniCard(t, regionEdges)).join('')
      : `<p class="theory-panel__empty">이 지역에 매핑된 이론이 없습니다.<br>theory_tags: ${tags.join(', ') || '(없음)'}</p>`;

    INNER_THEORY_EL.innerHTML = `
      <div class="theory-panel__header">
        <div class="theory-panel__header-meta">
          <span class="theory-panel__label">이론 분석</span>
        </div>
        <div class="theory-panel__event-title">${label} — 인과 연쇄</div>
        <div class="theory-panel__event-meta">
          <span>Cascade Graph 선택</span>
        </div>
      </div>
      <div class="theory-panel__body">${cardsHTML}</div>
    `;
  }

  /**
   * 이론 카드 HTML 생성 — TheoryPanel._buildCard()의 경량 버전.
   * 학습 포인트(도서관 팁, Korea relevance)는 포함하되, 노트 슬롯은 생략.
   */
  _buildMiniCard(theory, regionEdges) {
    // 이 이론의 cascade rule 중 실제 활성(엣지 존재) 링크 확인
    const confirmedHTML = regionEdges
      .filter(e => (theory.cascade_rules ?? []).includes(e.data?.rule_id))
      .map(e => {
        const ruleLabel = RULE_LABEL[e.data.rule_id] ?? e.data.rule_id;
        // edge label: "+1.8%\n(2건)" → "+1.8% (2건)"
        const badge = (e.data.label ?? '').replace('\n', ' ');
        return `<div class="theory-card__confirmed">⛓ ${ruleLabel} <span class="theory-card__pct">${badge}</span></div>`;
      })
      .join('');

    const readingHTML = (theory.reading ?? [])
      .slice(0, 3)
      .map(r => r.url
        ? `<a class="theory-card__link" href="${r.url}" target="_blank" rel="noopener">${r.title}</a>`
        : `<span class="theory-card__link-text">${r.title}</span>`
      )
      .join('');

    const tipHTML = theory.library_tip ? `
      <details class="theory-card__tip">
        <summary class="theory-card__tip-summary">💡 도서관 검색 팁</summary>
        <div class="theory-card__tip-body">
          ${theory.library_tip.riss  ? `<div><span class="theory-card__tip-db">RISS</span>${theory.library_tip.riss}</div>`  : ''}
          ${theory.library_tip.dbpia ? `<div><span class="theory-card__tip-db">DBpia</span>${theory.library_tip.dbpia}</div>` : ''}
        </div>
      </details>
    ` : '';

    return `
      <div class="theory-card">
        <div class="theory-card__header">
          <span class="theory-card__icon">📚</span>
          <div>
            <div class="theory-card__name">${theory.name}</div>
            <div class="theory-card__scholars">${theory.scholars}</div>
          </div>
        </div>
        <p class="theory-card__summary">${theory.summary}</p>
        <p class="theory-card__detail">${theory.detail}</p>
        ${confirmedHTML ? `
          <div class="theory-card__cascade">
            <div class="theory-card__cascade-title">활성 Cascade Rule</div>
            ${confirmedHTML}
          </div>
        ` : ''}
        <div class="theory-card__reading">${readingHTML}</div>
        ${tipHTML}
      </div>
    `;
  }

  _clearInternalTheory() {
    INNER_THEORY_EL.innerHTML =
      '<p class="cgraph__inner-theory-hint">노드를 클릭하면<br>이론 분석이 표시됩니다.</p>';
  }

  _fitAll() {
    if (!this._cy) return;
    this._resetHighlight();
    this._cy.animate({
      fit:      { eles: this._cy.elements(), padding: 20 },
      duration: 350,
      easing:   'ease-in-out-cubic',
    });
  }

  _toggleFullscreen() {
    this._isFullscreen ? this._exitFullscreen() : this._enterFullscreen();
  }

  _enterFullscreen() {
    // 패널이 닫혀 있으면 먼저 열기
    if (!this._isOpen) this._open();

    this._isFullscreen = true;
    PANEL_EL.classList.add('is-fullscreen');
    FULLSCREEN_EL.textContent = '✕';
    FULLSCREEN_EL.title = '전체화면 종료';

    // CSS transition(300ms) 완료 후 1회만 resize+fit — 더블 줌 방지
    setTimeout(() => {
      if (!this._cy) return;
      this._cy.resize();
      this._cy.fit(undefined, 40);
    }, 300);
  }

  _exitFullscreen() {
    this._isFullscreen = false;
    PANEL_EL.classList.remove('is-fullscreen');
    FULLSCREEN_EL.textContent = '⛶';
    FULLSCREEN_EL.title = '전체화면 전환';
    this._clearInternalTheory();

    // CSS transition 완료 후 1회만 resize+fit
    setTimeout(() => {
      if (!this._cy) return;
      this._cy.resize();
      this._cy.fit(undefined, 20);
    }, 300);
  }

  // ── Cytoscape 초기화 ──────────────────────────────────────────────

  _initCytoscape() {
    this._cy = cytoscape({
      container: CY_EL,
      elements:  this._elements,
      style:     CYTOSCAPE_STYLE,
      layout:    this._layoutConfig(),
      minZoom:   0.25,
      maxZoom:   4,
    });

    // 분쟁 지역 노드 클릭
    // 전체화면: 내부 이론 패널에 렌더 (글로벌 TheoryPanel 미사용)
    // 일반 모드: 기존 TheoryPanel에 marker:click emit
    this._cy.on('tap', 'node[type = "conflict"]', evt => {
      const region = evt.target.data('region');
      this._highlightRegion(region);

      if (this._isFullscreen) {
        this._showInternalTheory(region);
      } else {
        this._eventBus.emit('marker:click', {
          source_type: 'conflict',
          region_code: region,
          title:       `${REGION_LABEL[region] ?? region} — 인과 연쇄`,
          severity:    65,
          timestamp:   new Date().toISOString(),
          theory_tags: REGION_THEORY_TAGS[region] ?? [],
          description: 'Cascade 그래프에서 선택된 분쟁 지역',
          id:          null,
        });
      }
    });

    // 배경 클릭 → 하이라이트 해제
    this._cy.on('tap', evt => {
      if (evt.target === this._cy) {
        this._resetHighlight();
        if (this._isFullscreen) {
          this._clearInternalTheory();
        } else {
          this._eventBus.emit('marker:close');
        }
      }
    });
  }

  _runLayout() {
    if (!this._cy) return;
    this._cy.layout(this._layoutConfig()).run();
  }

  /**
   * breadthfirst 레이아웃: 방향 그래프 계층 배치.
   * directed=true이면 인입 엣지 없는 노드(region)를 루트로 잡아 좌→우 배치.
   * 플러그인 없이 Cytoscape 내장 레이아웃만 사용 (저비용 원칙).
   */
  _layoutConfig() {
    return {
      name:              'breadthfirst',
      directed:          true,
      padding:           24,
      spacingFactor:     1.7,
      animate:           true,
      animationDuration: 420,
      animationEasing:   'ease-in-out-cubic',
    };
  }
}
