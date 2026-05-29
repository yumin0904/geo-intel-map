/**
 * TopBarView.js — 상단 3단 바 (총 48px)
 *
 * Row 1: ◆ GEO-INTEL BRIEF ◆ │ THREAT: 중동🔴91 │ 인태🟠72 │ 유럽🟡68 │ 아프리카🟢45 │ 🍕 74.6
 * Row 2: MARKET │ WTI $96.60▼0.88% │ 금 $413.8▲0.57% │ 반도체 $537.3▲2.06% │ 원/달러 ₩1,514▲0.46%
 * Row 3: ▶  뉴스 티커 스크롤
 */

const API_BASE = 'http://localhost:8000';

// 긴장도 레벨 → emoji
const LEVEL_EMOJI = {
  critical: '🔴',
  high:     '🟠',
  medium:   '🟡',
  low:      '🟢',
};

const TICKER_SPEED_PX_S = 80;
const TICKER_REFRESH_MS = 3 * 60 * 1000;

// ── 🍕 펜타곤 피자 지수 레벨 정의 ─────────────────────────────────────────────
// 참고: 실제 CIA 분석가들이 펜타곤 인근 피자 주문 급증 = 야근 = 작전 임박을 비공식 지표로 사용
const PIZZA_LEVELS = [
  {
    min:   76,
    label: 'CRITICAL',
    emoji: '🔴',
    desc:  '작전 임박',
    detail: [
      '강대국 직접 군사 개입 또는 전략 억제력 경보 상태',
      '에너지·식량·반도체 공급망 동시 붕괴 위험',
      '시장: 극단적 리스크오프, 금·달러 급등',
      '역사 사례: 1962 쿠바 미사일 위기, 2022 우크라이나 침공 직후',
    ],
  },
  {
    min:   56,
    label: 'GUARDED',
    emoji: '🟠',
    desc:  '야근 감지',
    detail: [
      '복수 전선 동시 고강도 충돌 또는 핵심 SLOC 위협',
      '글로벌 공급망 압박 시작, 유가·곡물가 상승',
      '시장: 리스크오프 신호, 방산주 상승',
      '역사 사례: 2024년 1월 홍해 위기, 2023년 10월 7일 가자 공습',
    ],
  },
  {
    min:   36,
    label: 'ELEVATED',
    emoji: '🟡',
    desc:  '회의 증가',
    detail: [
      '1개 이상 전선에서 전투 강도 상승',
      '특수작전·드론 타격 증가, 우발적 확전 위험',
      '시장: 산발적 변동, 회색지대 갈등 지속',
      '역사 사례: 2021 미얀마 쿠데타, 2019 아덴만 유조선 공격',
    ],
  },
  {
    min:   0,
    label: 'NORMAL',
    emoji: '🟢',
    desc:  '정상 업무',
    detail: [
      '주요 열강 간 직접 군사 대치 없음',
      '외교·제재 수단 중심, 분쟁은 국지전 수준 유지',
      '시장: 지정학 리스크 프리미엄 최소화',
      '역사 사례: 2016-17년 북핵 위기 이전 안정기',
    ],
  },
];

// 피자 지수 최근 갱신 상태
let _pizzaIndexVal  = 0;
let _tensionFetchAt = 0;
let _lastSectors    = [];   // 최신 섹터 데이터 (툴팁 드라이버 표시용)

// ── DOM 참조 ─────────────────────────────────────────────────────────────────
const $tension      = () => document.getElementById('tension-zone');
const $market       = () => document.getElementById('market-zone');
const $tickerTrack  = () => document.getElementById('news-ticker-track');
const $pizzaTooltip = () => document.getElementById('pizza-tooltip');
const $driverTooltip= () => document.getElementById('driver-tooltip');

// ── API ──────────────────────────────────────────────────────────────────────
async function _get(path) {
  const res = await fetch(API_BASE + path);
  if (!res.ok) throw new Error(`${path} HTTP ${res.status}`);
  return res.json();
}

