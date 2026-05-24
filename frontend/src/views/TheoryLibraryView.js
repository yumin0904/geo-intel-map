/**
 * frontend/src/views/TheoryLibraryView.js
 *
 * 이론 라이브러리 풀스크린 오버레이 (Phase 3).
 *
 * 레이아웃:
 *   좌측 30% — 섹터 탭 + 검색 + 이론 카드 목록
 *   우측 70% — 선택된 이론 상세 (marked.js 본문 + AI 스트리밍)
 *
 * 열기/닫기: EventBus 'library:toggle' 또는 ✕ 버튼
 */

import { api }                        from '../services/api.js';
import { store, setState }            from '../core/StateStore.js';

const SECTOR_LABELS = {
  all:          '전체',
  maritime:     '해양',
  energy:       '에너지',
  techno:       '기술',
  indo_pacific: '인태',
  gray_zone:    '회색지대',
};

const ASSET_TYPE_LABELS = {
  all:        '전체',
  theory:     '이론',
  case_study: '사례',
  profile:    '프로필',
  norm:       '법·제재',
};

const ERA_LABELS = {
  all:        '전체',
  cold_war:   '냉전',
  unipolar:   '단극',
  multipolar: '다극',
};

const REGION_LABELS = {
  all:              '전체 지역',
  taiwan_strait:    '대만해협',
  south_china_sea:  '남중국해',
  hormuz:           '호르무즈',
  bab_el_mandeb:    '바브엘만데브',
  suez:             '수에즈',
  malacca:          '말라카',
  ukraine:          '우크라이나',
  middle_east:      '중동',
  korean_peninsula: '한반도',
};

const SECTOR_COLORS = {
  maritime:     '#4a9eff',
  energy:       '#ff9a3c',
  techno:       '#c77dff',
  indo_pacific: '#4aff91',
  gray_zone:    '#ffd700',
};

export class TheoryLibraryView {
  constructor(map, eventBus, layerManager) {
    this._map    = map;
    this._bus    = eventBus;
    this._lm     = layerManager;
    this._el     = null;
    this._open   = false;
    this._loaded = false;
    this._activeId    = null;   // 현재 선택된 theory_id
    this._aiAbortCtrl = null;

    this._mount();
    this._bindEvents();
  }

  // ── 마운트 ───────────────────────────────────────────────────────────────

  _mount() {
    this._el = document.getElementById('library-panel');
    if (!this._el) { console.error('[TheoryLibraryView] #library-panel 없음'); return; }
    this._el.innerHTML = this._template();
    this._bindPanelEvents();
  }

  _template() {
    const sectorTabs = Object.entries(SECTOR_LABELS)
      .map(([k, l]) =>
        `<button class="lib-sector-tab${k === 'all' ? ' is-active' : ''}" data-sector="${k}">${l}</button>`
      ).join('');

    const assetOpts = Object.entries(ASSET_TYPE_LABELS)
      .map(([k, l]) => `<option value="${k}">${l}</option>`).join('');

    const eraOpts = Object.entries(ERA_LABELS)
      .map(([k, l]) => `<option value="${k}">${l}</option>`).join('');

    const regionOpts = Object.entries(REGION_LABELS)
      .map(([k, l]) => `<option value="${k}">${l}</option>`).join('');

    return `
      <div class="lib__header">
        <span class="lib__header-title">📚 라이브러리</span>
        <button class="lib__close" title="닫기">✕</button>
      </div>

      <div class="lib__body">

        <!-- 좌측 30%: 필터 + 목록 -->
        <aside class="lib__sidebar">
          <div class="lib-search">
            <input type="search" class="lib-search__input" placeholder="이론 / 학자 검색…" />
          </div>
          <div class="lib-sectors">${sectorTabs}</div>
          <div class="lib-filters">
            <select class="lib-filter-select" data-filter="assetType">
              ${assetOpts}
            </select>
            <select class="lib-filter-select" data-filter="era">
              ${eraOpts}
            </select>
            <select class="lib-filter-select" data-filter="region">
              ${regionOpts}
            </select>
          </div>
          <div class="lib-list"></div>
        </aside>

        <!-- 우측 70%: 상세 -->
        <main class="lib__detail">
          <div class="lib__detail-placeholder">← 좌측에서 이론을 선택하세요</div>
          <div class="lib__detail-content" style="display:none">
            <div class="lib__detail-header">
              <div class="lib__detail-title-row">
                <span class="lib-card__sector lib__detail-sector"></span>
                <h2 class="lib__detail-title"></h2>
                <button class="lib__focus-btn">🗺 지도에서 보기</button>
              </div>
              <div class="lib__detail-meta"></div>
            </div>
            <div class="lib__detail-body">
              <div class="lib-detail-md"></div>
            </div>
            <div class="lib__detail-footer">
              <button class="lib-ai-btn">🤖 AI로 더 알아보기</button>
              <div class="lib-ai-result"></div>
            </div>
          </div>
        </main>

      </div>
    `;
  }

