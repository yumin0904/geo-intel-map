/**
 * frontend/src/views/TheoryLibraryView.js
 *
 * 이론 라이브러리 풀스크린 오버레이 (Phase 3).
 *
 * 레이아웃:
 *   좌측 30% — 칩 필터 3행 + 검색 + 이론 카드 목록
 *   우측 70% — 선택된 이론 상세 (marked.js 본문 + AI 스트리밍)
 *
 * 필터 칩 (5행, 행 내 단일 선택, AND 조건):
 *   1행 용도:  전체 / 🔍개념 / 📚사례 / 📊데이터 / ⚖️규범
 *   2행 지역:  전체 / 인도-태평양 / 중동 / 유럽 / 아프리카 / 전지구
 *   3행 시대:  전체 / 냉전 / 탈냉전 / 미중경쟁 / 현재
 *   4행 분석수준: 전체 / 체계 / 국가 / 비국가  (Waltz 3수준, §15)
 *   5행 권력수단: 전체 / 외교 / 정보 / 군사 / 경제  (DIME 프레임워크, §15)
 *
 * 열기/닫기: EventBus 'library:toggle' 또는 ✕ 버튼
 */

import { api }             from '../services/api.js';
import { store, setState } from '../core/StateStore.js';

// ── 필터 칩 정의 ──────────────────────────────────────────────────────────────

const USE_CASE_CHIPS = [
  { key: 'all',        label: '전체',    icon: '' },
  { key: 'concept',    label: '개념',    icon: '🔍' },
  { key: 'case_study', label: '사례',    icon: '📚' },
  { key: 'briefing',   label: '브리핑',  icon: '📋' },
  { key: 'norm',       label: '규범',    icon: '⚖️' },
  { key: 'data',       label: '데이터',  icon: '📊' },
];

const REGION_CHIPS = [
  { key: 'all',          label: '전체' },
  { key: 'indo_pacific', label: '인도-태평양' },
  { key: 'middle_east',  label: '중동' },
  { key: 'europe',       label: '유럽' },
  { key: 'africa',       label: '아프리카' },
  { key: 'global',       label: '전지구' },
];

// temporal_era: 7대 축 §15 (cold_war/post_cold/us_china_rivalry/hot)
const ERA_CHIPS = [
  { key: 'all',               label: '전체' },
  { key: 'cold_war',          label: '냉전 (1947-91)' },
  { key: 'post_cold',         label: '탈냉전 (91-17)' },
  { key: 'us_china_rivalry',  label: '미중경쟁 (17-)' },
];

// level_of_analysis: Waltz 3수준 이론 (§15)
const LEVEL_CHIPS = [
  { key: 'all',           label: '전체' },
  { key: 'systemic',      label: '체계' },
  { key: 'state_domestic',label: '국가' },
  { key: 'non_state',     label: '비국가' },
];

// instrument_of_power: DIME 프레임워크 (§15)
const INSTRUMENT_CHIPS = [
  { key: 'all',           label: '전체' },
  { key: 'diplomatic',    label: '외교' },
  { key: 'informational', label: '정보' },
  { key: 'military',      label: '군사' },
  { key: 'economic',      label: '경제' },
];

// 지역 코드 → 클러스터 매핑
const REGION_CLUSTER_CODES = {
  indo_pacific: [
    'taiwan_strait', 'south_china_sea', 'east_china_sea', 'malacca',
    'korean_strait', 'korean_peninsula', 'pacific', 'indo_pacific',
    'bay_of_bengal', 'philippine_sea', 'senkaku',
  ],
  middle_east: [
    'hormuz', 'bab_el_mandeb', 'suez', 'persian_gulf',
    'red_sea', 'middle_east', 'strait_of_hormuz', 'arabian_sea',
  ],
  europe: [
    'ukraine', 'baltic', 'black_sea', 'europe', 'arctic', 'caspian', 'north_sea',
  ],
  africa: [
    'gulf_of_guinea', 'horn_of_africa', 'sahel', 'somalia', 'africa',
    'caribbean', 'mozambique',
  ],
};