// ── 드라이버 툴팁 ─────────────────────────────────────────────────────────────
function _showDriverTooltip(sector, el) {
  const tt = $driverTooltip();
  if (!tt) return;

  const sectorData = _lastSectors.find(s => s.sector === sector);
  if (!sectorData) return;

  const score = sectorData.avg_severity.toFixed(1);
  const level = sectorData.level;
  const emoji = LEVEL_EMOJI[level] || '🟢';
  const drivers = sectorData.drivers || [];

  const levelText = {
    critical: '위험 (75+)',
    high:     '높음 (55-74)',
    medium:   '보통 (35-54)',
    low:      '낮음 (0-34)',
  }[level] || '';

  // 드라이버 HTML
  const driverHtml = drivers.length === 0
    ? '<div class="dt-driver-empty">최근 주요 이벤트 없음</div>'
    : drivers.map(d => {
        const src   = d.data_source === 'GDELT' ? '🔴실시간' : '📊ACLED';
        const daysStr = d.days_ago < 1
          ? `${Math.round(d.days_ago * 24)}시간 전`
          : d.days_ago > 90
            ? `${Math.round(d.days_ago / 30)}개월 전`
            : `${Math.round(d.days_ago)}일 전`;
        const etko  = d.event_type_ko ? `<span class="dt-etype">${_escHtml(d.event_type_ko)}</span> ` : '';
        return (
          `<div class="dt-driver">` +
          `<span class="dt-src">${src}</span> ` +
          etko +
          `<span class="dt-name">${_escHtml(d.display)}</span>` +
          `<span class="dt-time"> · ${daysStr}</span>` +
          `</div>`
        );
      }).join('');

  // 데이터 기반 설명
  const acledCnt = sectorData.acled_count || 0;
  const gdeltCnt = sectorData.gdelt_count || 0;
  const sourceLine = `ACLED ${acledCnt.toLocaleString()}건 + GDELT ${gdeltCnt}건 분석`;

  tt.innerHTML =
    `<div class="dt-header">${emoji} ${sector} 위험도 ${score} <span class="dt-level">${levelText}</span></div>` +
    `<div class="dt-source">${sourceLine} (이벤트 유형·최근성 가중 평균)</div>` +
    `<div class="dt-sep"></div>` +
    `<div class="dt-drivers-label">▶ 주요 드라이버</div>` +
    driverHtml;

  // 위치 계산 (el 아래)
  const rect = el.getBoundingClientRect();
  tt.style.left = `${Math.max(4, rect.left)}px`;
  tt.style.top  = `${rect.bottom + 4}px`;
  tt.classList.add('is-visible');
}

function _hideDriverTooltip() {
  const tt = $driverTooltip();
  if (tt) tt.classList.remove('is-visible');
}

// ── 1단: THREAT 긴장도 ────────────────────────────────────────────────────────
function _renderTension(sectors) {
  const el = $tension();
  if (!el) return;
  _lastSectors = sectors || [];

  if (!sectors || sectors.length === 0) {
    el.innerHTML = '<span style="color:var(--color-text-secondary)">데이터 없음</span>';
    return;
  }

  el.innerHTML = sectors.map(s => {
    const score = Math.round(s.avg_severity);
    const emoji = LEVEL_EMOJI[s.level] || LEVEL_EMOJI.low;
    return (
      `<span class="tension-item" data-sector="${_esc(s.sector)}">` +
      `<span class="t-name">${s.sector}</span>` +
      `<span class="t-emoji">${emoji}</span>` +
      `<span class="t-score">${score}</span>` +
      `</span>`
    );
  }).join('');

  // 호버 이벤트
  el.querySelectorAll('.tension-item').forEach(item => {
    item.addEventListener('mouseenter', () => _showDriverTooltip(item.dataset.sector, item));
    item.addEventListener('mouseleave', _hideDriverTooltip);
  });
}