  // ── 이벤트 바인딩 ────────────────────────────────────────────────────────

  _bindPanelEvents() {
    this._el.querySelector('.lib__close')
      .addEventListener('click', () => this.close());

    // 섹터 탭
    this._el.querySelectorAll('.lib-sector-tab').forEach(btn => {
      btn.addEventListener('click', () => {
        this._el.querySelectorAll('.lib-sector-tab').forEach(b => b.classList.remove('is-active'));
        btn.classList.add('is-active');
        setState('library', { sectorFilter: btn.dataset.sector, searchQuery: '' });
        this._el.querySelector('.lib-search__input').value = '';
        this._renderList();
      });
    });

    // 검색 debounce
    let _t;
    this._el.querySelector('.lib-search__input').addEventListener('input', e => {
      clearTimeout(_t);
      _t = setTimeout(() => {
        setState('library', { searchQuery: e.target.value.trim() });
        this._renderList();
      }, 300);
    });

    // 유형·시대·지역 드롭다운 필터
    this._el.querySelectorAll('.lib-filter-select').forEach(sel => {
      sel.addEventListener('change', () => {
        const key = sel.dataset.filter;         // assetType | era | region
        setState('library', { [`${key}Filter`]: sel.value });
        this._renderList();
      });
    });

    // AI 버튼
    this._el.querySelector('.lib-ai-btn')
      .addEventListener('click', () => {
        const { theories } = store.getState('library');
        const theory = (theories || []).find(t => t.theory_id === this._activeId);
        if (theory) this._fetchAiExplain(theory);
      });

    // 지도에서 보기
    this._el.querySelector('.lib__focus-btn')
      .addEventListener('click', () => {
        const { theories } = store.getState('library');
        const theory = (theories || []).find(t => t.theory_id === this._activeId);
        if (theory) this._focusMap(theory);
      });
  }

  _bindEvents() {
    this._bus.on('library:toggle', () => this._open ? this.close() : this.open());
  }

  // ── 열기/닫기 ────────────────────────────────────────────────────────────

  async open() {
    if (!this._loaded) await this._loadData();
    this._el.classList.add('is-open');
    this._open = true;
    this._renderList();
  }

  close() {
    this._el.classList.remove('is-open');
    this._open = false;
    this._cancelAiStream();
  }

  // ── 데이터 로드 ──────────────────────────────────────────────────────────

  async _loadData() {
    setState('library', { loading: true });
    try {
      const [theories, regionIndex] = await Promise.all([
        api.get('/api/library/items'),
        api.get('/api/library/region-index'),
      ]);
      setState('library', { theories, regionIndex, loading: false });
      this._loaded = true;
    } catch (err) {
      console.error('[TheoryLibraryView] 로드 실패:', err);
      setState('library', { loading: false });
    }
  }

  // ── 목록 렌더링 ──────────────────────────────────────────────────────────

