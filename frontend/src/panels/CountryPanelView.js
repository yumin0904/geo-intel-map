/**
 * CountryPanelView.js — 국가 클릭 정보 패널
 *
 * 흐름:
 *   country:open 이벤트 → GET /api/country/{iso3} → 5탭 슬라이드인 패널 표시
 *
 * 탭 구성:
 *   1. 기본정보 — 국가명·지역 코드·ISO 코드
 *   2. 거시지표 — FRED 최근 30일 (환율·원유·VIX)
 *   3. 무역의존도 — HS 8542/27/26 상위 5개 파트너
 *   4. 제재 레짐 — sanctions.yaml 매칭 항목
 *   5. 관련이론 — library.db 지역 코드 매칭 이론
 *
 * EventBus:
 *   수신: country:open  { iso3, name_en }
 *   수신: marker:close  (ESC·지도 클릭)
 *
 * 정치외교학:
 *   Weaponized Interdependence (Farrell & Newman 2019) — 무역의존도 탭
 *   Economic Coercion (Drezner 2011) — 제재 탭
 */

import { api } from '../services/api.js';

const HS_LABELS = {
  '8542': '반도체·집적회로',
  '27':   '에너지·광물연료',
  '26':   '광석·희토류',
};

const TAB_DEFS = [
  { id: 'info',     label: '기본정보' },
  { id: 'macro',    label: '거시지표' },
  { id: 'trade',    label: '무역의존도' },
  { id: 'sanction', label: '제재' },
  { id: 'theory',   label: '관련이론' },
];