// ── 🍕 펜타곤 피자 지수 ──────────────────────────────────────────────────────
function _pizzaLevel(index) {
  return PIZZA_LEVELS.find(l => index >= l.min) || PIZZA_LEVELS[PIZZA_LEVELS.length - 1];
}

function _calcPizzaIndex(sectors) {
  if (!sectors || sectors.length === 0) return 0;
  let total = 0;
  for (const s of sectors) {
    const w = s.pizza_weight ?? (1 / sectors.length);
    total += (s.avg_severity || 0) * w;
  }
  return total;
}

function _renderPizzaBadge() {
  const btn = document.getElementById('pizza-btn');
  if (btn) btn.textContent = `🍕 ${_pizzaIndexVal.toFixed(1)}`;
}

function _renderPizzaTooltip() {
  const el = $pizzaTooltip();
  if (!el) return;

  const idx = _pizzaIndexVal;
  const lv  = _pizzaLevel(idx);
  const minAgo = _tensionFetchAt
    ? Math.floor((Date.now() - _tensionFetchAt) / 60000)
    : null;
  const updateStr = minAgo === null ? '—' : minAgo === 0 ? '방금 전' : `${minAgo}분 전`;

  const SEP = '─'.repeat(36);

  // 현재 레벨 상세 항목 HTML
  const detailHtml = lv.detail
    .map(line => `<div class="pzt-detail-line">· ${_escHtml(line)}</div>`)
    .join('');

  // 레벨 가이드 (4단계)
  const guideHtml = PIZZA_LEVELS.slice().reverse().map(lvl => {
    const isActive = (lvl.label === lv.label);
    const style = isActive ? ' style="color:#00b4d8;font-weight:700"' : '';
    const range = lvl === PIZZA_LEVELS[0]
      ? `76+` : lvl === PIZZA_LEVELS[1]
      ? `56-75` : lvl === PIZZA_LEVELS[2]
      ? `36-55` : `0-35`;
    return `<div class="pzt-guide"${style}>${lvl.emoji} ${range}&nbsp;${lvl.label}&nbsp;—&nbsp;${lvl.desc}</div>`;
  }).join('');

  el.innerHTML =
    `<div class="pzt-title">🍕 펜타곤 피자 지수 (Pentagon Pizza Index)</div>` +
    `<div class="pzt-sub">CIA·NSA 분석가들의 비공식 작전 임박 지표</div>` +
    `<div class="pzt-rule">${SEP}</div>` +
    `<div class="pzt-cur">현재: <b>${idx.toFixed(1)}</b> → ${lv.emoji} <b>${lv.label}</b> — ${lv.desc}</div>` +
    `<div class="pzt-detail">${detailHtml}</div>` +
    `<div class="pzt-rule">${SEP}</div>` +
    `<div class="pzt-guide-hdr">레벨 기준:</div>` +
    guideHtml +
    `<div class="pzt-rule">${SEP}</div>` +
    `<div class="pzt-concept">개념: 펜타곤 인근 피자 배달량 급증 시<br>&nbsp;&nbsp;&nbsp;&nbsp;내부 긴급회의·야근 = 군사작전 임박 신호</div>` +
    `<div class="pzt-footer">가중 평균: 중동(40%)·인태(30%)·유럽(20%)·아프리카(10%) | 업데이트: ${updateStr}</div>`;
}

// ── 2단: MARKET ───────────────────────────────────────────────────────────────
function _renderMarkets(items) {
  const el = $market();
  if (!el) return;
  if (!items || items.length === 0) {
    el.innerHTML = '<span style="color:var(--color-text-secondary)">데이터 없음</span>';
    return;
  }

  el.innerHTML = items.map(item => {
    if (item.price == null) {
      return (
        `<span class="market-item">` +
        `<span class="mkt-name">${item.emoji} ${item.name}</span> ` +
        `<span class="mkt-price" style="color:var(--color-text-secondary)">—</span>` +
        `</span>`
      );
    }
    const up    = item.direction === 'up';
    const arrow = up ? '▲' : '▼';
    const color = up ? '#3fb950' : '#f85149';
    const priceStr = item.ticker === 'KRW=X'
      ? `₩${Math.round(item.price).toLocaleString()}`
      : `$${item.price.toFixed(item.price >= 100 ? 1 : 2)}`;

    return (
      `<span class="market-item">` +
      `<span class="mkt-name">${item.name}</span> ` +
      `<span class="mkt-price">${priceStr}</span>` +
      `<span class="mkt-change" style="color:${color}">${arrow}${Math.abs(item.change_pct).toFixed(2)}%</span>` +
      `</span>`
    );
  }).join('');
}

