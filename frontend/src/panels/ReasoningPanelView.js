/**
 * ReasoningPanelView.js
 * 8단계 지정학 추론 패널.
 *
 * 흐름:
 *   마커 클릭 → 팝업 [🤖 AI 분析] 버튼 → reasoning:open 이벤트 → 우측 슬라이드인
 *   API 응답 도착 후 단계별 0.4s 간격 순차 표시 → [분석실에서 열기] 버튼
 *
 * EventBus 이벤트:
 *   수신: reasoning:open  { event_id, title }
 *   수신: marker:close    (ESC·지도 클릭)
 *   발신: sandbox:toggle  { event_id, report }  (분석실 버튼 클릭 시)
 */

import { api } from '../services/api.js';

// ── 8단계 메타데이터 ─────────────────────────────────────────────────────
const STAGE_META = [
  { num: 1, key: '1_facts',     icon: '🔍', label: '사건 팩트' },
  { num: 2, key: '2_sector',    icon: '🏷', label: '섹터 분류' },
  { num: 3, key: '3_history',   icon: '📜', label: '역사적 비교' },
  { num: 4, key: '4_macro',     icon: '📈', label: '거시 변수' },
  { num: 5, key: '5_intent',    icon: '🎯', label: '명분과 의도' },
  { num: 6, key: '6_sanctions', icon: '⚖', label: '제도적 저항' },
  { num: 7, key: '7_cascade',   icon: '⛓', label: '시간적 추이' },
  { num: 8, key: '8_alliance',  icon: '🤝', label: '동맹 확산' },
];

// ── 단계별 1줄 요약 생성 ──────────────────────────────────────────────────
function summarizeStage(key, data) {
  if (!data)        return '—';
  if (data.error)   return `⚠️ ${data.error}`;

  switch (key) {
    case '1_facts': {
      const actors = (data.actors ?? []).filter(Boolean).join(' vs ');
      const sev    = data.severity ?? '?';
      const imp    = Math.round((data.importance_score ?? 0) * 100);
      return actors ? `${actors} · sev ${sev} · imp ${imp}%` : `sev ${sev} · imp ${imp}%`;
    }
    case '2_sector': {
      const tags = [...new Set([
        ...(data.explicit_tags    ?? []),
        ...(data.inferred_sectors ?? []),
      ])].slice(0, 3);
      return tags.length ? tags.join(' · ') : (data.primary_sector ?? '—');
    }
    case '3_history': {
      const analogues = data.analogues ?? [];
      if (!analogues.length) return '유사 사례 없음';
      return analogues.slice(0, 2).map(a => a.title_ko).join(', ');
    }
    case '4_macro': {
      const tickers = data.tickers ?? [];
      if (!tickers.length) return data.error ? `⚠️ ${data.error}` : '데이터 없음';
      return tickers.slice(0, 3).map(t => {
        const arrow = t.direction === 'up' ? '▲' : (t.direction === 'down' ? '▼' : '─');
        return `${t.ticker} ${arrow}${Math.abs(t.change_pct).toFixed(1)}%`;
      }).join(' · ');
    }
    case '5_intent':
      return 'Phase 4 구현 예정';
    case '6_sanctions': {
      const list = data.active_sanctions ?? [];
      if (!list.length) return '관련 제재 없음';
      return list.slice(0, 2).map(s => s.issuer || s.name || s.id).join(', ');
    }
    case '7_cascade': {
      const n = (data.cascade_chain ?? []).length;
      return n ? `인과 링크 ${n}개` : 'Cascade 연결 없음';
    }
    case '8_alliance': {
      const list = data.relevant_alliances ?? [];
      if (!list.length) return '관련 동맹 없음';
      return list.slice(0, 3).map(a => a.name_ko).join(' · ');
    }
    default: return '—';
  }
}

// ── 단계별 상세 텍스트 (클릭으로 펼치기) ────────────────────────────────
function buildDetailLines(key, data) {
  if (!data || data.error) return null;

  switch (key) {
    case '3_history':
      return (data.analogues ?? []).map(a =>
        `▸ ${a.title_ko} (${(a.date ?? '').slice(0, 4)})\n  ${a.lessons_ko ?? ''}`
      ).join('\n\n') || null;

    case '4_macro':
      return (data.tickers ?? []).map(t => {
        const sign  = t.change_pct >= 0 ? '+' : '';
        const arrow = t.direction === 'up' ? '▲' : (t.direction === 'down' ? '▼' : '─');
        return `${t.ticker}: $${t.price} ${arrow}${sign}${t.change_pct.toFixed(2)}%`;
      }).join('\n') || null;

    case '6_sanctions':
      return (data.active_sanctions ?? []).map(s => {
        const sectors = (s.sectors ?? []).slice(0, 3).join(', ');
        return `▸ ${s.issuer || s.target_country || ''} → ${s.name || s.id}\n  분야: ${sectors}`;
      }).join('\n\n') || null;

    case '8_alliance':
      return (data.relevant_alliances ?? []).map(a =>
        `▸ ${a.name_ko} (${a.type})\n  ${a.notes_ko ?? ''}`
      ).join('\n\n') || null;

    case '7_cascade':
      return (data.cascade_chain ?? []).map(c =>
        `▸ ${c.source_id?.slice(0, 8)} → ${c.target_id?.slice(0, 8)}\n  상관 ${((c.correlation_score ?? 0) * 100).toFixed(0)}% · ${c.time_delta_hours}h 후`
      ).join('\n') || null;

    default:
      return null;
  }
}