function esc(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// ── 탭별 HTML 렌더러 ─────────────────────────────────────────────────────────

function renderInfo(data) {
  const region = data.region_code
    ? `<span class="cp-badge">${esc(data.region_code)}</span>`
    : '<span class="cp-na">—</span>';

  return `
    <div class="cp-section">
      <div class="cp-kv">
        <span class="cp-key">한국어</span>
        <span class="cp-val">${esc(data.name_ko)}</span>
      </div>
      <div class="cp-kv">
        <span class="cp-key">영문명</span>
        <span class="cp-val">${esc(data.name_en)}</span>
      </div>
      <div class="cp-kv">
        <span class="cp-key">ISO-3</span>
        <span class="cp-val cp-mono">${esc(data.iso3)}</span>
      </div>
      <div class="cp-kv">
        <span class="cp-key">ISO-2</span>
        <span class="cp-val cp-mono">${esc(data.iso2 ?? '—')}</span>
      </div>
      <div class="cp-kv">
        <span class="cp-key">지역 코드</span>
        <span class="cp-val">${region}</span>
      </div>
    </div>
  `;
}

function renderMacro(data) {
  const items = data.macro ?? [];
  if (!items.length) {
    return `<div class="cp-empty">거시지표 없음 (FRED 키 미설정 또는 적재 전)</div>`;
  }

  return items.map(item => {
    const sparkLine = _sparkline(item.series ?? []);
    const pct = _changePct(item.series ?? []);
    const pctHtml = pct !== null
      ? `<span class="cp-pct ${pct >= 0 ? 'cp-up' : 'cp-dn'}">${pct >= 0 ? '+' : ''}${pct.toFixed(1)}%</span>`
      : '';

    return `
      <div class="cp-macro-row">
        <div class="cp-macro-header">
          <span class="cp-macro-label">${esc(item.label)}</span>
          <span class="cp-macro-unit">${esc(item.unit)}</span>
          ${pctHtml}
        </div>
        <div class="cp-macro-latest">
          <span class="cp-macro-value">${item.latest_value?.toLocaleString() ?? '—'}</span>
          <span class="cp-macro-date">${esc(item.latest_date ?? '')}</span>
        </div>
        ${sparkLine}
      </div>
    `;
  }).join('');
}

function renderTrade(data) {
  const tradeMap = data.trade ?? {};
  const hsCodes  = Object.keys(tradeMap);
  if (!hsCodes.length) {
    return `<div class="cp-empty">무역 데이터 없음 (Comtrade CSV 미적재)</div>`;
  }

  return hsCodes.map(hs => {
    const block   = tradeMap[hs];
    const partners = block.partners ?? [];
    const rows = partners.map((p, i) => {
      const dep  = p.dependency_ratio != null
        ? `<span class="cp-dep">${(p.dependency_ratio * 100).toFixed(1)}%</span>`
        : '';
      const flow = p.flow === 'M' ? '수입' : (p.flow === 'X' ? '수출' : p.flow);
      const val  = p.value_usd ? `$${_formatUsd(p.value_usd)}` : '—';
      return `
        <tr>
          <td class="cp-rank">${i + 1}</td>
          <td class="cp-partner">${esc(p.iso3)}</td>
          <td class="cp-flow">${esc(flow)}</td>
          <td class="cp-tval">${esc(val)}</td>
          <td class="cp-tdep">${dep}</td>
        </tr>
      `;
    }).join('');

    return `
      <div class="cp-trade-block">
        <div class="cp-trade-head">
          <span class="cp-badge">${esc(HS_LABELS[hs] ?? hs)}</span>
          <span class="cp-trade-period">${esc(block.period ?? '')}</span>
        </div>
        <table class="cp-trade-table">
          <thead>
            <tr>
              <th>#</th><th>국가</th><th>방향</th><th>금액</th><th>의존도</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    `;
  }).join('');
}

function renderSanctions(data) {
  const list = data.sanctions ?? [];
  if (!list.length) {
    return `<div class="cp-empty">해당 제재 레짐 없음</div>`;
  }

  return list.map(s => {
    const bodies  = (s.sanctioning_bodies ?? []).join(' · ');
    const sectors = (s.sectors ?? []).slice(0, 4).join(', ');
    const tags    = (s.theory_tags ?? []).slice(0, 3)
      .map(t => `<span class="cp-tag">${esc(t)}</span>`).join('');

    const severity = s.severity ?? 0;
    const sevClass = severity >= 90 ? 'cp-sev-crit'
                   : severity >= 70 ? 'cp-sev-high'
                   : severity >= 50 ? 'cp-sev-mid'
                   : 'cp-sev-low';

    return `
      <div class="cp-sanction-card">
        <div class="cp-sanction-header">
          <span class="cp-sanction-name">${esc(s.target_name ?? s.id)}</span>
          <span class="cp-severity ${sevClass}">${severity}</span>
        </div>
        <div class="cp-sanction-meta">
          <span class="cp-key">제재국:</span> ${esc(bodies)}
          · <span class="cp-key">개시:</span> ${esc(s.year_established ?? '?')}
        </div>
        <div class="cp-sanction-sectors">${esc(sectors)}</div>
        <div class="cp-sanction-desc">${esc(s.description ?? '')}</div>
        <div class="cp-sanction-tags">${tags}</div>
      </div>
    `;
  }).join('');
}

function renderTheories(data) {
  const list = data.theories ?? [];
  if (!list.length) {
    return `<div class="cp-empty">관련 이론 없음 (지역 코드 미매칭)</div>`;
  }

  const useOrder = { case_study: 0, norm: 1, concept: 2, data: 3 };
  const useLabelMap = { case_study: '사례', norm: '제도·규범', concept: '개념', data: '데이터' };

  return list.map(t => {
    const sectorHtml = `<span class="cp-sector cp-sector--${esc(t.sector_tag)}">${esc(t.sector_tag)}</span>`;
    const useLabel   = useLabelMap[t.use_case] ?? t.use_case;
    return `
      <div class="cp-theory-card">
        <div class="cp-theory-header">
          <span class="cp-theory-title">${esc(t.title)}</span>
          <span class="cp-use-case">${esc(useLabel)}</span>
        </div>
        <div class="cp-theory-meta">${sectorHtml}</div>
        <div class="cp-theory-summary">${esc(t.summary ?? '')}</div>
      </div>
    `;
  }).join('');
}

// ── 유틸 ────────────────────────────────────────────────────────────────────

function _sparkline(series) {
  if (series.length < 2) return '';
  const vals = series.map(s => s.value);
  const min  = Math.min(...vals);
  const max  = Math.max(...vals);
  const range = max - min || 1;
  const W = 280, H = 30;
  const pts = vals.map((v, i) => {
    const x = (i / (vals.length - 1)) * W;
    const y = H - ((v - min) / range) * H;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
  return `
    <svg class="cp-spark" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}">
      <polyline points="${pts}" fill="none" stroke="#58a6ff" stroke-width="1.2" opacity="0.7"/>
    </svg>
  `;
}

function _changePct(series) {
  if (series.length < 2) return null;
  const first = series[0].value;
  const last  = series[series.length - 1].value;
  if (!first) return null;
  return ((last - first) / first) * 100;
}

function _formatUsd(v) {
  if (v >= 1e9) return `${(v / 1e9).toFixed(1)}B`;
  if (v >= 1e6) return `${(v / 1e6).toFixed(1)}M`;
  if (v >= 1e3) return `${(v / 1e3).toFixed(0)}K`;
  return v.toFixed(0);
}

// ── 패널 쉘 HTML ─────────────────────────────────────────────────────────────

function buildShell(name_ko, name_en) {
  const tabsHtml = TAB_DEFS.map((t, i) =>
    `<button class="cp-tab ${i === 0 ? 'is-active' : ''}" data-tab="${t.id}">${t.label}</button>`
  ).join('');

  return `
    <div class="cp-header">
      <div class="cp-header-meta">
        <span class="cp-label">🌏 국가 정보</span>
        <button class="cp-close" title="닫기 (ESC)">✕</button>
      </div>
      <div class="cp-title">${esc(name_ko)}</div>
      <div class="cp-subtitle">${esc(name_en)}</div>
    </div>
    <div class="cp-tabs">${tabsHtml}</div>
    <div class="cp-body">
      <div class="cp-loading">⌛ 로딩 중…</div>
    </div>
  `;
}

// ── 컴포넌트 ─────────────────────────────────────────────────────────────────

export class CountryPanelView {
  /** @param {import('../core/EventBus.js').EventBus} eventBus */
  constructor(eventBus) {
    this._bus      = eventBus;
    this._el       = null;
    this._activeTab = 'info';
    this._data     = null;
  }

  mount(containerId) {
    this._el = document.getElementById(containerId);
    if (!this._el) return;

    this._bus.on('country:open', ({ iso3, name_en }) => this._open(iso3, name_en));
    this._bus.on('marker:close', () => this._close());

    document.addEventListener('keydown', e => {
      if (e.key === 'Escape') this._close();
    });
  }

  _close() {
    this._el?.classList.remove('is-open');
    this._data     = null;
    this._activeTab = 'info';
  }

  async _open(iso3, name_en) {
    if (!this._el) return;

    this._activeTab = 'info';
    this._data      = null;

    // 즉시 쉘 표시
    const nameFallback = iso3;
    this._el.innerHTML = buildShell(nameFallback, name_en || iso3);
    this._el.classList.add('is-open');

    this._el.querySelector('.cp-close')
      ?.addEventListener('click', () => this._close(), { once: true });

    // 탭 클릭 바인딩
    this._el.querySelectorAll('.cp-tab').forEach(btn => {
      btn.addEventListener('click', () => {
        this._activeTab = btn.dataset.tab;
        this._el.querySelectorAll('.cp-tab').forEach(b => b.classList.remove('is-active'));
        btn.classList.add('is-active');
        this._renderTab();
      });
    });

    // API 호출
    let data;
    try {
      data = await api.get(`/api/country/${encodeURIComponent(iso3)}`);
    } catch (err) {
      this._showError(`국가 API 오류: ${err.message}`);
      return;
    }

    this._data = data;

    // 쉘 헤더를 실제 데이터로 교체
    this._el.querySelector('.cp-title').textContent = data.name_ko || iso3;
    this._el.querySelector('.cp-subtitle').textContent = data.name_en || '';

    this._renderTab();
  }

  _renderTab() {
    const body = this._el?.querySelector('.cp-body');
    if (!body) return;

    if (!this._data) {
      body.innerHTML = '<div class="cp-loading">⌛ 로딩 중…</div>';
      return;
    }

    switch (this._activeTab) {
      case 'info':     body.innerHTML = renderInfo(this._data);     break;
      case 'macro':    body.innerHTML = renderMacro(this._data);    break;
      case 'trade':    body.innerHTML = renderTrade(this._data);    break;
      case 'sanction': body.innerHTML = renderSanctions(this._data); break;
      case 'theory':   body.innerHTML = renderTheories(this._data); break;
      default:         body.innerHTML = '';
    }
  }

  _showError(msg) {
    const body = this._el?.querySelector('.cp-body');
    if (body) body.innerHTML = `<p class="cp-error">${esc(msg)}</p>`;
  }
}
