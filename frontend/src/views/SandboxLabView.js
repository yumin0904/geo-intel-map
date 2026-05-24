/**
 * SandboxLabView — 분석실(Sandbox Lab) 풀스크린 오버레이.
 *
 * 레이아웃: 좌측 20% 캔버스 목록 | 중앙 60% Cytoscape | 우측 20% 검증 결과
 * 열기/닫기: EventBus 'sandbox:toggle' 또는 ✕ 버튼
 *
 * cytoscape, cytoscape-dagre는 index.html에서 전역 로드됨
 */

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
    this._bus.on('sandbox:toggle', () => this._open ? this.close() : this.open());
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
}
