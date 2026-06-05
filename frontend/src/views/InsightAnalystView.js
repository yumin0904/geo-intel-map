/**
 * InsightAnalystView — 인사이트 분석실 탭.
 * 저장 기능: 분석 완료 후 💾 저장 버튼 → POST /api/intel/save
 * 히스토리: 좌측 패널에서 과거 분석 목록 조회·불러오기·삭제
 */

import { api } from '../services/api.js';

const BASE = api.BASE_URL;

const SECTOR_LABEL = {
  maritime:     '🌊 해양',
  energy:       '⚡ 에너지',
  techno:       '💻 기술패권',
  indo_pacific: '🌏 인도-태평양',
  gray_zone:    '🌫 회색지대',
  cyber:        '🔒 사이버',
};

const MODE_CONFIG = {
  insight:      { icon: '💡', label: '인사이트 발굴' },
  presentation: { icon: '📊', label: '발표 주제 추천' },
  verify:       { icon: '✓',  label: '가설 검증' },
};

export class InsightAnalystView {
  constructor() {
    this._pane        = null;
    this._abortCtrl   = null;
    this._rendered    = false;
    this._lastResult  = null;   // { query, mode, regions, sectors, result_md, context_chars }
    this._lastMeta    = null;
    this._lastScore   = null;   // §19-D confidence score result
  }

  mount(pane) {
    this._pane = pane;
    if (!this._rendered) {
      pane.innerHTML = this._template();
      this._bindEvents();
      this._loadHistory();
      this._rendered = true;
    }
  }

  // ── 템플릿 ────────────────────────────────────────────────────────────────

  _template() {
    return `
      <div class="ia__layout">

        <!-- 좌측: 히스토리 패널 -->
        <aside class="ia__history-panel">
          <div class="ia__history-header">
            <span>📂 저장된 분석</span>
          </div>
          <div class="ia__history-list" id="ia-history-list">
            <div class="ia__history-empty">분석 결과를 저장하면<br>여기에 표시됩니다.</div>
          </div>
        </aside>

        <!-- 우측: 메인 영역 -->
        <div class="ia__main">

          <!-- 입력 영역 -->
          <div class="ia__input-area">
            <textarea
              class="ia__query-input"
              id="ia-query-input"
              placeholder="분석 질문을 입력하세요.&#10;예) 러시아-우크라이나 전쟁에 대해 발표하려고 해. 새로운 인사이트를 중심으로 발표 주제를 선정해줘."
              rows="3"
            ></textarea>

            <div class="ia__controls">
              <div class="ia__mode-btns">
                <button class="ia__mode-btn is-active" data-mode="insight">💡 인사이트</button>
                <button class="ia__mode-btn" data-mode="presentation">📊 발표 주제</button>
                <button class="ia__mode-btn" data-mode="verify">✓ 검증</button>
              </div>
              <div class="ia__action-btns">
                <button class="ia__save-btn" id="ia-save-btn" style="display:none">💾 저장</button>
                <button class="ia__submit-btn" id="ia-submit-btn">분석 시작 ▶</button>
              </div>
            </div>
          </div>

          <!-- 메타 바 -->
          <div class="ia__meta-bar" id="ia-meta-bar" style="display:none"></div>

          <!-- 결과 영역 -->
          <div class="ia__result-area" id="ia-result-area">
            <div class="ia__placeholder">
              <div class="ia__placeholder-icon">🧠</div>
              <p>질문을 입력하고 <strong>분석 시작</strong>을 누르세요.</p>
              <p class="ia__placeholder-hint">
                브리핑 원문 57개 · ACLED 252,409건 · Cascade 룰 22개 교차 분석
              </p>
            </div>
          </div>

        </div>
      </div>
    `;
  }

  // ── 이벤트 바인딩 ─────────────────────────────────────────────────────────