  _renderList() {
    const list = this._el.querySelector('.lib-list');
    if (!list) return;
    const {
      theories, sectorFilter, searchQuery, loading,
      assetTypeFilter, eraFilter, regionFilter,
    } = store.getState('library');

    if (loading) { list.innerHTML = '<div class="lib-loading">로딩 중…</div>'; return; }

    const filtered = this._filter(
      theories || [], sectorFilter, searchQuery,
      assetTypeFilter, eraFilter, regionFilter,
    );
    if (!filtered.length) { list.innerHTML = '<div class="lib-empty">이론이 없습니다.</div>'; return; }

    list.innerHTML = filtered.map(t => this._cardHTML(t)).join('');

    list.querySelectorAll('.lib-card').forEach(card => {
      card.addEventListener('click', () => {
        const theory = filtered.find(t => t.theory_id === card.dataset.id);
        if (theory) this._selectTheory(theory);
      });
    });
  }

  _filter(theories, sector, query, assetType, era, region) {
    let r = theories;
    if (sector    && sector    !== 'all') r = r.filter(t => t.sector_tag  === sector);
    if (assetType && assetType !== 'all') r = r.filter(t => t.asset_type  === assetType);
    if (era       && era       !== 'all') r = r.filter(t => t.era         === era);
    if (region    && region    !== 'all') r = r.filter(t => (t.related_regions || []).includes(region));
    if (query) {
      const q = query.toLowerCase();
      r = r.filter(t =>
        t.display_name.toLowerCase().includes(q) ||
        (t.summary || '').toLowerCase().includes(q) ||
        (t.theorists || []).some(th => th.toLowerCase().includes(q))
      );
    }
    return r;
  }

  _cardHTML(theory) {
    const color    = SECTOR_COLORS[theory.sector_tag] || '#888';
    const label    = SECTOR_LABELS[theory.sector_tag] || theory.sector_tag;
    const theorists = (theory.theorists || []).slice(0, 2).join(', ') || '—';
    const year     = theory.year ? ` (${theory.year})` : '';
    const summary  = theory.summary
      ? `<p class="lib-card__summary">${theory.summary}</p>` : '';
    const isActive = theory.theory_id === this._activeId ? ' is-active' : '';

    return `
      <div class="lib-card${isActive}" data-id="${theory.theory_id}">
        <div class="lib-card__header">
          <span class="lib-card__sector" style="--sector-color:${color}">${label}</span>
          <span class="lib-card__name">${theory.display_name}</span>
        </div>
        <div class="lib-card__meta">${theorists}${year}</div>
        ${summary}
      </div>
    `;
  }

  // ── 이론 선택 → 우측 상세 렌더링 ────────────────────────────────────────

  async _selectTheory(theory) {
    this._activeId = theory.theory_id;
    this._cancelAiStream();

    // 카드 active 상태 갱신
    this._el.querySelectorAll('.lib-card').forEach(c => {
      c.classList.toggle('is-active', c.dataset.id === this._activeId);
    });

    // 우측 패널 표시 + 헤더 즉시 업데이트
    const placeholder = this._el.querySelector('.lib__detail-placeholder');
    const content     = this._el.querySelector('.lib__detail-content');
    placeholder.style.display = 'none';
    content.style.display = 'flex';

    const color  = SECTOR_COLORS[theory.sector_tag] || '#888';
    const label  = SECTOR_LABELS[theory.sector_tag] || theory.sector_tag;
    const theorists = (theory.theorists || []).join(', ') || '—';
    const year   = theory.year ? ` · ${theory.year}` : '';

    const sectorEl = this._el.querySelector('.lib__detail-sector');
    sectorEl.textContent = label;
    sectorEl.style.setProperty('--sector-color', color);
    this._el.querySelector('.lib__detail-title').textContent = theory.display_name;
    this._el.querySelector('.lib__detail-meta').textContent  = `${theorists}${year}`;

    // AI 결과 초기화
    this._el.querySelector('.lib-ai-result').innerHTML = '';
    const aiBtn = this._el.querySelector('.lib-ai-btn');
    aiBtn.disabled = false;
    aiBtn.textContent = '🤖 AI로 더 알아보기';

    // body가 없으면 API에서 로드
    let fullTheory = theory;
    if (!theory.body) {
      this._el.querySelector('.lib-detail-md').innerHTML =
        '<p style="color:#8b949e;font-size:12px">본문 로딩 중…</p>';
      try {
        fullTheory = await api.get(`/api/library/theories/${theory.theory_id}`);
        // 캐시: StateStore theories 배열의 해당 항목 갱신
        const { theories } = store.getState('library');
        const idx = theories.findIndex(t => t.theory_id === theory.theory_id);
        if (idx >= 0) theories[idx] = fullTheory;
      } catch (e) {
        this._el.querySelector('.lib-detail-md').innerHTML =
          '<p style="color:#f85149;font-size:12px">본문 로드 실패</p>';
        return;
      }
    }

    // marked.js 렌더링
    const bodyHtml = fullTheory.body
      ? (window.marked ? window.marked.parse(fullTheory.body) : `<pre style="white-space:pre-wrap;font-size:12px">${fullTheory.body}</pre>`)
      : '<p style="color:#8b949e;font-size:12px">본문이 없습니다. POST /api/library/reindex 실행 후 새로고침하세요.</p>';

    this._el.querySelector('.lib-detail-md').innerHTML = bodyHtml;
    // 본문 스크롤 최상단으로
    this._el.querySelector('.lib__detail-body').scrollTop = 0;
  }

