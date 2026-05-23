/**
 * frontend/src/views/TheoryLibraryView.js
 *
 * 이론 라이브러리 패널 (Phase 3 학습 도구).
 *
 * - 우측 슬라이드인 패널 (360px)
 * - 5대 섹터 탭 필터 + 검색
 * - 이론 카드 목록 → "지도에서 보기" 버튼 클릭 시 library:focus 이벤트 emit
 * - StateStore.library 슬라이스와 양방향 동기화
 *
 * 열기/닫기: EventBus 'library:toggle' 이벤트 또는 close 버튼
 */

import { api }                   from '../services/api.js';
import { store, setState, subscribe } from '../core/StateStore.js';

// 5대 섹터 레이블 (CLAUDE.md 1-5번 섹터)
const SECTOR_LABELS = {
  all:          '전체',
  maritime:     '해양',
  energy:       '에너지',
  techno:       '기술',
  indo_pacific: '인태',
  gray_zone:    '회색지대',
};

// 섹터별 색상 (CSS 변수와 연동)
const SECTOR_COLORS = {
  maritime:     '#4a9eff',
  energy:       '#ff9a3c',
  techno:       '#c77dff',
  indo_pacific: '#4aff91',
  gray_zone:    '#ffd700',
};

export class TheoryLibraryView {
  /**
   * @param {L.Map}    map       Leaflet 지도 인스턴스 (flyTo 호출용)
   * @param {EventBus} eventBus
   * @param {LayerManager} layerManager  레이어 활성화용
   */
  constructor(map, eventBus, layerManager) {
    this._map   = map;
    this._bus   = eventBus;
    this._lm    = layerManager;
    this._el    = null;
    this._open  = false;
    this._loaded = false; // 최초 API 호출 여부 (lazy load)

    this._mount();
    this._bindEvents();
  }

  // ── 마운트 ────────────────────────────────────────────────────────────────

  _mount() {
    this._el = document.getElementById('library-panel');
    if (!this._el) {
      console.error('[TheoryLibraryView] #library-panel 요소 없음');
      return;
    }
    this._el.innerHTML = this._template();
    this._bindPanelEvents();
  }

  _template() {
    const sectorTabs = Object.entries(SECTOR_LABELS)
      .map(([key, label]) =>
        `<button class="lib-sector-tab${key === 'all' ? ' is-active' : ''}" data-sector="${key}">${label}</button>`
      ).join('');

    return `
      <div class="lib-header">
        <span class="lib-header__title">📚 이론 라이브러리</span>
        <button class="lib-close" title="닫기">✕</button>
      </div>
      <div class="lib-search">
        <input type="search" class="lib-search__input" placeholder="이론 검색…" />
      </div>
      <div class="lib-sectors">${sectorTabs}</div>
      <div class="lib-list"></div>
    `;
  }

  // ── 이벤트 바인딩 ─────────────────────────────────────────────────────────

  _bindPanelEvents() {
    // 닫기 버튼
    this._el.querySelector('.lib-close').addEventListener('click', () => this.close());

    // 섹터 탭 필터
    this._el.querySelectorAll('.lib-sector-tab').forEach(btn => {
      btn.addEventListener('click', () => {
        this._el.querySelectorAll('.lib-sector-tab').forEach(b => b.classList.remove('is-active'));
        btn.classList.add('is-active');
        setState('library', { sectorFilter: btn.dataset.sector, searchQuery: '' });
        this._el.querySelector('.lib-search__input').value = '';
        this._render();
      });
    });

    // 검색 (300ms debounce — 클라이언트 필터)
    let _debounce;
    this._el.querySelector('.lib-search__input').addEventListener('input', e => {
      clearTimeout(_debounce);
      _debounce = setTimeout(() => {
        setState('library', { searchQuery: e.target.value.trim() });
        this._render();
      }, 300);
    });
  }

  _bindEvents() {
    // LayerPanel에서 emit하는 library:toggle
    this._bus.on('library:toggle', () => {
      this._open ? this.close() : this.open();
    });
  }

