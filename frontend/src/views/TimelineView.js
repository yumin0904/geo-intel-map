/**
 * TimelineView.js — Cascade 인과 타임라인 패널 (vis-timeline 기반)
 *
 * CLAUDE.md 3.4: "타임라인 뷰: vis-timeline, 시간순 이벤트 배열"
 *
 * 데이터 흐름: CascadeLayer.load() → EventBus('cascade:loaded') → 이 뷰
 * API 이중 호출 없이 EventBus 단일 발화로 공유 (CLAUDE.md 성능 원칙).
 *
 * 각 CascadeLink는 "trigger 시점 ~ response 시점" range 바로 표시.
 * 바의 너비 = 인과 전달 시간(time_delta) — 정치외교학 학습 포인트:
 * 지역 분쟁이 글로벌 시장에 전달되는 데 걸리는 시간을 직관적으로 관찰.
 */

// rule_id → 한국어 레이블 (cascade_rules.yaml name 필드와 동기화)
const RULE_LABEL = {
  bab_el_mandeb_tension_to_oil:  '바브엘만데브 → 유가',
  ukraine_conflict_to_wheat:      '우크라이나 → 밀선물',
  middle_east_conflict_to_gold:   '중동 → 금(안전자산)',
  south_china_sea_to_defense:     '남중국해 → 방산주',
  south_china_sea_to_lng:         '남중국해 → LNG',
  suez_tension_to_shipping:       '수에즈 → 해운주',
};

function ruleLabel(id) {
  return RULE_LABEL[id] ?? id.replace(/_to_/, ' → ').replace(/_/g, ' ');
}

function fmtDelta(seconds) {
  const h = Math.round(seconds / 3600);
  return h < 24 ? `${h}h 후` : `${Math.round(h / 24)}d 후`;
}

// DOM 참조 — 파일 상단에서 한 번만 쿼리 (CLAUDE.md JS 원칙)
const PANEL_EL   = document.getElementById('timeline-panel');
const VIS_EL     = document.getElementById('timeline-vis');
const TOGGLE_BTN = document.getElementById('timeline-toggle');
const COUNT_EL   = document.getElementById('timeline-count');
const FILTER_BAR = document.getElementById('conflict-filter-bar');
const YEAR_SEL   = document.getElementById('tl-year');
const MONTH_SEL  = document.getElementById('tl-month');
const DAY_SEL    = document.getElementById('tl-day');
const GOTO_BTN   = document.getElementById('tl-goto');
const FIT_BTN    = document.getElementById('tl-fit');

// 패널의 고정 오버헤드(header 36px + toolbar 36px) — vis 높이 계산에 사용
const _OVERHEAD = 72;

export class TimelineView {
  /** @param {EventBus} eventBus */
  constructor(eventBus) {
    this._eventBus = eventBus;
    this._timeline = null;
    this._linkMap  = new Map(); // link.id → { link, src, tgt }
    this._isOpen   = false;
    this._dragH    = null;     // 드래그로 설정한 패널 높이(px). null이면 CSS 30vh 사용

    this._initResizeHandle();
    this._initControls();
    TOGGLE_BTN.addEventListener('click', () => this._toggle());

    // CascadeLayer가 load 완료 후 emit — 같은 데이터를 재사용해 이중 fetch 방지
    this._eventBus.on('cascade:loaded', data => this._render(data));
  }

  _initResizeHandle() {
    const handle = document.createElement('div');
    handle.className = 'timeline-resize-handle';
    PANEL_EL.prepend(handle);

    let startY = 0, startH = 0;

    const onMove = (e) => {
      // 위로 드래그(dy > 0)하면 패널이 커짐
      const dy = startY - e.clientY;
      const newH = Math.max(120, Math.min(window.innerHeight * 0.8, startH + dy));
      PANEL_EL.style.height = newH + 'px';
      VIS_EL.style.height   = (newH - _OVERHEAD) + 'px';
      if (FILTER_BAR) FILTER_BAR.style.bottom = (newH + 14) + 'px';
    };

    const onEnd = () => {
      PANEL_EL.style.transition = '';
      handle.classList.remove('is-dragging');
      this._dragH = PANEL_EL.offsetHeight;
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onEnd);
      // vis-timeline이 새 컨테이너 크기를 인식하도록 강제 재계산
      if (this._timeline) {
        this._timeline.setOptions({ height: (this._dragH - _OVERHEAD) + 'px' });
        this._timeline.redraw();
      }
    };

