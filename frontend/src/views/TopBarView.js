/**
 * TopBarView.js — 상단 3단 바 (총 48px)
 *
 * Row 1: ◆ GEO-INTEL BRIEF ◆  THREAT │ 중동 ████ 91 │ 인태 ███ 72 │ ...
 * Row 2: MARKET │ WTI $96.6▼ │ 금 $413▲ │ SOXX $537▲ │ ₩1,513▼
 * Row 3: ▶  뉴스 티커 스크롤
 */

const API_BASE = 'http://localhost:8000';

// 긴장도 레벨 → 블록 수 + 색상
const TENSION_LEVELS = {
  critical: { blocks: 4, color: '#f85149' },   // ≥80
  high:     { blocks: 3, color: '#f0883e' },   // ≥60
  medium:   { blocks: 2, color: '#d29922' },   // ≥40
  low:      { blocks: 1, color: '#3fb950' },   // <40
};

const TICKER_SPEED_PX_S = 80;
const TICKER_REFRESH_MS = 3 * 60 * 1000;

// ── DOM 참조 ─────────────────────────────────────────────────────────────────
const $tension     = () => document.getElementById('tension-zone');
const $market      = () => document.getElementById('market-zone');
const $tickerTrack = () => document.getElementById('news-ticker-track');

// ── API ──────────────────────────────────────────────────────────────────────
async function _get(path) {
  const res = await fetch(API_BASE + path);
  if (!res.ok) throw new Error(`${path} HTTP ${res.status}`);
  return res.json();
}

// ── 1단: THREAT 긴장도 ────────────────────────────────────────────────────────
function _tensionBar(level) {
  const cfg = TENSION_LEVELS[level] || TENSION_LEVELS.low;
  return `<span class="tension-bar" style="color:${cfg.color}">${'█'.repeat(cfg.blocks)}</span>`;
}

function _renderTension(sectors) {
  const el = $tension();
  if (!el) return;
  if (!sectors || sectors.length === 0) {
    el.innerHTML = '<span style="color:var(--color-text-secondary)">데이터 없음</span>';
    return;
  }
  el.innerHTML = sectors.map(s => {
    const score = Math.round(s.avg_severity);
    const hint  = `${s.event_count}건 평균 ${s.avg_severity.toFixed(1)}`;
    return (
      `<span class="tension-item" title="${hint}">` +
      `<span class="tension-name">${s.sector}</span>` +
      _tensionBar(s.level) +
      `<span class="tension-score">${score}</span>` +
      `</span>`
    );
  }).join('');
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

    const up     = item.direction === 'up';
    const arrow  = up ? '▲' : '▼';
    const color  = up ? '#3fb950' : '#f85149';
    const sign   = item.change_pct >= 0 ? '+' : '';

    // KRW=X는 정수, 나머지는 소수점 1자리
    const priceStr = item.ticker === 'KRW=X'
      ? `₩${Math.round(item.price).toLocaleString()}`
      : `$${item.price.toFixed(item.price >= 100 ? 1 : 2)}`;

    return (
      `<span class="market-item">` +
      `<span class="mkt-name">${item.name}</span> ` +
      `<span class="mkt-price">${priceStr}</span>` +
      `<span class="mkt-change" style="color:${color}">${arrow}${sign}${Math.abs(item.change_pct).toFixed(2)}%</span>` +
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
    return `<span class="ticker-item"${urlAttr}>${_escHtml(item.text_ko)}${time}</span>`;
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
  try { _renderTension(await _get('/api/stats/tension')); }
  catch (e) { console.debug('[TopBar] tension 실패:', e.message); }
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
}