const SECTOR_COLORS = {
  maritime:     '#4a9eff',
  energy:       '#ff9a3c',
  techno:       '#c77dff',
  indo_pacific: '#4aff91',
  gray_zone:    '#ffd700',
  cyber:        '#ff6b9d',
};

const SECTOR_LABELS = {
  maritime:     '해양',
  energy:       '에너지',
  techno:       '기술',
  indo_pacific: '인태',
  gray_zone:    '회색지대',
  cyber:        '사이버',
};

// 브리핑 섹터 표시 순서
const BRIEFING_SECTOR_ORDER = [
  'indo_pacific', 'cyber', 'maritime', 'techno', 'gray_zone', 'energy',
];

// 출처 기관 필터
const SOURCE_ORG_CHIPS = [
  { key: 'all',              label: '전체' },
  { key: 'War on the Rocks', label: 'WotR' },
  { key: 'RAND',             label: 'RAND' },
  { key: 'CSIS',             label: 'CSIS' },
  { key: 'INSS',             label: 'INSS' },
  { key: 'ECFR',             label: 'ECFR' },
  { key: 'Foreign Affairs',  label: 'FA' },
];

// ── 필터 헬퍼 ────────────────────────────────────────────────────────────────

function _matchesUseCase(theory, key) {
  if (key === 'all') return true;
  return (theory.use_case || theory.asset_type || 'concept') === key;
}

function _matchesRegion(theory, key) {
  if (key === 'all') return true;
  const regions = theory.related_regions || [];
  if (key === 'global') {
    if (regions.length === 0) return true;
    const matchCount = Object.values(REGION_CLUSTER_CODES)
      .filter(codes => regions.some(r => codes.includes(r))).length;
    return matchCount >= 2;
  }
  const codes = REGION_CLUSTER_CODES[key] || [];
  return regions.some(r => codes.includes(r));
}

function _matchesEra(theory, key) {
  if (key === 'all') return true;
  // temporal_era 우선, fallback: 레거시 era 필드 매핑
  const te = theory.temporal_era;
  if (te) return te === key;
  // 레거시 era → temporal_era 근사 매핑 (DB 재인덱싱 전 호환)
  if (key === 'cold_war')         return theory.era === 'cold_war';
  if (key === 'post_cold')        return theory.era === 'unipolar';
  if (key === 'us_china_rivalry') return theory.era === 'multipolar';
  return false;
}

function _matchesLevel(theory, key) {
  if (key === 'all') return true;
  return theory.level_of_analysis === key;
}

function _matchesInstrument(theory, key) {
  if (key === 'all') return true;
  return theory.instrument_of_power === key;
}

// ── 뷰 클래스 ────────────────────────────────────────────────────────────────