    handle.addEventListener('mousedown', (e) => {
      if (!this._isOpen) return;
      e.preventDefault();
      startY = e.clientY;
      startH = PANEL_EL.offsetHeight;
      // 드래그 중 CSS transition 비활성화 (즉각 반응)
      PANEL_EL.style.transition = 'none';
      handle.classList.add('is-dragging');
      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', onEnd);
    });
  }

  _toggle() {
    this._isOpen = !this._isOpen;
    PANEL_EL.classList.toggle('is-open', this._isOpen);
    TOGGLE_BTN.textContent = this._isOpen ? '▲' : '▼';

    if (!this._isOpen) {
      // 닫힘: 인라인 스타일 제거 → CSS height: 36px 적용
      PANEL_EL.style.height = '';
      VIS_EL.style.height   = '';
      if (FILTER_BAR) FILTER_BAR.style.bottom = '';
    } else if (this._dragH) {
      // 다시 열 때 사용자가 드래그로 설정한 높이 복원
      PANEL_EL.style.height = this._dragH + 'px';
      VIS_EL.style.height   = (this._dragH - _OVERHEAD) + 'px';
      if (FILTER_BAR) FILTER_BAR.style.bottom = (this._dragH + 14) + 'px';
    }

    // 분쟁 필터 바가 타임라인 패널과 겹치지 않도록 위로 이동 (30vh 기본값)
    FILTER_BAR?.classList.toggle('timeline-raised', this._isOpen);
    // 패널 높이 변경 후 레이아웃 재계산
    if (this._timeline) this._timeline.redraw();
  }

  _render(data) {
    const links      = data.links ?? [];
    const eventsById = new Map((data.events ?? []).map(e => [e.id, e]));

    this._linkMap.clear();
    const groupSet = new Set();
    const itemsData = [];

    for (const link of links) {
      const src = eventsById.get(link.source_event_id);
      const tgt = eventsById.get(link.target_event_id);
      if (!src || !tgt) continue;

      groupSet.add(link.rule_id);
      this._linkMap.set(link.id, { link, src, tgt });

      const pct      = link.evidence?.pct_change ?? 0;
      const ticker   = link.evidence?.ticker ?? tgt.source_id ?? '?';
      const pctStr   = `${pct >= 0 ? '+' : ''}${pct.toFixed(2)}%`;
      const scoreStr = `${(link.correlation_score * 100).toFixed(0)}%`;

      // range item: 구간 너비가 "인과 전달 시간"을 시각화
      itemsData.push({
        id:        link.id,
        group:     link.rule_id,
        start:     new Date(src.timestamp),
        end:       new Date(tgt.timestamp),
        // tooltip: hover 시 표시, <br> 사용해야 줄바꿈 작동
        title:     `⛓ ${ruleLabel(link.rule_id)}<br>${fmtDelta(link.time_delta_seconds)} 반응 · 상관도 ${scoreStr}`,
        className: `tl-link ${pct >= 0 ? 'is-up' : 'is-down'}`,
        content: `<span class="tl-item__ticker">${ticker}</span>`
               + `<span class="tl-item__pct ${pct >= 0 ? 'is-up' : 'is-down'}">${pctStr}</span>`
               + `<span class="tl-item__score">${scoreStr}</span>`,
      });
    }

    COUNT_EL.textContent = `${links.length}개 링크`;

    const groups = new vis.DataSet(
      [...groupSet].map(id => ({
        id,
        content: `<span class="tl-group__label">${ruleLabel(id)}</span>`,
      }))
    );
    const items = new vis.DataSet(itemsData);

    const hasItems = itemsData.length > 0;

    // 이미 생성된 타임라인이면 데이터만 교체 후 구간 재조정 (DOM 재사용)
    if (this._timeline) {
      this._timeline.setData({ groups, items });
      this._fitOrDefault(hasItems);
      return;
    }

    const now        = Date.now();
    const thirtyAgo  = new Date(now - 30 * 24 * 3_600_000);
    const twoDaysOut = new Date(now +  2 * 24 * 3_600_000);

    // 패널 높이(30vh)에서 오버헤드(header+toolbar=72px)를 뺀 값으로 초기화
    const openH    = Math.max(120, Math.round(window.innerHeight * 0.3));
    const visHeight = (openH - _OVERHEAD) + 'px';

    this._timeline = new vis.Timeline(VIS_EL, items, groups, {
      height:          visHeight,
      stack:           true,
      showMajorLabels: true,
      showMinorLabels: true,
      orientation:     { axis: 'top' },
      start:           thirtyAgo,
      end:             twoDaysOut,
      zoomMin:         86_400_000,          // 1일
      zoomMax:         86_400_000 * 120,    // 120일
      tooltip:         { followMouse: true, overflowMethod: 'cap' },
    });

    // 아이템 클릭 → trigger 날짜로 뷰 이동 + TheoryPanel 연동
    this._timeline.on('select', ({ items: selected }) => {
      if (!selected.length) return;
      const entry = this._linkMap.get(selected[0]);
      if (!entry) return;
      // trigger 이벤트 날짜 중앙으로 이동
      this._timeline.moveTo(new Date(entry.src.timestamp), {
        animation: { duration: 300, easingFunction: 'easeInOutQuad' },
      });
      this._eventBus.emit('marker:click', entry.src);
    });

    this._fitOrDefault(hasItems);
  }

  _initControls() {
    // 연도: 2020 ~ 내년
    const curYear = new Date().getFullYear();
    for (let y = 2020; y <= curYear + 1; y++) {
      YEAR_SEL.add(new Option(y, y));
    }
    // 월: 1~12
    for (let m = 1; m <= 12; m++) {
      MONTH_SEL.add(new Option(m + '월', m));
    }
    // 일: 1~31
    for (let d = 1; d <= 31; d++) {
      DAY_SEL.add(new Option(d, d));
    }
    // 오늘 날짜로 초기화
    const today = new Date();
    YEAR_SEL.value  = today.getFullYear();
    MONTH_SEL.value = today.getMonth() + 1;
    DAY_SEL.value   = today.getDate();

    GOTO_BTN.addEventListener('click', () => {
      const date = new Date(+YEAR_SEL.value, +MONTH_SEL.value - 1, +DAY_SEL.value);
      if (this._timeline) {
        this._timeline.moveTo(date, { animation: { duration: 300, easingFunction: 'easeInOutQuad' } });
      }
    });

    FIT_BTN.addEventListener('click', () => {
      if (this._timeline) {
        this._timeline.fit({ animation: { duration: 400, easingFunction: 'easeInOutQuad' } });
      }
    });
  }

  // 링크가 있으면 실제 데이터 구간으로 줌인, 없으면 기본 30일 창 유지
  _fitOrDefault(hasItems) {
    if (hasItems) {
      this._timeline.fit({ animation: { duration: 400, easingFunction: 'easeInOutQuad' } });
    }
  }
}
