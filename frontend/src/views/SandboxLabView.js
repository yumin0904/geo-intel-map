/**
 * SandboxLabView — 분석실(Sandbox Lab) 풀스크린 오버레이.
 *
 * 두 가지 모드:
 *   A. 가설 빌더 — 수동 노드/엣지 구성, 검증
 *   B. 체인 뷰어 — sandbox:toggle({event_id, report}) 수신 시 해당 region의
 *      Cascade 체인 트리를 자동 시각화 (D1→D2→D3 다단계)
 *
 * 레이아웃: 좌측 20% 캔버스 목록 | 중앙 60% Cytoscape | 우측 20% 검증/체인 결과
 * 열기/닫기: EventBus 'sandbox:toggle' 또는 ✕ 버튼
 *
 * cytoscape, cytoscape-dagre는 index.html에서 전역 로드됨
 */

// region → 한국어 레이블 (CascadeGraphView와 동일)
const REGION_LABEL_KO = {
  bab_el_mandeb:   '바브엘만데브',
  ukraine:         '우크라이나',
  middle_east:     '중동',
  south_china_sea: '남중국해',
  suez:            '수에즈',
  hormuz:          '호르무즈',
  taiwan_strait:   '대만해협',
  north_korea:     '북한',
  korean_peninsula:'한반도',
};

// ticker → 한국어 레이블
const TICKER_LABEL_KO = {
  'CL=F': '원유(WTI)', 'ZW=F': '밀선물', 'GLD': '금ETF',
  'ITA': '방산ETF', 'NG=F': 'LNG선물', 'ZIM': '해운(ZIM)',
  'TSM': 'TSMC', 'SOXX': '반도체ETF', 'KRW=X': '원/달러',
  '^KS11': '코스피', 'TIP': '물가연동채', 'INTC': '인텔',
  'QQQ': '나스닥QQQ',
};

// depth별 노드 스타일
const DEPTH_STYLE = {
  0: { bg: '#c0392b', border: '#e74c3c', shape: 'ellipse' },   // 분쟁 지역 (빨강)
  1: { bg: '#b7950b', border: '#ffe566', shape: 'diamond' },   // D1 (황금)
  2: { bg: '#5d4037', border: '#ffe566', shape: 'diamond' },   // D2 (갈색)
  3: { bg: '#6d2600', border: '#ff9800', shape: 'diamond' },   // D3 (주황)
};

const cytoscape = window.cytoscape;

export class SandboxLabView {
  /**
   * @param {L.Map}    map
   * @param {EventBus} eventBus
   */
  constructor(map, eventBus) {
    this._map  = map;
    this._bus  = eventBus;
    this._el   = null;
    this._cy   = null;          // Cytoscape 인스턴스
    this._open = false;
    this._currentCanvasId = null;
    this._canvases = [];
    this._chainMode = false;    // 체인 뷰어 모드 플래그
    this._cascadeLinks = [];    // cascade:loaded 캐시
    this._cascadeEvents = {};   // event_id → event

    this._mount();
    this._bindEvents();
  }

  // ── 마운트 ──────────────────────────────────────────────────────────────────

  _mount() {
    this._el = document.getElementById('sandbox-panel');
    if (!this._el) {
      console.error('[SandboxLabView] #sandbox-panel 요소 없음');
      return;
    }
    this._el.innerHTML = this._template();
    this._bindPanelEvents();
  }

