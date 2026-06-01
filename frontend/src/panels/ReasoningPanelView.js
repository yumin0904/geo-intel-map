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
      const inds = data.indicators ?? data.tickers ?? [];
      if (!inds.length) return data.error ? `⚠️ ${data.error}` : '데이터 없음';
      return inds.slice(0, 3).map(t => {
        const arrow = t.direction === 'up' ? '▲' : (t.direction === 'down' ? '▼' : '─');
        const name = t.label ?? t.ticker ?? t.indicator ?? '?';
        return `${name} ${arrow}${Math.abs(t.change_pct ?? 0).toFixed(1)}%`;
      }).join(' · ');
    }
    case '5_intent': {
      if (!data || data.error) return '데이터 없음';
      const label = data.intent_label_ko ?? '불명확';
      const tone  = data.tone_label_ko ?? '';
      const esc   = data.escalation_risk ? ' ⚠️에스컬레이션위험' : '';
      return `${label} · 톤: ${tone}${esc}`;
    }
    case '6_sanctions': {
      const list = data.active_sanctions ?? [];
      if (!list.length) return '관련 제재 없음';
      return list.slice(0, 2).map(s => s.issuer || s.name || s.id).join(', ');
    }
    case '7_cascade': {
      const chain = data.cascade_chain ?? [];
      if (!chain.length) return 'Cascade 연결 없음';
      const maxDepth = Math.max(...chain.map(c => c.depth ?? 1));
      const depthBadge = maxDepth >= 3 ? ' 🟠D3' : maxDepth === 2 ? ' 🟡D2' : '';
      return `인과 링크 ${chain.length}개${depthBadge}`;
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
    case '3_history': {
      const analogueLines = (data.analogues ?? []).map(a =>
        `▸ ${a.title_ko} (${(a.date ?? '').slice(0, 4)})\n  ${a.lessons_ko ?? ''}`
      );
      const briefingLines = (data.briefing_refs ?? []).map(b => {
        const org  = b.source_org  ? `[${b.source_org}] ` : '';
        const date = b.published_date ? ` (${b.published_date.slice(0, 7)})` : '';
        return `📋 ${org}${b.title}${date}`;
      });
      const all = [...analogueLines, ...(briefingLines.length ? ['── 관련 브리핑 ──', ...briefingLines] : [])];
      return all.join('\n\n') || null;
    }

    case '4_macro': {
      const inds = data.indicators ?? data.tickers ?? [];
      const src  = data.source ?? '';
      const lines = inds.map(t => {
        const sign  = (t.change_pct ?? 0) >= 0 ? '+' : '';
        const arrow = t.direction === 'up' ? '▲' : (t.direction === 'down' ? '▼' : '─');
        const name  = t.label ?? t.ticker ?? t.indicator ?? '?';
        const val   = t.value ?? t.price;
        const valStr = val != null ? ` ${val.toLocaleString()}` : '';
        return `${name}:${valStr} ${arrow}${sign}${(t.change_pct ?? 0).toFixed(2)}%`;
      });
      if (src) lines.push(`출처: ${src}`);
      return lines.join('\n') || null;
    }

    case '5_intent': {
      if (!data) return null;
      const lines = [];
      lines.push(`의도: ${data.intent_label_ko ?? '불명확'} (${data.intent_label ?? ''})`);
      lines.push(`GKG 톤: ${data.tone ?? 0} (${data.tone_label_ko ?? ''})`);
      if (data.gkg_hostility_confirmed) lines.push('⚠️ GKG 적대성 확인됨');
      if ((data.matched_themes ?? []).length) {
        lines.push(`테마: ${data.matched_themes.join(', ')}`);
      }
      lines.push('');
      for (const p of (data.actor_postures ?? [])) {
        const posture = p.strategic_posture === 'revisionist' ? '🔴수정주의' : '🟢현상유지';
        lines.push(`▸ ${p.iso3}: ${posture} · 권력수단: ${p.instrument_of_power}`);
      }
      if (data.escalation_risk) {
        lines.push('');
        lines.push('🚨 에스컬레이션 위험: 수정주의 행위자 + 적대 톤 + 공세 의도 복합 감지');
      }
      if (data.theory_ref) {
        lines.push('');
        lines.push(`이론: ${data.theory_name}`);
        lines.push(data.theory_ref);
      }
      lines.push(`출처: ${data.source_note ?? ''}`);
      return lines.join('\n') || null;
    }

    case '6_sanctions':
      return (data.active_sanctions ?? []).map(s => {
        const sectors = (s.sectors ?? []).slice(0, 3).join(', ');
        return `▸ ${s.issuer || s.target_country || ''} → ${s.name || s.id}\n  분야: ${sectors}`;
      }).join('\n\n') || null;

    case '8_alliance': {
      const lines = [];
      // 동맹 목록
      for (const a of (data.relevant_alliances ?? [])) {
        lines.push(`▸ ${a.name_ko} (${a.type})\n  ${a.notes_ko ?? ''}`);
      }
      // 무역 의존도 (Weaponized Interdependence)
      const deps = data.trade_dependencies ?? [];
      if (deps.length) {
        lines.push('');
        lines.push('── 무역 의존도 (Weaponized Interdependence) ──');
        for (const dep of deps) {
          lines.push(`${dep.reporter} → ${dep.partner}`);
          for (const item of (dep.items ?? [])) {
            const pct = (item.dependency_ratio * 100).toFixed(1);
            lines.push(`  ${item.hs_label} (${item.flow}) ${pct}%`);
          }
        }
      }
      // 잠재 연루국
      const countries = data.potentially_involved_countries ?? [];
      if (countries.length) {
        lines.push('');
        lines.push(`잠재 연루국: ${countries.join(', ')}`);
      }
      return lines.join('\n') || null;
    }

    case '7_cascade':
      return (data.cascade_chain ?? []).map(c => {
        const depth = c.depth ?? 1;
        const badge = depth >= 3 ? '🟠D3' : depth === 2 ? '🟡D2' : '⬜D1';
        const score = ((c.correlation_score ?? 0) * 100).toFixed(0);
        return `${badge} ${c.source_id?.slice(0, 8)} → ${c.target_id?.slice(0, 8)}\n  상관 ${score}% · ${c.time_delta_hours ?? '?'}h 후`;
      }).join('\n') || null;

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

// ── 체인 검증 렌더링 (P5-6) ──────────────────────────────────────────────
const _VERDICT_STYLE = {
  supported:   { icon: '✅', color: '#00c896', label: '지지됨' },
  contested:   { icon: '⚠️', color: '#f4a261', label: '논쟁적' },
  unsupported: { icon: '❌', color: '#e63946', label: '반증' },
};

const _CLAIM_TYPE_KO = {
  cascade: '인과 체인',
  intent:  '의도·포지션',
  alliance:'동맹 확산',
  history: '역사 선례',
};

function _renderChainVerification(cv) {
  if (cv.error) return `<div class="cv-error">검증 실패: ${escHtml(cv.error)}</div>`;

  const vs = _VERDICT_STYLE[cv.verdict] ?? _VERDICT_STYLE.contested;
  const pct = Math.round((cv.chain_confidence ?? 0) * 100);

  const claimRows = (arr, cssClass) => arr.map(c => `
    <div class="cv-claim ${cssClass}">
      <span class="cv-claim__type">${escHtml(_CLAIM_TYPE_KO[c.type] ?? c.type)}</span>
      <span class="cv-claim__desc">${escHtml(c.description)}</span>
      <div class="cv-claim__evidence">${escHtml(c.evidence)}</div>
    </div>
  `).join('');

  const supported   = claimRows(cv.supported ?? [],   'cv-claim--supported');
  const refuted     = claimRows(cv.refuted ?? [],     'cv-claim--refuted');
  const unverified  = claimRows(cv.unverified ?? [],  'cv-claim--unverified');

  return `
    <div class="cv-header">
      <span class="cv-verdict" style="color:${vs.color}">${vs.icon} ${vs.label}</span>
      <span class="cv-confidence">신뢰도 ${pct}%</span>
    </div>
    <div class="cv-bar"><div class="cv-bar__fill" style="width:${pct}%;background:${vs.color}"></div></div>
    ${supported}${refuted}${unverified}
    <div class="cv-note">${escHtml(cv.note_ko ?? '')}</div>
  `;
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
      const summary   = summarizeStage(key, stageData);
      const detail    = buildDetailLines(key, stageData);

      row.querySelector('.rs-stage__check').textContent   = '✅';
      row.querySelector('.rs-stage__summary').textContent = summary;
      row.classList.add('is-done');

      if (detail) {
        row.querySelector('.rs-stage__detail').textContent = detail;
        row.querySelector('.rs-stage__arrow').classList.remove('rs-stage__arrow--hidden');
        row.classList.add('has-detail');  // CSS: cursor:pointer + hover bg
        row.addEventListener('click', () => row.classList.toggle('is-expanded'));
      }
    }

    // ── 체인 검증 결과 (P5-6) ────────────────────────────────────────
    if (report.chain_verification) {
      const cv = report.chain_verification;
      const body = this._el.querySelector('.reasoning-panel__body');
      const cvEl = document.createElement('div');
      cvEl.className = 'chain-verify';
      cvEl.innerHTML = _renderChainVerification(cv);
      body?.appendChild(cvEl);
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