  // ── 패널 열기/닫기 ────────────────────────────────────────────────────────

  async open() {
    if (!this._loaded) await this._loadData();
    this._el.classList.add('is-open');
    this._open = true;
    this._render();
  }

  close() {
    this._el.classList.remove('is-open');
    this._open = false;
  }

  // ── 데이터 로드 ───────────────────────────────────────────────────────────

  async _loadData() {
    setState('library', { loading: true });
    try {
      const [theories, regionIndex] = await Promise.all([
        api.get('/api/library/theories'),
        api.get('/api/library/region-index'),
      ]);
      setState('library', { theories, regionIndex, loading: false });
      this._loaded = true;
    } catch (err) {
      console.error('[TheoryLibraryView] 데이터 로드 실패:', err);
      setState('library', { loading: false });
    }
  }

  // ── 렌더링 ────────────────────────────────────────────────────────────────

  _render() {
    const list = this._el.querySelector('.lib-list');
    if (!list) return;

    const { theories, sectorFilter, searchQuery, loading } = store.getState('library');

    if (loading) {
      list.innerHTML = '<div class="lib-loading">로딩 중…</div>';
      return;
    }

    const filtered = this._filter(theories, sectorFilter, searchQuery);

    if (filtered.length === 0) {
      list.innerHTML = '<div class="lib-empty">이론이 없습니다.</div>';
      return;
    }

    list.innerHTML = filtered.map(t => this._cardHTML(t)).join('');

    // "지도에서 보기" 버튼 이벤트 위임
    list.querySelectorAll('.lib-card__focus-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const theory = filtered.find(t => t.theory_id === btn.dataset.id);
        if (theory) this._focusMap(theory);
      });
    });
  }

  _filter(theories, sector, query) {
    let result = theories;
    if (sector && sector !== 'all') {
      result = result.filter(t => t.sector_tag === sector);
    }
    if (query) {
      const q = query.toLowerCase();
      result = result.filter(t =>
        t.display_name.toLowerCase().includes(q) ||
        t.summary.toLowerCase().includes(q) ||
        (t.theorists || []).some(th => th.toLowerCase().includes(q))
      );
    }
    return result;
  }

  _cardHTML(theory) {
    const color = SECTOR_COLORS[theory.sector_tag] || '#888';
    const label = SECTOR_LABELS[theory.sector_tag] || theory.sector_tag;
    const theorists = (theory.theorists || []).join(', ') || '—';
    const year = theory.year ? ` (${theory.year})` : '';
    const summary = theory.summary
      ? `<p class="lib-card__summary">${theory.summary}</p>`
      : '';
    const layers = (theory.map_focus?.layers || []).join(', ');

    return `
      <div class="lib-card">
        <div class="lib-card__header">
          <span class="lib-card__sector" style="--sector-color:${color}">${label}</span>
          <span class="lib-card__name">${theory.display_name}</span>
        </div>
        <div class="lib-card__meta">${theorists}${year}</div>
        ${summary}
        ${layers ? `<div class="lib-card__layers">🗂 ${layers}</div>` : ''}
        <button class="lib-card__focus-btn" data-id="${theory.theory_id}" title="해당 지역으로 지도 이동">
          🗺 지도에서 보기
        </button>
      </div>
    `;
  }

  // ── 지도 포커스 ───────────────────────────────────────────────────────────

  _focusMap(theory) {
    const focus = theory.map_focus;
    if (!focus) return;

    // 지도 이동 (애니메이션)
    this._map.flyTo([focus.lat, focus.lon], focus.zoom, { duration: 1.2 });

    // 권장 레이어 활성화
    (focus.layers || []).forEach(layerId => {
      this._lm.setVisible(layerId, true);
    });

    // 다른 뷰도 알 수 있도록 이벤트 emit
    this._bus.emit('library:focus', { theory_id: theory.theory_id, map_focus: focus });
  }
}