// ── 패널 HTML 빌더 ───────────────────────────────────────────────────────
function buildShell(title) {
  const stagesHTML = STAGE_META.map(({ num, icon, label }) => `
    <div class="rs-stage" data-stage="${num}">
      <span class="rs-stage__check">⬜</span>
      <div class="rs-stage__main">
        <div class="rs-stage__header">
          <span class="rs-stage__num">${num}</span>
          <span class="rs-stage__icon">${icon}</span>
          <span class="rs-stage__label">${label}</span>
          <span class="rs-stage__arrow rs-stage__arrow--hidden">▸</span>
        </div>
        <div class="rs-stage__summary">대기 중…</div>
        <pre class="rs-stage__detail"></pre>
      </div>
    </div>
  `).join('');

  return `
    <div class="reasoning-panel__header">
      <div class="reasoning-panel__header-meta">
        <span class="reasoning-panel__label">🤖 8단계 추론</span>
        <button class="reasoning-panel__close" title="닫기 (ESC)">✕</button>
      </div>
      <div class="reasoning-panel__event-title">${escHtml(title ?? '이벤트')}</div>
      <div class="reasoning-panel__subtitle">Geopolitical Cascade Reasoning</div>
    </div>
    <div class="reasoning-panel__body">
      <div class="rs-stages">${stagesHTML}</div>
    </div>
    <div class="reasoning-panel__footer"></div>
  `;
}

function escHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// ── 컴포넌트 ─────────────────────────────────────────────────────────────
export class ReasoningPanelView {
  /** @param {import('../core/EventBus.js').EventBus} eventBus */
  constructor(eventBus) {
    this._eventBus = eventBus;
    this._el = null;
  }

  mount(containerId) {
    this._el = document.getElementById(containerId);
    if (!this._el) return;

    this._eventBus.on('reasoning:open', ({ event_id, title }) => this._open(event_id, title));
    this._eventBus.on('marker:close',   () => this._close());

    document.addEventListener('keydown', e => {
      if (e.key === 'Escape') this._close();
    });
  }

  _close() {
    this._el?.classList.remove('is-open');
  }

  async _open(event_id, title) {
    if (!this._el) return;

    // 즉시 로딩 셸 표시
    this._el.innerHTML = buildShell(title);
    this._el.classList.add('is-open');

    this._el.querySelector('.reasoning-panel__close')
      ?.addEventListener('click', () => this._close(), { once: true });

    // ── API 호출 ──────────────────────────────────────────────────────
    let report;
    try {
      report = await api.get(`/api/reasoning/${encodeURIComponent(event_id)}`);
    } catch (err) {
      this._showError(`추론 API 오류: ${err.message}`);
      return;
    }

    if (!report?.stages) {
      this._showError('추론 결과가 없습니다.');
      return;
    }

    // ── 단계별 순차 표시 (0.4s 간격) ─────────────────────────────────
    for (const { num, key } of STAGE_META) {
      await new Promise(r => setTimeout(r, 400));

      const row = this._el.querySelector(`.rs-stage[data-stage="${num}"]`);
      if (!row) continue;

      const stageData = report.stages[key];
      const isPhase4  = key === '5_intent';
      const summary   = summarizeStage(key, stageData);
      const detail    = buildDetailLines(key, stageData);

      row.querySelector('.rs-stage__check').textContent   = isPhase4 ? '⬜' : '✅';
      row.querySelector('.rs-stage__summary').textContent = summary;
      row.classList.add('is-done');

      if (detail) {
        row.querySelector('.rs-stage__detail').textContent = detail;
        row.querySelector('.rs-stage__arrow').classList.remove('rs-stage__arrow--hidden');
        row.classList.add('has-detail');  // CSS: cursor:pointer + hover bg
        row.addEventListener('click', () => row.classList.toggle('is-expanded'));
      }
    }

    // ── 완료 푸터 ─────────────────────────────────────────────────────
    const footer = this._el.querySelector('.reasoning-panel__footer');
    if (!footer) return;

    const elapsed = report.elapsed_sec?.toFixed(2) ?? '?';
    footer.innerHTML = `
      <div class="rs-footer">
        <span class="rs-footer__time">⏱ ${elapsed}s 완료</span>
        <button class="rs-footer__btn">🔬 분석실에서 열기</button>
      </div>
    `;

    footer.querySelector('.rs-footer__btn')?.addEventListener('click', () => {
      this._eventBus.emit('sandbox:toggle', { event_id, report });
      this._close();
    }, { once: true });
  }

  _showError(msg) {
    const body = this._el?.querySelector('.reasoning-panel__body');
    if (body) body.innerHTML = `<p class="rs-error">${escHtml(msg)}</p>`;
  }
}