  _template() {
    return `
      <div class="sandbox__header">
        <span class="sandbox__title">🔬 분석실</span>
        <div class="sandbox__header-actions">
          <button class="sandbox__new-btn">+ 새 가설</button>
          <button class="sandbox__close-btn" title="닫기">✕</button>
        </div>
      </div>

      <div class="sandbox__body">

        <!-- 좌측 20%: 캔버스 목록 -->
        <aside class="sandbox__sidebar">
          <div class="sandbox__sidebar-title">저장된 가설</div>
          <div class="sandbox__canvas-list"></div>

          <div class="sandbox__node-toolbar">
            <div class="sandbox__sidebar-title" style="margin-top:12px">노드 추가</div>
            <button class="sandbox__add-node-btn" data-type="event">＋ 사건</button>
            <button class="sandbox__add-node-btn" data-type="indicator">＋ 지표</button>
            <button class="sandbox__add-node-btn" data-type="outcome">＋ 결과</button>
            <div class="sandbox__sidebar-title" style="margin-top:12px">레이아웃</div>
            <button class="sandbox__layout-btn">⚙ 자동 정렬</button>
          </div>
        </aside>

        <!-- 중앙 60%: Cytoscape 그래프 -->
        <main class="sandbox__graph">
          <div class="sandbox__graph-hint" id="sandbox-hint">
            ← 좌측에서 가설을 선택하거나 새로 만드세요.
          </div>
          <div id="sandbox-cy" class="sandbox__cy"></div>
        </main>

        <!-- 우측 20%: 검증 결과 -->
        <aside class="sandbox__result">
          <div class="sandbox__sidebar-title">검증 결과</div>
          <div class="sandbox__result-empty" id="sandbox-result-empty">
            "✓ 검증" 버튼을 눌러<br>가설을 검증하세요.
          </div>
          <div class="sandbox__result-body" id="sandbox-result-body" style="display:none"></div>
          <button class="sandbox__verify-btn" id="sandbox-verify-btn" disabled>✓ 검증</button>
        </aside>

      </div>
    `;
  }

  // ── 이벤트 바인딩 ────────────────────────────────────────────────────────────

  _bindPanelEvents() {
    this._el.querySelector('.sandbox__close-btn')
      .addEventListener('click', () => this.close());

    this._el.querySelector('.sandbox__new-btn')
      .addEventListener('click', () => this._createCanvas());

    this._el.querySelectorAll('.sandbox__add-node-btn').forEach(btn => {
      btn.addEventListener('click', () => this._promptAddNode(btn.dataset.type));
    });

    this._el.querySelector('.sandbox__layout-btn')
      .addEventListener('click', () => this._runLayout());

    document.getElementById('sandbox-verify-btn')
      .addEventListener('click', () => this._verify());
  }

  _bindEvents() {
    // cascade:loaded — 체인 뷰어에서 지역 기반 체인 트리를 빌드하기 위해 캐시
    this._bus.on('cascade:loaded', data => {
      this._cascadeLinks   = data.links ?? [];
      this._cascadeEvents  = {};
      for (const ev of (data.events ?? [])) this._cascadeEvents[ev.id] = ev;
    });

    // sandbox:toggle — 페이로드 없으면 토글, event_id 있으면 체인 뷰어 모드
    this._bus.on('sandbox:toggle', payload => {
      const { event_id, report } = payload || {};
      if (event_id && report) {
        this._openWithChain(event_id, report);
      } else {
        this._open ? this.close() : this.open();
      }
    });
  }

  // ── 열기/닫기 ────────────────────────────────────────────────────────────────

  async open() {
    this._el.classList.add('is-open');
    this._open = true;
    await this._loadCanvasList();
  }

  close() {
    this._el.classList.remove('is-open');
    this._open = false;
  }

  // ── 캔버스 목록 ──────────────────────────────────────────────────────────────

  async _loadCanvasList() {
    try {
      const res = await fetch('/api/sandbox/canvases');
      this._canvases = await res.json();
    } catch {
      this._canvases = [];
    }
    this._renderCanvasList();
  }