export class TheoryLibraryView {
  constructor(map, eventBus, layerManager) {
    this._map    = map;
    this._bus    = eventBus;
    this._lm     = layerManager;
    this._el     = null;
    this._open   = false;
    this._loaded = false;
    this._activeId    = null;
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
    const useCaseChips = USE_CASE_CHIPS.map(({ key, label, icon }) =>
      `<button class="lib-chip${key === 'all' ? ' is-active' : ''}" data-filter="useCase" data-value="${key}">${icon ? icon + ' ' : ''}${label}</button>`
    ).join('');

    const regionChips = REGION_CHIPS.map(({ key, label }) =>
      `<button class="lib-chip${key === 'all' ? ' is-active' : ''}" data-filter="region" data-value="${key}">${label}</button>`
    ).join('');

    const eraChips = ERA_CHIPS.map(({ key, label }) =>
      `<button class="lib-chip${key === 'all' ? ' is-active' : ''}" data-filter="era" data-value="${key}">${label}</button>`
    ).join('');

    const levelChips = LEVEL_CHIPS.map(({ key, label }) =>
      `<button class="lib-chip${key === 'all' ? ' is-active' : ''}" data-filter="level" data-value="${key}">${label}</button>`
    ).join('');

    const instrumentChips = INSTRUMENT_CHIPS.map(({ key, label }) =>
      `<button class="lib-chip${key === 'all' ? ' is-active' : ''}" data-filter="instrument" data-value="${key}">${label}</button>`
    ).join('');

    const sourceOrgChips = SOURCE_ORG_CHIPS.map(({ key, label }) =>
      `<button class="lib-chip${key === 'all' ? ' is-active' : ''}" data-filter="sourceOrg" data-value="${key}">${label}</button>`
    ).join('');

    return `
      <div class="lib__header">
        <span class="lib__header-title">📚 라이브러리</span>
        <button class="lib__close" title="닫기">✕</button>
      </div>

      <div class="lib__body">

        <!-- 좌측 30%: 칩 필터 + 검색 + 목록 -->
        <aside class="lib__sidebar">
          <div class="lib-search">
            <input type="search" class="lib-search__input" placeholder="이론 / 학자 / 기관 검색…" />
          </div>

          <div class="lib-chips-section">
            <div class="lib-chip-row" data-row="useCase">
              <span class="lib-chip-label">용도</span>
              ${useCaseChips}
            </div>
            <!-- 브리핑 모드 전용 필터 (기본 hidden) -->
            <div class="lib-chip-row lib-chip-row--briefing-only" data-row="sourceOrg" style="display:none">
              <span class="lib-chip-label">출처</span>
              ${sourceOrgChips}
            </div>
            <!-- 일반 모드 필터 -->
            <div class="lib-chip-row lib-chip-row--normal-only" data-row="region">
              <span class="lib-chip-label">지역</span>
              ${regionChips}
            </div>
            <div class="lib-chip-row lib-chip-row--normal-only" data-row="era">
              <span class="lib-chip-label">시대</span>
              ${eraChips}
            </div>
            <div class="lib-chip-row lib-chip-row--normal-only" data-row="level">
              <span class="lib-chip-label">분석수준</span>
              ${levelChips}
            </div>
            <div class="lib-chip-row lib-chip-row--normal-only" data-row="instrument">
              <span class="lib-chip-label">권력수단</span>
              ${instrumentChips}
            </div>
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

    // 칩 클릭 — 행 내 단일 선택
    this._el.querySelectorAll('.lib-chip').forEach(chip => {
      chip.addEventListener('click', () => {
        const { filter, value } = chip.dataset;
        const row = chip.closest('.lib-chip-row');
        row.querySelectorAll('.lib-chip').forEach(c => c.classList.remove('is-active'));
        chip.classList.add('is-active');
        setState('library', { [`${filter}Filter`]: value });

        // 브리핑 모드 전환: 필터 행 표시/숨김
        if (filter === 'useCase') this._toggleBriefingMode(value === 'briefing');

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
      theories, loading,
      useCaseFilter, regionFilter, eraFilter, levelFilter, instrumentFilter,
      sourceOrgFilter, searchQuery,
    } = store.getState('library');

    if (loading) { list.innerHTML = '<div class="lib-loading">로딩 중…</div>'; return; }

    // 브리핑 모드: 섹터별 아코디언 뷰
    if ((useCaseFilter || 'all') === 'briefing') {
      this._renderBriefingView(list, theories || [], sourceOrgFilter, searchQuery);
      return;
    }

    const filtered = this._filter(
      theories || [], useCaseFilter, regionFilter, eraFilter,
      levelFilter, instrumentFilter, searchQuery,
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

  // 브리핑 모드 전환 — 필터 행 표시/숨김
  _toggleBriefingMode(isBriefing) {
    this._el.querySelectorAll('.lib-chip-row--briefing-only').forEach(el => {
      el.style.display = isBriefing ? '' : 'none';
    });
    this._el.querySelectorAll('.lib-chip-row--normal-only').forEach(el => {
      el.style.display = isBriefing ? 'none' : '';
    });
    // 브리핑 모드 진입 시 sourceOrg 필터 초기화
    if (isBriefing) setState('library', { sourceOrgFilter: 'all' });
  }

  // 브리핑 섹터별 아코디언 렌더링
  _renderBriefingView(list, theories, sourceOrgFilter, searchQuery) {
    const briefings = theories.filter(t =>
      (t.use_case || t.asset_type) === 'briefing'
    );

    // 출처 필터 — 부분 매칭 (RAND Corporation / Foreign Policy 등 변형 대응)
    const ORG_MATCH = {
      'War on the Rocks': s => s?.startsWith('War on the Rocks'),
      'RAND':             s => s?.startsWith('RAND'),
      'CSIS':             s => s?.startsWith('CSIS'),
      'INSS':             s => s?.startsWith('INSS'),
      'ECFR':             s => s?.startsWith('ECFR') || s?.startsWith('European Council'),
      'Foreign Affairs':  s => s?.startsWith('Foreign Affairs'),
    };
    let filtered = briefings;
    if (sourceOrgFilter && sourceOrgFilter !== 'all') {
      const matchFn = ORG_MATCH[sourceOrgFilter] || (s => s === sourceOrgFilter);
      filtered = filtered.filter(t => matchFn(t.source_org));
    }
    // 검색
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      filtered = filtered.filter(t =>
        t.display_name.toLowerCase().includes(q) ||
        (t.summary || '').toLowerCase().includes(q) ||
        (t.source_org || '').toLowerCase().includes(q)
      );
    }

    if (!filtered.length) {
      list.innerHTML = '<div class="lib-empty">브리핑이 없습니다.</div>';
      return;
    }

    // 섹터별 그룹핑
    const groups = {};
    filtered.forEach(t => {
      const sector = t.sector_tag || 'unknown';
      if (!groups[sector]) groups[sector] = [];
      groups[sector].push(t);
    });

    // 순서대로 + 나머지 섹터
    const orderedKeys = [
      ...BRIEFING_SECTOR_ORDER.filter(k => groups[k]),
      ...Object.keys(groups).filter(k => !BRIEFING_SECTOR_ORDER.includes(k)),
    ];

    list.innerHTML = orderedKeys.map(sector => {
      const items = groups[sector];
      const color = SECTOR_COLORS[sector] || '#888';
      const label = SECTOR_LABELS[sector] || sector;
      const cards = items.map(t => this._cardHTML(t)).join('');
      return `
        <div class="lib-briefing-group" data-sector="${sector}">
          <button class="lib-briefing-group__header" aria-expanded="true">
            <span class="lib-briefing-group__sector-dot" style="background:${color}"></span>
            <span class="lib-briefing-group__label">${label}</span>
            <span class="lib-briefing-group__count">${items.length}</span>
            <span class="lib-briefing-group__arrow">▾</span>
          </button>
          <div class="lib-briefing-group__items">${cards}</div>
        </div>
      `;
    }).join('');

    // 아코디언 토글
    list.querySelectorAll('.lib-briefing-group__header').forEach(btn => {
      btn.addEventListener('click', () => {
        const expanded = btn.getAttribute('aria-expanded') === 'true';
        btn.setAttribute('aria-expanded', String(!expanded));
        btn.nextElementSibling.style.display = expanded ? 'none' : '';
        btn.querySelector('.lib-briefing-group__arrow').textContent = expanded ? '▸' : '▾';
      });
    });

    // 카드 클릭
    list.querySelectorAll('.lib-card').forEach(card => {
      card.addEventListener('click', () => {
        const theory = filtered.find(t => t.theory_id === card.dataset.id);
        if (theory) this._selectTheory(theory);
      });
    });
  }

  _filter(theories, useCase, region, era, level, instrument, query) {
    let r = theories;
    r = r.filter(t => _matchesUseCase(t,   useCase    || 'all'));
    r = r.filter(t => _matchesRegion(t,    region     || 'all'));
    r = r.filter(t => _matchesEra(t,       era        || 'all'));
    r = r.filter(t => _matchesLevel(t,     level      || 'all'));
    r = r.filter(t => _matchesInstrument(t,instrument || 'all'));
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
    const isActive = theory.theory_id === this._activeId ? ' is-active' : '';
    const summary  = theory.summary
      ? `<p class="lib-card__summary">${theory.summary}</p>` : '';

    // 브리핑 카드: 기관명 + 날짜 표시
    if (theory.use_case === 'briefing') {
      const org  = theory.source_org  ? `<span class="lib-card__org">${theory.source_org}</span>` : '';
      const date = theory.published_date
        ? `<span class="lib-card__date">${theory.published_date}</span>` : '';
      return `
        <div class="lib-card lib-card--briefing${isActive}" data-id="${theory.theory_id}">
          <div class="lib-card__header">
            <span class="lib-card__sector" style="--sector-color:${color}">${label}</span>
            <span class="lib-card__name">${theory.display_name}</span>
          </div>
          <div class="lib-card__meta">${org}${date}</div>
          ${summary}
        </div>
      `;
    }

    // 일반 이론/사례 카드
    const theorists = (theory.theorists || []).slice(0, 2).join(', ') || '—';
    const year      = theory.year ? ` (${theory.year})` : '';
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

    this._el.querySelectorAll('.lib-card').forEach(c => {
      c.classList.toggle('is-active', c.dataset.id === this._activeId);
    });

    const placeholder = this._el.querySelector('.lib__detail-placeholder');
    const content     = this._el.querySelector('.lib__detail-content');
    placeholder.style.display = 'none';
    content.style.display = 'flex';

    const color     = SECTOR_COLORS[theory.sector_tag] || '#888';
    const label     = SECTOR_LABELS[theory.sector_tag] || theory.sector_tag;
    const theorists = (theory.theorists || []).join(', ') || '—';
    const year      = theory.year ? ` · ${theory.year}` : '';

    const sectorEl = this._el.querySelector('.lib__detail-sector');
    sectorEl.textContent = label;
    sectorEl.style.setProperty('--sector-color', color);
    this._el.querySelector('.lib__detail-title').textContent = theory.display_name;
    this._el.querySelector('.lib__detail-meta').textContent  = `${theorists}${year}`;

    this._el.querySelector('.lib-ai-result').innerHTML = '';
    const aiBtn = this._el.querySelector('.lib-ai-btn');
    aiBtn.disabled = false;
    aiBtn.textContent = '🤖 AI로 더 알아보기';

    let fullTheory = theory;
    if (!theory.body) {
      this._el.querySelector('.lib-detail-md').innerHTML =
        '<p style="color:#8b949e;font-size:12px">본문 로딩 중…</p>';
      try {
        fullTheory = await api.get(`/api/library/theories/${theory.theory_id}`);
        const { theories } = store.getState('library');
        const idx = theories.findIndex(t => t.theory_id === theory.theory_id);
        if (idx >= 0) theories[idx] = fullTheory;
      } catch (e) {
        this._el.querySelector('.lib-detail-md').innerHTML =
          '<p style="color:#f85149;font-size:12px">본문 로드 실패</p>';
        return;
      }
    }

    const bodyHtml = fullTheory.body
      ? (window.marked
          ? window.marked.parse(fullTheory.body)
          : `<pre style="white-space:pre-wrap;font-size:12px">${fullTheory.body}</pre>`)
      : '<p style="color:#8b949e;font-size:12px">본문이 없습니다. POST /api/library/reindex 실행 후 새로고침하세요.</p>';

    this._el.querySelector('.lib-detail-md').innerHTML = bodyHtml;
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