  _bindEvents() {
    const p = this._pane;

    p.querySelectorAll('.ia__mode-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        p.querySelectorAll('.ia__mode-btn').forEach(b => b.classList.remove('is-active'));
        btn.classList.add('is-active');
      });
    });

    p.querySelector('#ia-submit-btn').addEventListener('click', () => this._run());

    p.querySelector('#ia-query-input').addEventListener('keydown', e => {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); this._run(); }
    });

    p.querySelector('#ia-save-btn').addEventListener('click', () => this._save());
  }

  // ── 분석 실행 ─────────────────────────────────────────────────────────────

  async _run() {
    const p      = this._pane;
    const query  = p.querySelector('#ia-query-input').value.trim();
    if (!query) return;

    const mode = p.querySelector('.ia__mode-btn.is-active')?.dataset.mode ?? 'insight';

    if (this._abortCtrl) this._abortCtrl.abort();
    this._abortCtrl = new AbortController();

    const submitBtn  = p.querySelector('#ia-submit-btn');
    const saveBtn    = p.querySelector('#ia-save-btn');
    const metaBar    = p.querySelector('#ia-meta-bar');
    const resultArea = p.querySelector('#ia-result-area');

    submitBtn.disabled    = true;
    submitBtn.textContent = '분석 중...';
    saveBtn.style.display = 'none';
    metaBar.style.display = 'none';
    this._lastResult      = null;
    this._lastMeta        = null;

    resultArea.innerHTML = `
      <pre class="ia__stream-pre" id="ia-stream-pre"></pre>
      <div class="ia__md-output" id="ia-md-output" style="display:none"></div>
    `;
    const preEl = resultArea.querySelector('#ia-stream-pre');
    const mdEl  = resultArea.querySelector('#ia-md-output');

    const startedAt = Date.now();
    const timerEl   = document.createElement('div');
    timerEl.className = 'ia__timer';
    resultArea.prepend(timerEl);
    const timerTick = setInterval(() => {
      timerEl.textContent = `⏱ ${((Date.now() - startedAt) / 1000).toFixed(1)}s 분석 중...`;
    }, 200);

    let mdText = '', buffer = '', metaSet = false, streamDone = false;
    this._lastScore = null;

    try {
      const resp = await fetch(`${BASE}/api/intel/query`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, mode_override: mode }),
        signal: this._abortCtrl.signal,
      });
      if (!resp.ok) throw new Error(`API ${resp.status}`);

      const reader  = resp.body.getReader();
      const decoder = new TextDecoder();

      while (!streamDone) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop();

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          let payload;
          try { payload = JSON.parse(line.slice(6)); } catch { continue; }

          if (payload.type === 'meta' && !metaSet) {
            this._renderMeta(metaBar, payload);
            metaBar.style.display = '';
            timerEl.style.display = 'none';
            this._lastMeta = payload;
            metaSet = true;
            continue;
          }

          if (payload.type === 'score') {
            this._lastScore = payload;
            this._renderScore(metaBar, payload);
            continue;
          }

          if (payload.type === 'hypothesis') {
            this._renderHypotheses(resultArea, payload.hypotheses ?? []);
            continue;
          }

          if (payload.fallback) {
            preEl.insertAdjacentHTML('beforebegin',
              '<div class="ia__notice">⚡ Thinking 일시 과부하 → 일반 모드 전환</div>');
            continue;
          }

          if (payload.text && !payload.done) {
            mdText += payload.text;
            preEl.textContent = mdText;
            resultArea.scrollTop = resultArea.scrollHeight;
          }

          if (payload.done) {
            clearInterval(timerTick);
            timerEl.remove();
            this._finishRender(preEl, mdEl, resultArea, mdText);

            this._lastResult = {
              query, mode,
              regions: this._lastMeta?.regions ?? [],
              sectors: this._lastMeta?.sectors ?? [],
              result_md: mdText,
              context_chars: Object.values(this._lastMeta?.source_counts ?? {})
                               .reduce((a, b) => a + b, 0),
              confidence_score: this._lastScore?.confidence ?? null,
            };
            saveBtn.style.display = '';
            streamDone = true;
            break;
          }
        }
      }

      // done 이벤트 없이 스트림 종료된 경우 fallback 렌더링
      clearInterval(timerTick);
      if (timerEl.isConnected) timerEl.remove();
      if (mdText && preEl.style.display !== 'none') {
        this._finishRender(preEl, mdEl, resultArea, mdText);
        this._lastResult = { query, mode, regions: [], sectors: [], result_md: mdText, context_chars: 0 };
        saveBtn.style.display = '';
      }

    } catch (err) {
      clearInterval(timerTick);
      if (timerEl.isConnected) timerEl.remove();
      if (err.name !== 'AbortError') {
        resultArea.innerHTML = `<div class="ia__error">⚠️ 오류: ${err.message}</div>`;
      }
    } finally {
      submitBtn.disabled    = false;
      submitBtn.textContent = '분석 시작 ▶';
    }
  }

  // ── 렌더링 완료 처리 ───────────────────────────────────────────────────────

  _finishRender(preEl, mdEl, resultArea, mdText) {
    preEl.style.display = 'none';

    // marked.js 파싱 — 실패 시 <pre>로 fallback
    let html;
    try {
      html = window.marked ? window.marked.parse(mdText) : null;
    } catch (e) {
      html = null;
    }

    if (html) {
      mdEl.innerHTML = html;
    } else {
      // marked 없거나 파싱 실패 → pre 그대로 보여줌
      preEl.style.display = '';
      mdEl.style.display = 'none';
      return;
    }
    mdEl.style.display = '';

    // 완료 푸터: 수신 글자 수 + 📋 복사 버튼
    const footer = document.createElement('div');
    footer.className = 'ia__footer';
    footer.innerHTML = `
      <span class="ia__footer-info">✅ 분석 완료 · ${mdText.length.toLocaleString()}자 수신</span>
      <button class="ia__copy-btn" title="마크다운 원문 복사">📋 복사</button>
    `;
    footer.querySelector('.ia__copy-btn').addEventListener('click', () => {
      navigator.clipboard.writeText(mdText).then(() => {
        const btn = footer.querySelector('.ia__copy-btn');
        btn.textContent = '✅ 복사됨';
        setTimeout(() => { btn.textContent = '📋 복사'; }, 2000);
      });
    });
    resultArea.appendChild(footer);

    // 맨 위(처음)에서 시작 — 스크롤 없이 전체 내용 접근 가능
    resultArea.scrollTop = 0;
  }

  // ── 저장 ──────────────────────────────────────────────────────────────────

  async _save() {
    if (!this._lastResult) return;
    const saveBtn = this._pane.querySelector('#ia-save-btn');
    saveBtn.disabled    = true;
    saveBtn.textContent = '저장 중...';
    try {
      const resp = await fetch(`${BASE}/api/intel/save`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify(this._lastResult),
      });
      if (!resp.ok) {
        // 422 완결성 검사 실패: 이유 파싱 후 재시도 버튼 표시
        if (resp.status === 422) {
          const err = await resp.json().catch(() => ({}));
          const reason = err.detail ?? '인사이트 미완성';
          saveBtn.textContent = '⚠️ 저장 실패';
          saveBtn.disabled = false;
          this._showSaveFailReason(reason);
        } else {
          throw new Error(`${resp.status}`);
        }
        return;
      }
      const data = await resp.json();
      saveBtn.textContent = '✅ 저장됨';
      saveBtn.disabled = true;
      this._hideSaveFailBanner();
      this._loadHistory();
    } catch (e) {
      saveBtn.textContent = '⚠️ 저장 실패';
      saveBtn.disabled = false;
    }
  }

  _showSaveFailReason(reason) {
    const resultArea = this._pane.querySelector('#ia-result-area');
    let banner = this._pane.querySelector('#ia-save-fail-banner');
    if (!banner) {
      banner = document.createElement('div');
      banner.id = 'ia-save-fail-banner';
      banner.className = 'ia__save-fail-banner';
      resultArea.prepend(banner);
    }
    banner.innerHTML = `
      <span class="ia__save-fail-icon">⚠️</span>
      <span class="ia__save-fail-reason">${reason}</span>
      <button class="ia__save-fail-retry" id="ia-save-fail-retry">🔄 재분석</button>
    `;
    // 재분석 버튼: 동일 쿼리 재실행 (인사이트 미완성 시 Gemini 재생성)
    banner.querySelector('#ia-save-fail-retry').addEventListener('click', () => {
      this._hideSaveFailBanner();
      const submitBtn = this._pane.querySelector('#ia-submit-btn');
      submitBtn.click();
    });
  }

  _hideSaveFailBanner() {
    this._pane.querySelector('#ia-save-fail-banner')?.remove();
  }

  // ── 히스토리 로드 ─────────────────────────────────────────────────────────

  async _loadHistory() {
    const listEl = this._pane?.querySelector('#ia-history-list');
    if (!listEl) return;
    try {
      const resp = await fetch(`${BASE}/api/intel/history`);
      const data = await resp.json();
      if (!data.length) {
        listEl.innerHTML = '<div class="ia__history-empty">저장된 분석이 없습니다.</div>';
        return;
      }
      listEl.innerHTML = data.map(item => `
        <div class="ia__history-item" data-id="${item.id}">
          <div class="ia__history-title">${item.title}</div>
          <div class="ia__history-meta">
            ${(MODE_CONFIG[item.mode]?.icon ?? '💡')} ${item.mode}
            · ${item.created_at.slice(0, 10)}
          </div>
          <button class="ia__history-del" data-id="${item.id}" title="삭제">✕</button>
        </div>
      `).join('');

      // 클릭: 불러오기
      listEl.querySelectorAll('.ia__history-item').forEach(el => {
        el.addEventListener('click', e => {
          if (e.target.classList.contains('ia__history-del')) return;
          this._loadAnalysis(el.dataset.id);
        });
      });

      // 삭제 버튼
      listEl.querySelectorAll('.ia__history-del').forEach(btn => {
        btn.addEventListener('click', e => {
          e.stopPropagation();
          this._deleteAnalysis(btn.dataset.id);
        });
      });
    } catch (e) {
      listEl.innerHTML = '<div class="ia__history-empty">로드 실패</div>';
    }
  }

  // ── 불러오기 ──────────────────────────────────────────────────────────────

  async _loadAnalysis(id) {
    const resultArea = this._pane.querySelector('#ia-result-area');
    const metaBar    = this._pane.querySelector('#ia-meta-bar');
    const saveBtn    = this._pane.querySelector('#ia-save-btn');
    try {
      const resp = await fetch(`${BASE}/api/intel/history/${id}`);
      const data = await resp.json();

      // 쿼리 복원
      this._pane.querySelector('#ia-query-input').value = data.query;

      // 모드 버튼 복원
      this._pane.querySelectorAll('.ia__mode-btn').forEach(b => {
        b.classList.toggle('is-active', b.dataset.mode === data.mode);
      });

      // 결과 표시
      resultArea.innerHTML = `<div class="ia__md-output" id="ia-md-output"></div>`;
      const mdEl = resultArea.querySelector('#ia-md-output');
      mdEl.innerHTML = window.marked ? window.marked.parse(data.result_md) : data.result_md;

      // 메타 바
      metaBar.innerHTML = `
        <div class="ia__meta-row">
          <span class="ia__badge ia__badge--mode">
            ${MODE_CONFIG[data.mode]?.icon ?? '💡'} ${data.mode}
          </span>
          <span class="ia__meta-sep">|</span>
          <span>📍 ${data.regions.join(', ') || '전체'}</span>
          <span class="ia__meta-sep">|</span>
          <span>🗓 ${data.created_at.slice(0, 16).replace('T', ' ')}</span>
          <span class="ia__badge ia__badge--saved">저장된 분석</span>
        </div>
      `;
      metaBar.style.display = '';
      saveBtn.style.display = 'none';
    } catch (e) {
      resultArea.innerHTML = `<div class="ia__error">⚠️ 불러오기 실패: ${e.message}</div>`;
    }
  }

  // ── 삭제 ──────────────────────────────────────────────────────────────────

  async _deleteAnalysis(id) {
    if (!confirm('이 분석을 삭제하시겠습니까?')) return;
    await fetch(`${BASE}/api/intel/history/${id}`, { method: 'DELETE' });
    this._loadHistory();
  }

  // ── 메타 바 렌더링 ────────────────────────────────────────────────────────

  _renderMeta(el, meta) {
    const sc      = meta.source_counts ?? {};
    const mode    = MODE_CONFIG[meta.mode] ?? { icon: '💡', label: meta.mode };
    const sectors = (meta.sectors ?? []).map(s => SECTOR_LABEL[s] ?? s).join(' · ');
    const regions = (meta.regions ?? []).join(', ') || '전체';
    const thinking = meta.thinking
      ? '<span class="ia__badge ia__badge--thinking">🧠 Thinking</span>'
      : '<span class="ia__badge">⚡ Fast</span>';

    el.innerHTML = `
      <div class="ia__meta-row">
        <span class="ia__badge ia__badge--mode">${mode.icon} ${mode.label}</span>
        ${thinking}
        <span class="ia__meta-sep">|</span>
        <span>📍 ${regions}</span>
        ${sectors ? `<span class="ia__meta-sep">|</span><span>${sectors}</span>` : ''}
        <span class="ia__meta-sep">|</span>
        <span>브리핑 ${(sc.fts_items ?? 0) + (sc.sector_items ?? 0)}건
          · 이벤트 ${sc.event_stats_regions ?? 0}지역
          · Cascade ${sc.cascade_links ?? 0}건</span>
        <span id="ia-score-badge"></span>
      </div>
    `;
  }

  // ── §19-D 신뢰도 점수 렌더링 ──────────────────────────────────────────────

  _renderScore(metaBar, scoreData) {
    const { confidence, provisional, breakdown,
            inference_grade, inference_caveat } = scoreData;
    const resultArea = this._pane.querySelector('#ia-result-area');

    // ── 2축 표시: 증거 등급(grounding) + 추론 등급(causal ladder) ──────────
    // 학술 재설계: 신뢰도 숫자는 '인과 확신'이 아니라 '근거 충실도'다.
    const _ladderMeta = {
      '선행성': { cls: 'precedence',    icon: '🟢' },
      '상관':   { cls: 'correlational', icon: '🟡' },
      '기술적': { cls: 'descriptive',   icon: '⚪' },
    };
    const badge = metaBar.querySelector('#ia-score-badge');
    if (badge) {
      const cls  = confidence >= 80 ? 'high' : confidence >= 60 ? 'mid' : 'low';
      const fill = Math.round(confidence / 10);
      const bar  = '█'.repeat(fill) + '░'.repeat(10 - fill);
      const lm   = _ladderMeta[inference_grade] ?? _ladderMeta['기술적'];
      badge.innerHTML = `
        <span class="ia__meta-sep">|</span>
        <span class="ia__score-badge ia__score-badge--${cls}"
              title="§19-D 증거 충실도: 수치인용${breakdown.numeric_citation} + 1차사료${breakdown.primary_source} + 가설${breakdown.hypothesis} + 경쟁이론${breakdown.competing_theory} + 고리강도${breakdown.chain_strength} — 인과 확신 아님">
          증거 ${bar} ${confidence}
        </span>
        <span class="ia__meta-sep">|</span>
        <span class="ia__ladder-badge ia__ladder-badge--${lm.cls}"
              title="${inference_caveat ?? ''}">
          추론 ${lm.icon} ${inference_grade ?? '기술적'}
        </span>
      `;
    }

    // 두 축의 의미를 명확히 — 증거↑ 라도 추론(인과)은 별개임을 결과 상단에 고지
    const note = resultArea.querySelector('.ia__axis-note');
    if (!note) {
      const el = document.createElement('div');
      el.className = 'ia__axis-note';
      el.innerHTML = `
        <strong>2축 해석</strong> — <b>증거 등급</b>(데이터·이론 충실도)과
        <b>추론 등급</b>(인과추론 사다리: 기술적 &lt; 상관 &lt; 선행성)은 별개입니다.
        ${inference_caveat ? `<small>추론 단서: ${inference_caveat}</small>` : ''}
      `;
      resultArea.prepend(el);
    }

    // 60점 미만 → PROVISIONAL 배너 (증거 충실도 기준)
    if (provisional) {
      const existing = resultArea.querySelector('.ia__provisional-banner');
      if (!existing) {
        const banner = document.createElement('div');
        banner.className = 'ia__provisional-banner';
        banner.innerHTML = `
          ⚠️ <strong>[PROVISIONAL]</strong> 증거 등급 ${confidence}점 — 수치 근거·경쟁 이론이 부족합니다.
          <small>§19-D 기준: 60점 미만은 잠정 분석으로 처리.</small>
        `;
        resultArea.prepend(banner);
      }
    }
  }

  // ── IA-Engine-D: H1 가설 검증 결과 렌더링 ────────────────────────────────

  _renderHypotheses(resultArea, hypotheses) {
    if (!hypotheses.length) return;

    // 학술 재설계: 인과추론 사다리 (기술적 < 상관 < 선행성). 인과 단정 어휘 배제.
    const _ladderLabel = {
      '선행성': { cls: 'precedence',    icon: '🟢', text: '선행성',
                  desc: 'Granger 예측적 선행 (통제변수 조건부) — 구조적 인과는 아님' },
      '상관':   { cls: 'correlational', icon: '🟡', text: '상관',
                  desc: '시사적 — 선행성 미달(교란 미통제·이론근거 약함·p<0.15)' },
      '기술적': { cls: 'descriptive',   icon: '⚪', text: '기술적',
                  desc: '서술·이론 근거만 — 인과 검정 미달/불가' },
    };

    const cards = hypotheses.map(h => {
      const grade = h.inference_grade ?? '기술적';
      const st = _ladderLabel[grade] ?? _ladderLabel['기술적'];
      const pStr   = h.granger_p   != null ? `p = ${h.granger_p}` : '—';
      const qStr   = h.granger_q   != null ? `q = ${h.granger_q}` : '';   // FDR
      const fStr   = h.f_statistic != null ? `F = ${h.f_statistic}` : '';
      const lagStr = h.best_lag   != null ? `lag ${h.best_lag}` : '';
      const nStr   = h.n_obs > 0          ? `n = ${h.n_obs}`     : '';
      const statsStr = [pStr, qStr, fStr, lagStr, nStr].filter(Boolean).join(' · ');
      // 검정 절차 투명성 뱃지 (정상성 차분·교란통제·이론근거)
      const guards = [];
      if (h.controlled)      guards.push(`<span class="ia__hyp-tag ia__hyp-tag--ok">교란통제${h.control_name ? `(${h.control_name})` : ''}</span>`);
      else                   guards.push(`<span class="ia__hyp-tag ia__hyp-tag--warn">교란 미통제</span>`);
      if (h.differenced)     guards.push(`<span class="ia__hyp-tag">정상성 차분</span>`);
      if (h.theory_grounded) guards.push(`<span class="ia__hyp-tag ia__hyp-tag--ok">이론근거</span>`);
      const targetBadge = h.dependent_region
        ? `<span class="ia__hyp-tag">${h.region_code} → ${h.dependent_region} (사건→사건)</span>`
        : (h.region_code ? `<span class="ia__hyp-tag">${h.region_code}${h.ticker ? ` → ${h.ticker}` : ''}</span>` : '');
      const caveatNote  = h.inference_caveat ? `<div class="ia__hyp-caveat">⚠️ ${h.inference_caveat}</div>` : '';
      const proxyNote   = (h.var_type === 'Type_C' && h.proxy_suggestions?.length)
        ? `<div class="ia__hyp-proxy">권장 대리변수: ${h.proxy_suggestions.join(' · ')}</div>`
        : '';

      return `
        <div class="ia__hyp-card ia__hyp-card--${st.cls}">
          <div class="ia__hyp-header">
            <span class="ia__hyp-status">${st.icon} 추론: ${st.text}</span>
            ${targetBadge}
            <span class="ia__hyp-stats">${statsStr}</span>
          </div>
          <div class="ia__hyp-h1"><strong>H1</strong> ${h.h1}</div>
          <div class="ia__hyp-h0"><strong>H0</strong> ${h.h0}</div>
          <div class="ia__hyp-guards">${guards.join(' ')}</div>
          <div class="ia__hyp-desc">${st.desc}</div>
          ${caveatNote}
          ${proxyNote}
        </div>
      `;
    }).join('');

    const section = document.createElement('div');
    section.className = 'ia__hyp-section';
    section.innerHTML = `
      <div class="ia__hyp-title">🔬 인과추론 사다리 — H1 선행성 검정 (Granger, 인과 아님)</div>
      <div class="ia__hyp-ladder-legend">
        기술적(서술) &lt; 상관(시사) &lt; 선행성(통제 조건부 예측 선행) — 어느 칸도 구조적 인과를 단정하지 않음
      </div>
      ${cards}
    `;
    resultArea.appendChild(section);
  }
}