  // ── AI 스트리밍 ──────────────────────────────────────────────────────────

  async _fetchAiExplain(theory) {
    const aiResult = this._el.querySelector('.lib-ai-result');
    const aiBtn    = this._el.querySelector('.lib-ai-btn');

    aiBtn.disabled = true;
    aiBtn.textContent = '⏳ 생성 중…';
    aiResult.innerHTML = '<div class="lib-ai-loading">Gemini가 분석 중입니다…</div>';

    this._aiAbortCtrl = new AbortController();
    let accumulated = '';
    let isCached    = false;

    try {
      const res = await fetch(
        `${api.BASE_URL}/api/library/theories/${theory.theory_id}/ai-explain`,
        { method: 'POST', signal: this._aiAbortCtrl.signal }
      );
      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const reader  = res.body.getReader();
      const decoder = new TextDecoder();
      let   buf     = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buf += decoder.decode(value, { stream: true });
        const lines = buf.split('\n');
        buf = lines.pop();

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          let evt;
          try { evt = JSON.parse(line.slice(6)); } catch { continue; }

          if (evt.text) {
            accumulated += evt.text;
            isCached = !!evt.cached;
            aiResult.innerHTML = this._wrapAiResult(
              window.marked ? window.marked.parse(accumulated) : accumulated,
              false, isCached
            );
            aiResult.scrollTop = aiResult.scrollHeight;
          }
          if (evt.done) break;
        }
      }

      aiResult.innerHTML = this._wrapAiResult(
        window.marked ? window.marked.parse(accumulated) : accumulated,
        true, isCached
      );
      aiBtn.textContent = '✅ 완료 (재생성)';
      aiBtn.disabled = false;

    } catch (err) {
      if (err.name === 'AbortError') return;
      aiResult.innerHTML = `<p class="lib-ai-error">오류: ${err.message}</p>`;
      aiBtn.textContent = '🤖 AI로 더 알아보기';
      aiBtn.disabled = false;
    }
  }

  _wrapAiResult(html, isDone, isCached) {
    const badge  = isCached
      ? '<span class="lib-ai-badge lib-ai-badge--cached">캐시</span>'
      : '<span class="lib-ai-badge lib-ai-badge--gemini">Gemini 1.5 Flash</span>';
    const cursor = isDone ? '' : '<span class="lib-ai-cursor">▍</span>';
    return `
      <div class="lib-ai-header">${badge}</div>
      <div class="lib-ai-content">${html}${cursor}</div>
    `;
  }

  _cancelAiStream() {
    if (this._aiAbortCtrl) { this._aiAbortCtrl.abort(); this._aiAbortCtrl = null; }
  }

  // ── 지도 포커스 ──────────────────────────────────────────────────────────

  _focusMap(theory) {
    const focus = theory.map_focus;
    if (!focus) return;
    this._map.flyTo([focus.lat, focus.lon], focus.zoom, { duration: 1.2 });
    (focus.layers || []).forEach(id => this._lm.setVisible(id, true));
    this._bus.emit('library:focus', { theory_id: theory.theory_id, map_focus: focus });
  }
}
