/**
 * TopBarView.js — 상단 3단 바 (총 48px)
 *
 * Row 1: ◆ GEO-INTEL BRIEF ◆ │ THREAT: 중동🔴91 │ 인태🟠72 │ 유럽🟡68 │ 아프리카🟢45 │ 🍕 74.6
 * Row 2: MARKET │ WTI $96.60▼0.88% │ 금 $413.8▲0.57% │ 반도체 $537.3▲2.06% │ 원/달러 ₩1,514▲0.46%
 * Row 3: ▶  뉴스 티커 스크롤
 */

const API_BASE = 'http://localhost:8000';

// 긴장도 레벨 → emoji 표시 (블록 바 → compact emoji 형식으로 변경)
const LEVEL_EMOJI = {
  critical: '🔴',   // ≥80
  high:     '🟠',   // ≥60
  medium:   '🟡',   // ≥40
  low:      '🟢',   // <40
};

const TICKER_SPEED_PX_S = 80;
const TICKER_REFRESH_MS = 3 * 60 * 1000;

// 🍕 펜타곤 피자 지수 레벨 정의 (긴장도 → 작전 임박도)
const PIZZA_LEVELS = [
  { min: 81, label: 'CRITICAL', emoji: '🔴', desc: '작전 임박'  },
  { min: 61, label: 'GUARDED',  emoji: '🟠', desc: '야근 감지'  },
  { min: 41, label: 'ELEVATED', emoji: '🟡', desc: '회의 증가'  },
  { min:  0, label: 'NORMAL',   emoji: '🟢', desc: '정상 업무'  },
];

// 피자 지수 최근 갱신 상태 (hover 시 "N분 전" 계산용)
let _pizzaIndexVal   = 0;
let _tensionFetchAt  = 0;   // Date.now() 타임스탬프

// ── DOM 참조 ─────────────────────────────────────────────────────────────────
const $tension     = () => document.getElementById('tension-zone');
const $market      = () => document.getElementById('market-zone');
const $tickerTrack = () => document.getElementById('news-ticker-track');
const $pizzaTooltip = () => document.getElementById('pizza-tooltip');

// ── API ──────────────────────────────────────────────────────────────────────
async function _get(path) {
  const res = await fetch(API_BASE + path);
  if (!res.ok) throw new Error(`${path} HTTP ${res.status}`);
  return res.json();
}

// ── 1단: THREAT 긴장도 — compact emoji 형식 ─────────────────────────────────
function _renderTension(sectors) {
  const el = $tension();
  if (!el) return;
  if (!sectors || sectors.length === 0) {
    el.innerHTML = '<span style="color:var(--color-text-secondary)">데이터 없음</span>';
    return;
  }
  el.innerHTML = sectors.map(s => {
    const score = Math.round(s.avg_severity);
    const emoji = LEVEL_EMOJI[s.level] || LEVEL_EMOJI.low;
    const hint  = `${s.event_count}건 평균 ${s.avg_severity.toFixed(1)}`;
    return (
      `<span class="tension-item" title="${hint}">` +
      `<span class="t-name">${s.sector}</span>` +
      `<span class="t-emoji">${emoji}</span>` +
      `<span class="t-score">${score}</span>` +
      `</span>`
    );
  }).join('');
}

// ── 🍕 펜타곤 피자 지수 ──────────────────────────────────────────────────────
function _pizzaLevel(index) {
  return PIZZA_LEVELS.find(l => index >= l.min) || PIZZA_LEVELS[PIZZA_LEVELS.length - 1];
}

function _calcPizzaIndex(sectors) {
  if (!sectors || sectors.length === 0) return 0;
  // pizza_weight(백엔드 지정)로 가중 평균 — 중동(0.4)·인태(0.3)·유럽(0.2)·아프리카(0.1)
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

  const SEP = '━'.repeat(33);
  el.innerHTML =
    `<div class="pzt-title">🍕 펜타곤 피자 지수 (Pentagon Pizza Index)</div>` +
    `<div class="pzt-rule">${SEP}</div>` +
    `<div class="pzt-cur">현재: <b>${idx.toFixed(1)}</b> → ${lv.emoji} ${lv.label} — ${lv.desc}</div>` +
    `<div class="pzt-rule">${SEP}</div>` +
    `<div class="pzt-desc">개념: 펜타곤 인근 피자 배달량 급증 시\n` +
    `      내부 긴급회의/야근 = 군사작전 임박 신호\n` +
    `      CIA·NSA 분석가들의 비공식 참고 지표</div>` +
    `<div class="pzt-guide-hdr">\n판독 기준:</div>` +
    `<div class="pzt-guide">🟢 0-40&nbsp;&nbsp; NORMAL&nbsp;&nbsp;&nbsp;— 정상 업무</div>` +
    `<div class="pzt-guide">🟡 41-60 ELEVATED — 회의 증가</div>` +
    `<div class="pzt-guide">🟠 61-80 GUARDED&nbsp; — 야근 감지</div>` +
    `<div class="pzt-guide">🔴 81+&nbsp;&nbsp;&nbsp;&nbsp;CRITICAL — 작전 임박</div>` +
    `<div class="pzt-footer">현재 글로벌 긴장도 기반 산출\n업데이트: ${updateStr}</div>`;
}

// ── 2단: MARKET 4개 동시 표시 ────────────────────────────────────────────────
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

    // KRW=X → ₩1,514  / 나머지 → $96.60 (< 100: 2자리) $413.8 (≥ 100: 1자리)
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
    // 새 콘텐츠 적용 시 애니메이션 재시작
    track.style.animation = 'none';
    void track.offsetWidth;
    track.style.animation = '';
  });
}

function _esc(s)    { return String(s).replace(/"/g, '&quot;'); }
function _escHtml(s){ return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

// ── 갱신 함수 ─────────────────────────────────────────────────────────────────
async function _refreshTension() {
  try {
    const sectors = await _get('/api/stats/tension');
    _renderTension(sectors);
    // 피자 지수: 섹터 평균 긴장도 기반
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
  // 1·2단 즉시 로드
  _refreshTension();
  _refreshMarkets();

  // 3단: GDELT 캐시 웜업 대기 후 로드
  setTimeout(_refreshTicker, 3000);

  // 주기적 갱신
  setInterval(_refreshTension, 5 * 60 * 1000);
  setInterval(_refreshMarkets, 5 * 60 * 1000);
  setInterval(_refreshTicker,  TICKER_REFRESH_MS);

  // 티커 클릭 → 원문 새 탭
  document.getElementById('news-ticker-wrap')?.addEventListener('click', e => {
    const item = e.target.closest('[data-url]');
    if (item?.dataset.url) window.open(item.dataset.url, '_blank', 'noopener,noreferrer');
  });

  // 🍕 피자 툴팁 — 호버 시 최신 "N분 전" 포함 콘텐츠 렌더
  document.querySelector('.pizza-wrap')?.addEventListener('mouseenter', _renderPizzaTooltip);
}