// ── 3단: 뉴스 티커 ───────────────────────────────────────────────────────────
function _renderTicker(items) {
  const track = $tickerTrack();
  if (!track) return;
  if (!items || items.length === 0) {
    track.innerHTML = '<span class="ticker-item">뉴스 없음</span>';
    track.style.removeProperty('--ticker-duration');
    return;
  }
  const singleSet = items.map(item => {
    const time    = item.time_label ? ` · ${item.time_label}` : '';
    const urlAttr = item.url ? ` data-url="${_esc(item.url)}"` : '';
    return `<span class="ticker-item"${urlAttr}>${_escHtml(item.text ?? item.text_ko ?? '')}${time}</span>`;
  }).join('<span class="ticker-sep">　·　</span>');

  const sep = '<span class="ticker-sep">　·　·　</span>';
  track.innerHTML = singleSet + sep + singleSet + sep;

  requestAnimationFrame(() => {
    const halfWidth = track.scrollWidth / 2;
    if (halfWidth > 0) {
      track.style.setProperty('--ticker-duration', `${(halfWidth / TICKER_SPEED_PX_S).toFixed(1)}s`);
    }
    track.style.animation = 'none';
    void track.offsetWidth;
    track.style.animation = '';
  });
}

function _esc(s)    { return String(s).replace(/"/g, '&quot;'); }
function _escHtml(s){ return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

// ── 갱신 ─────────────────────────────────────────────────────────────────────
async function _refreshTension() {
  try {
    const sectors = await _get('/api/stats/tension');
    _renderTension(sectors);
    _pizzaIndexVal  = _calcPizzaIndex(sectors);
    _tensionFetchAt = Date.now();
    _renderPizzaBadge();
  } catch (e) { console.debug('[TopBar] tension 실패:', e.message); }
}

async function _refreshMarkets() {
  try { _renderMarkets(await _get('/api/stats/markets')); }
  catch (e) { console.debug('[TopBar] markets 실패:', e.message); }
}

async function _refreshTicker() {
  try {
    const { items } = await _get('/api/news/ticker');
    _renderTicker(items);
  } catch (e) { console.debug('[TopBar] ticker 실패:', e.message); }
}

// ── 초기화 ───────────────────────────────────────────────────────────────────
export function initTopBar() {
  _refreshTension();
  _refreshMarkets();
  setTimeout(_refreshTicker, 3000);

  setInterval(_refreshTension, 10 * 60 * 1000);
  setInterval(_refreshMarkets,  5 * 60 * 1000);
  setInterval(_refreshTicker,  TICKER_REFRESH_MS);

  // 티커 클릭 → 원문 새 탭
  document.getElementById('news-ticker-wrap')?.addEventListener('click', e => {
    const item = e.target.closest('[data-url]');
    if (item?.dataset.url) window.open(item.dataset.url, '_blank', 'noopener,noreferrer');
  });

  // 🍕 피자 툴팁 호버
  document.querySelector('.pizza-wrap')?.addEventListener('mouseenter', _renderPizzaTooltip);

  // 드라이버 툴팁 — 다른 곳 클릭 시 닫기
  document.addEventListener('mouseover', e => {
    if (!e.target.closest('.tension-item') && !e.target.closest('#driver-tooltip')) {
      _hideDriverTooltip();
    }
  });
}