  _renderCanvasList() {
    const list = this._el.querySelector('.sandbox__canvas-list');
    if (this._canvases.length === 0) {
      list.innerHTML = '<div class="sandbox__canvas-empty">가설 없음</div>';
      return;
    }
    list.innerHTML = this._canvases.map(c => `
      <div class="sandbox__canvas-item${this._currentCanvasId === c.id ? ' is-active' : ''}"
           data-id="${c.id}">
        <span class="sandbox__canvas-name">${c.title}</span>
        <button class="sandbox__canvas-del" data-id="${c.id}" title="삭제">✕</button>
      </div>
    `).join('');

    list.querySelectorAll('.sandbox__canvas-item').forEach(el => {
      el.addEventListener('click', e => {
        if (e.target.classList.contains('sandbox__canvas-del')) return;
        this._selectCanvas(el.dataset.id);
      });
    });

    list.querySelectorAll('.sandbox__canvas-del').forEach(btn => {
      btn.addEventListener('click', e => {
        e.stopPropagation();
        this._deleteCanvas(btn.dataset.id);
      });
    });
  }

  async _createCanvas() {
    const title = prompt('가설 이름:');
    if (!title?.trim()) return;

    const now = new Date().toISOString();
    const res = await fetch('/api/sandbox/canvases', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: title.trim(), hypothesis: '', sector_tag: null,
                             created_at: now, updated_at: now }),
    });
    if (!res.ok) {
      console.error('[Sandbox] 캔버스 생성 실패', res.status);
      await this._loadCanvasList();
      return;
    }
    const canvas = await res.json();
    await this._loadCanvasList();
    await this._selectCanvas(canvas.id);
  }

  async _deleteCanvas(canvasId) {
    if (!confirm('이 가설을 삭제하시겠습니까?')) return;
    await fetch(`/api/sandbox/canvases/${canvasId}`, { method: 'DELETE' });
    if (this._currentCanvasId === canvasId) {
      this._currentCanvasId = null;
      this._cy?.destroy();
      this._cy = null;
      document.getElementById('sandbox-hint').style.display = 'flex';
      document.getElementById('sandbox-cy').style.display = 'none';
      document.getElementById('sandbox-verify-btn').disabled = true;
    }
    await this._loadCanvasList();
  }

  async _selectCanvas(canvasId) {
    this._currentCanvasId = canvasId;
    this._renderCanvasList(); // active 상태 갱신

    const res = await fetch(`/api/sandbox/canvases/${canvasId}`);
    const data = await res.json();
    this._initCy(data.nodes, data.edges);

    document.getElementById('sandbox-hint').style.display = 'none';
    document.getElementById('sandbox-cy').style.display = 'block';
    document.getElementById('sandbox-verify-btn').disabled = false;
    this._clearResult();
  }

  // ── Cytoscape ────────────────────────────────────────────────────────────────

  _initCy(nodes, edges) {
    const container = document.getElementById('sandbox-cy');
    this._cy?.destroy();

    const elements = [
      ...nodes.map(n => ({
        data: { id: n.id, label: n.label, type: n.node_type },
        position: { x: n.x, y: n.y },
      })),
      ...edges.map(e => ({
        data: { id: e.id, source: e.source_node_id, target: e.target_node_id, kind: e.kind },
      })),
    ];

    this._cy = cytoscape({
      container,
      elements,
      style: [
        {
          selector: 'node',
          style: {
            'background-color': ele => this._nodeColor(ele.data('type')),
            label: 'data(label)',
            'text-valign': 'center',
            'text-halign': 'center',
            color: '#e6edf3',
            'font-size': 11,
            'text-wrap': 'wrap',
            'text-max-width': 70,
            width: 70,
            height: 70,
            'border-width': 2,
            'border-color': '#30363d',
          },
        },
        {
          selector: 'node:selected',
          style: { 'border-color': '#58a6ff', 'border-width': 3 },
        },
        {
          selector: 'edge',
          style: {
            'target-arrow-shape': 'triangle',
            'target-arrow-color': '#8b949e',
            'line-color': '#8b949e',
            width: 2,
            label: 'data(kind)',
            'font-size': 9,
            color: '#8b949e',
            'curve-style': 'bezier',
          },
        },
      ],
      layout: nodes.length > 0 ? { name: 'dagre' } : { name: 'preset' },
      wheelSensitivity: 0.1,
    });

    this._cy.on('dbltap', 'node', e => this._editNode(e.target));
    this._cy.on('free', 'node', e => this._saveNodePosition(e.target));
  }

  _nodeColor(type) {
    return { event: '#c0392b', indicator: '#d68910', outcome: '#1a5276' }[type] || '#5d6d7e';
  }

  async _promptAddNode(type) {
    if (!this._currentCanvasId) { alert('먼저 가설을 선택하세요.'); return; }
    const label = prompt(`${type === 'event' ? '사건' : type === 'indicator' ? '지표' : '결과'} 이름:`);
    if (!label?.trim()) return;

    const now = new Date().toISOString();
    const node = {
      canvas_id: this._currentCanvasId,
      node_type: type,
      label: label.trim(),
      x: Math.random() * 300,
      y: Math.random() * 200,
      event_ref: null, region_code: null, theory_tags: [], note: '',
      created_at: now, updated_at: now,
    };

    const res = await fetch(`/api/sandbox/canvases/${this._currentCanvasId}/nodes`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(node),
    });
    const saved = await res.json();

    this._cy.add({ data: { id: saved.id, label: saved.label, type: saved.node_type },
                   position: { x: saved.x, y: saved.y } });
  }

  _editNode(target) {
    const label = prompt('노드 이름 변경:', target.data('label'));
    if (label?.trim()) target.data('label', label.trim());
  }

  async _saveNodePosition(target) {
    if (!this._currentCanvasId) return;
    const pos = target.position();
    // 위치만 업데이트 — payload 전체를 PUT하는 대신 REPLACE upsert 재사용
    const now = new Date().toISOString();
    await fetch(`/api/sandbox/canvases/${this._currentCanvasId}/nodes`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        id: target.id(),
        canvas_id: this._currentCanvasId,
        node_type: target.data('type'),
        label: target.data('label'),
        x: pos.x, y: pos.y,
        event_ref: null, region_code: null, theory_tags: [], note: '',
        created_at: now, updated_at: now,
      }),
    });
  }

  _runLayout() {
    this._cy?.layout({ name: 'dagre', animate: true, animationDuration: 400 }).run();
  }

  // ── 가설 검증 ────────────────────────────────────────────────────────────────

  async _verify() {
    if (!this._currentCanvasId) return;

    const btn = document.getElementById('sandbox-verify-btn');
    btn.textContent = '검증 중…';
    btn.disabled = true;

    try {
      const res = await fetch(`/api/sandbox/canvases/${this._currentCanvasId}`);
      const canvasFull = await res.json();

      const vRes = await fetch(`/api/sandbox/canvases/${this._currentCanvasId}/verify`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(canvasFull),
      });
      const result = await vRes.json();
      this._renderResult(result);
    } catch (err) {
      console.error('[SandboxLabView] 검증 실패:', err);
    } finally {
      btn.textContent = '✓ 검증';
      btn.disabled = false;
    }
  }

  _clearResult() {
    document.getElementById('sandbox-result-empty').style.display = 'block';
    document.getElementById('sandbox-result-body').style.display = 'none';
  }

  _renderResult(result) {
    document.getElementById('sandbox-result-empty').style.display = 'none';
    const body = document.getElementById('sandbox-result-body');
    body.style.display = 'block';

    const pct     = Math.round(result.total_score * 100);
    const confMap = { high: '✅ 높음', medium: '◐ 중간', low: '✗ 낮음' };
    const conf    = confMap[result.confidence_level] || result.confidence_level;

    body.innerHTML = `
      <div class="sandbox__score">
        <div class="sandbox__score-circle"
             style="--score-pct:${pct}">${pct}</div>
        <div class="sandbox__score-meta">
          <strong>${conf}</strong><br>
          ${result.num_matches}개 규칙 매칭
        </div>
      </div>

      ${result.top_match ? `
        <div class="sandbox__match-card">
          <div class="sandbox__match-label">⭐ 최고 매칭</div>
          <div class="sandbox__match-name">${result.top_match.rule_name}</div>
          <div class="sandbox__match-score">${Math.round(result.top_match.match_score * 100)}%</div>
          <div class="sandbox__match-theory">${result.top_match.theory_framework}</div>
          ${result.top_match.missing_nodes.map(m =>
            `<div class="sandbox__match-gap">❌ ${m}</div>`).join('')}
        </div>` : ''}

      ${result.gaps.length > 0 ? `
        <div class="sandbox__gaps">
          <div class="sandbox__sidebar-title">💡 개선 제안</div>
          ${result.gaps.map(g => `<div class="sandbox__gap-item">${g}</div>`).join('')}
        </div>` : ''}

      <div class="sandbox__all-matches">
        <div class="sandbox__sidebar-title">전체 매칭 (${result.all_matches.length})</div>
        ${result.all_matches.map(m => `
          <div class="sandbox__match-row">
            <span>${m.rule_name}</span>
            <span class="sandbox__match-pct">${Math.round(m.match_score * 100)}%</span>
          </div>`).join('')}
      </div>
    `;
  }

  // ── 체인 뷰어 모드 ──────────────────────────────────────────────────────────

  /**
   * 분석실을 열고 해당 이벤트의 region 기반 cascade 체인 트리를 표시한다.
   * event_id는 UUID라 cascade link ID와 매칭 불가 — region_code로 체인 조회.
   */
  async _openWithChain(event_id, report) {
    // 열기
    if (!this._open) {
      this._el.classList.add('is-open');
      this._open = true;
      await this._loadCanvasList();
    }
    this._chainMode = true;

    // report에서 region 추출 (Stage 1)
    // report.stages는 {"1_facts": {...}, "2_sector": {...}, ...} 형태의 object
    const stagesObj = report.stages ?? {};
    const stage1 = stagesObj['1_facts'] ?? {};
    const region = stage1.region_code || 'unknown';
    const regionLabel = REGION_LABEL_KO[region] ?? region;
    const eventTitle  = stage1.title ?? event_id.slice(0, 8);

    // cascade 데이터가 없으면 새로 fetch
    if (!this._cascadeLinks.length) {
      try {
        const res  = await fetch('/api/cascade/links');
        const data = await res.json();
        this._cascadeLinks  = data.links ?? [];
        this._cascadeEvents = {};
        for (const ev of (data.events ?? [])) this._cascadeEvents[ev.id] = ev;
      } catch { /* cascade 없으면 빈 트리 */ }
    }

    // region 기반 체인 elements 빌드
    const elements = this._buildChainElementsForRegion(region, regionLabel);

    // 중앙 영역 전환
    const hint  = document.getElementById('sandbox-hint');
    const cyDiv = document.getElementById('sandbox-cy');
    const verifyBtn = document.getElementById('sandbox-verify-btn');

    if (!elements) {
      hint.textContent = `"${regionLabel}" 지역에서 발화된 Cascade 체인이 없습니다. (cascade 데이터 로드 필요)`;
      hint.style.display = 'flex';
      cyDiv.style.display = 'none';
      return;
    }

    hint.style.display = 'none';
    cyDiv.style.display = 'block';
    verifyBtn.disabled = true;

    // 타이틀 임시 변경
    const titleEl = this._el.querySelector('.sandbox__title');
    if (titleEl) titleEl.textContent = `🔗 체인 뷰어: ${regionLabel}`;

    this._initChainCy(elements);
    this._renderChainInfo(region, regionLabel, eventTitle);
  }

  /**
   * region_code 기반으로 Cytoscape elements를 빌드한다.
   * D1 링크 → D2 링크 → D3 링크 순으로 재귀 탐색.
   */
  _buildChainElementsForRegion(region, regionLabel) {
    // D1: evidence.region == region 인 링크
    const d1Links = this._cascadeLinks.filter(
      l => (l.depth == null || l.depth === 1) && l.evidence?.region === region
    );
    if (!d1Links.length) return null;

    // link.id → link 인덱스 (parent_link_id 역참조)
    const linkById = new Map(this._cascadeLinks.map(l => [l.id, l]));

    const nodeSet  = new Set();
    const elements = [];

    // 루트 노드: 분쟁 지역
    const rootId = `region-${region}`;
    elements.push({ data: { id: rootId, label: regionLabel, type: 'conflict', depth: 0 } });
    nodeSet.add(rootId);

    const addLinks = (parentNodeId, links, depth) => {
      for (const link of links) {
        const ticker = link.evidence?.ticker;
        if (!ticker) continue;

        const pct       = link.evidence?.pct_change ?? 0;
        const tickLabel = TICKER_LABEL_KO[ticker] ?? ticker;
        const sign      = pct >= 0 ? '+' : '';
        const nodeLabel = `${tickLabel}\n${sign}${pct.toFixed(1)}%`;
        // 같은 ticker가 여러 번 나와도 link.id로 구분
        const nodeId    = `ticker-${link.id}`;

        if (!nodeSet.has(nodeId)) {
          elements.push({ data: { id: nodeId, label: nodeLabel, type: 'market', depth } });
          nodeSet.add(nodeId);
        }

        // 인과 엣지
        const ruleShort = (link.rule_id ?? '').replace(/_/g, ' ').slice(0, 20);
        elements.push({ data: { source: parentNodeId, target: nodeId, label: ruleShort, depth } });

        // 재귀: 자식 체인 링크
        const children = this._cascadeLinks.filter(l => l.parent_link_id === link.id);
        if (children.length) addLinks(nodeId, children, depth + 1);
      }
    };

    addLinks(rootId, d1Links, 1);
    return elements;
  }

  /** 체인 전용 Cytoscape 초기화 (dagre 상하 트리) */
  _initChainCy(elements) {
    const container = document.getElementById('sandbox-cy');
    this._cy?.destroy();

    this._cy = cytoscape({
      container,
      elements,
      style: [
        {
          selector: 'node[type = "conflict"]',
          style: {
            'background-color': DEPTH_STYLE[0].bg,
            'border-color':     DEPTH_STYLE[0].border,
            'border-width': 2, shape: DEPTH_STYLE[0].shape,
            label: 'data(label)', color: '#fff',
            'font-size': 11, 'font-weight': 'bold',
            'text-valign': 'center', 'text-halign': 'center',
            'text-wrap': 'wrap', 'text-max-width': '80px',
            width: 100, height: 56,
          },
        },
        {
          selector: 'node[type = "market"][depth = 1]',
          style: {
            'background-color': DEPTH_STYLE[1].bg, 'border-color': DEPTH_STYLE[1].border,
            'border-width': 2, shape: DEPTH_STYLE[1].shape,
            label: 'data(label)', color: '#fff', 'font-size': 10,
            'text-valign': 'center', 'text-halign': 'center',
            'text-wrap': 'wrap', 'text-max-width': '70px',
            width: 84, height: 56,
          },
        },
        {
          selector: 'node[type = "market"][depth = 2]',
          style: {
            'background-color': DEPTH_STYLE[2].bg, 'border-color': DEPTH_STYLE[2].border,
            'border-width': 2, shape: DEPTH_STYLE[2].shape,
            label: 'data(label)', color: '#ffe566', 'font-size': 10,
            'text-valign': 'center', 'text-halign': 'center',
            'text-wrap': 'wrap', 'text-max-width': '70px',
            width: 80, height: 52,
          },
        },
        {
          selector: 'node[type = "market"][depth = 3]',
          style: {
            'background-color': DEPTH_STYLE[3].bg, 'border-color': DEPTH_STYLE[3].border,
            'border-width': 2, shape: DEPTH_STYLE[3].shape,
            label: 'data(label)', color: '#ff9800', 'font-size': 10,
            'text-valign': 'center', 'text-halign': 'center',
            'text-wrap': 'wrap', 'text-max-width': '70px',
            width: 80, height: 52,
          },
        },
        {
          selector: 'edge[depth = 1]',
          style: {
            'line-color': '#ffe566', 'target-arrow-color': '#ffe566',
            'target-arrow-shape': 'triangle', width: 2,
            'curve-style': 'bezier', label: 'data(label)',
            'font-size': 8, color: '#aaa',
          },
        },
        {
          selector: 'edge[depth >= 2]',
          style: {
            'line-color': '#ff9800', 'target-arrow-color': '#ff9800',
            'target-arrow-shape': 'triangle', width: 1.5,
            'curve-style': 'bezier', 'line-style': 'dashed',
            label: 'data(label)', 'font-size': 8, color: '#888',
          },
        },
      ],
      layout: {
        name:      'dagre',
        rankDir:   'TB',   // 상→하 트리
        nodeSep:   40,
        rankSep:   70,
        animate:   true,
        animationDuration: 400,
      },
      wheelSensitivity: 0.1,
    });
  }

  /** 우측 패널에 체인 요약 정보 표시 */
  _renderChainInfo(region, regionLabel, eventTitle) {
    const d1 = this._cascadeLinks.filter(l => (l.depth == null || l.depth === 1) && l.evidence?.region === region);
    const d2 = this._cascadeLinks.filter(l => l.depth === 2 && d1.some(p => p.id === l.parent_link_id));
    const d3 = this._cascadeLinks.filter(l => l.depth === 3 && d2.some(p => p.id === l.parent_link_id));

    const emptyEl = document.getElementById('sandbox-result-empty');
    const bodyEl  = document.getElementById('sandbox-result-body');
    if (!emptyEl || !bodyEl) return;

    emptyEl.style.display = 'none';
    bodyEl.style.display  = 'block';

    const mkRows = (links) => links.map(l => {
      const ticker = l.evidence?.ticker ?? '?';
      const pct    = l.evidence?.pct_change ?? 0;
      const sign   = pct >= 0 ? '↑' : '↓';
      const score  = Math.round((l.correlation_score ?? 0) * 100);
      return `<div class="sandbox__chain-row">
        <span class="sandbox__chain-ticker">${ticker}</span>
        <span class="sandbox__chain-pct ${pct>=0?'up':'dn'}">${sign}${Math.abs(pct).toFixed(1)}%</span>
        <span class="sandbox__chain-score">${score}%</span>
      </div>`;
    }).join('');

    bodyEl.innerHTML = `
      <div class="sandbox__chain-info">
        <div class="sandbox__chain-title">📍 ${regionLabel}</div>
        <div class="sandbox__chain-sub">이벤트: ${eventTitle}</div>

        ${d1.length ? `<div class="sandbox__chain-depth-label">D1 — 직접 반응 (${d1.length}개)</div>
          <div class="sandbox__chain-rows">${mkRows(d1)}</div>` : ''}

        ${d2.length ? `<div class="sandbox__chain-depth-label">D2 — 2차 전이 (${d2.length}개)</div>
          <div class="sandbox__chain-rows">${mkRows(d2)}</div>` : ''}

        ${d3.length ? `<div class="sandbox__chain-depth-label">D3 — 3차 파급 (${d3.length}개)</div>
          <div class="sandbox__chain-rows">${mkRows(d3)}</div>` : ''}

        ${(!d1.length && !d2.length && !d3.length) ? '<div style="color:#888;font-size:12px">현재 기간 발화 없음</div>' : ''}

        <div class="sandbox__chain-note">
          💡 이론: Weaponized Interdependence →<br>
          Supply Chain Contagion → Military-Industrial Complex
        </div>
      </div>
    `;
  }
}
