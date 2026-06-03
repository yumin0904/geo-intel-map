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
      if (!resp.ok) throw new Error(`${resp.status}`);
      const data = await resp.json();
      saveBtn.textContent = '✅ 저장됨';
      saveBtn.disabled = true;
      this._loadHistory();  // 히스토리 목록 갱신
    } catch (e) {
      saveBtn.textContent = '⚠️ 저장 실패';
      saveBtn.disabled = false;
    }
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
    const { confidence, provisional, breakdown } = scoreData;
    const resultArea = this._pane.querySelector('#ia-result-area');

    // 메타 바에 점수 배지 삽입
    const badge = metaBar.querySelector('#ia-score-badge');
    if (badge) {
      const cls  = confidence >= 80 ? 'high' : confidence >= 60 ? 'mid' : 'low';
      const fill = Math.round(confidence / 10);
      const bar  = '█'.repeat(fill) + '░'.repeat(10 - fill);
      badge.innerHTML = `
        <span class="ia__meta-sep">|</span>
        <span class="ia__score-badge ia__score-badge--${cls}"
              title="§19-D: 수치인용${breakdown.numeric_citation} + 1차사료${breakdown.primary_source} + 가설${breakdown.hypothesis} + 경쟁이론${breakdown.competing_theory} + 고리강도${breakdown.chain_strength}">
          신뢰도 ${bar} ${confidence}점
        </span>
      `;
    }

    // 60점 미만 → PROVISIONAL 배너를 결과 최상단에 삽입
    if (provisional) {
      const existing = resultArea.querySelector('.ia__provisional-banner');
      if (!existing) {
        const banner = document.createElement('div');
        banner.className = 'ia__provisional-banner';
        banner.innerHTML = `
          ⚠️ <strong>[PROVISIONAL]</strong> 신뢰도 ${confidence}점 — 수치 근거·경쟁 이론이 부족합니다.
          <small>§19-D 기준: 60점 미만은 잠정 분석으로 처리.</small>
        `;
        resultArea.prepend(banner);
      }
    }
  }
}
