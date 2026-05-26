/**
 * ConflictEventsLayer.js
 * ACLED + GDELT 분쟁 이벤트를 단일 레이어로 통합 렌더링한다.
 *
 * 마커 체계:
 *   ACLED  → DivIcon 펄스 (기존 스타일 유지)
 *   GDELT  → circleMarker, confidence≥0.8: 실선 / <0.8: dashArray 점선 + ⚠️
 *
 * 팝업: 동일 템플릿, 출처 뱃지로 구분
 *   "ACLED ✅" / "GDELT 교차검증✓" / "GDELT ⚠️미검증"
 *
 * CLAUDE.md 섹터: 인도-태평양 군사 대치 + 회색지대 & 비전통 안보
 */

import { api } from '../services/api.js';

const EVENT_TYPE_KO = {
  'Protests':                   '시위/집회',
  'Battles':                    '무력충돌',
  'Violence against civilians': '민간인 피해',
  'Riots':                      '폭동',
  'Strategic developments':     '전략적 동향',
  'Explosions/Remote violence': '폭발/원거리 공격',
};

// severity 0-100 → 마커 반지름 (요구사항 §5)
const SEVERITY_RADIUS = [
  { min: 81, radius: 16 },
  { min: 61, radius: 12 },
  { min: 31, radius:  8 },
  { min:  0, radius:  4 },
];

// severity → 마커 색상 (펄스 속도는 importance 기반으로 분리)
const SEVERITY_STYLES = [
  { min: 80, color: '#f85149' },
  { min: 60, color: '#ff8c00' },
  { min: 30, color: '#d29922' },
  { min:  0, color: '#3fb950' },
];

// importance_score 임계값 — zoom별 가시성 기준 (요구사항 §4)
const IMP_HIGH  = 0.7;  // 항상 표시 ⭐
const IMP_MID   = 0.4;  // zoom ≥ 5 시 표시 📌
                        // < 0.4: zoom ≥ 7 시 표시 💤

const CLUSTER_THRESHOLD = 1000;

// GDELT 마커 색상
const GDELT_COLOR_HIGH = '#ff4444';  // QuadClass 4: Material Conflict
const GDELT_COLOR_LOW  = '#ff8800';  // QuadClass 3: Verbal Conflict

function getSeverityRadius(severity) {
  return (SEVERITY_RADIUS.find(s => severity >= s.min) ?? SEVERITY_RADIUS.at(-1)).radius;
}

function getSeverityStyle(severity) {
  return SEVERITY_STYLES.find(s => severity >= s.min) ?? SEVERITY_STYLES.at(-1);
}

/** importance_score → 등급 기호 */
function importanceTier(score) {
  if (score >= IMP_HIGH) return '⭐';
  if (score >= IMP_MID)  return '📌';
  return '💤';
}

/** importance_score → 펄스 CSS 클래스 */
function pulseClass(importance) {
  if (importance >= IMP_HIGH) return 'conflict-pulse-fast';  // ⭐ 1s
  if (importance >= IMP_MID)  return 'conflict-pulse-slow';  // 📌 2s
  return 'conflict-no-pulse';                                 // 💤 없음
}

/** ACLED용 DivIcon 펄스 마커 (cluster_count 배지 포함) */
function buildAcledIcon(severity, clusterCount = 1, importance = 0) {
  const radius  = getSeverityRadius(severity);
  const { color } = getSeverityStyle(severity);
  const size    = radius * 2;

  // importance ≥ 0.7이면 실선 테두리로 강조
  const outline = importance >= IMP_HIGH ? 'outline:2px solid rgba(255,255,255,0.7);' : '';

  // cluster_count > 1이면 숫자 배지 표시 (요구사항 §6)
  const badgeHtml = clusterCount > 1
    ? `<span class="conflict-cluster-badge">${clusterCount}건</span>`
    : '';

  return L.divIcon({
    className:   'conflict-icon',
    html:        `<div class="conflict-dot ${pulseClass(importance)}" style="--cdot-color:${color};${outline}"></div>${badgeHtml}`,
    iconSize:    [size, size],
    iconAnchor:  [radius, radius],
    popupAnchor: [0, -(radius + 4)],
  });
}

/** GDELT용 circleMarker */
function buildGdeltMarker(lat, lon, props) {
  const verified  = (props.confidence_score ?? 0) >= 0.8;
  const color     = (props.quad_class ?? 3) >= 4 ? GDELT_COLOR_HIGH : GDELT_COLOR_LOW;
  const radius    = 5 + Math.round((props.severity ?? 50) / 10);
  const opacity   = verified ? 0.85 : 0.55;

  return L.circleMarker([lat, lon], {
    radius,
    color,
    fillColor:   color,
    fillOpacity: opacity,
    opacity,
    dashArray:   verified ? null : '4 3',
    weight:      verified ? 1.5 : 2,
  });
}

/** 통합 팝업 — 출처(ACLED/GDELT)에 따라 뱃지·행 전환 */
function buildPopup(props) {
  const isGdelt   = props.data_source === 'GDELT';
  const date      = props.timestamp?.slice(0, 10) ?? '';
  const region    = props.region_code || props.country || '-';
  const tags      = (props.theory_tags ?? [])
    .map(t => `<span class="theory-tag">${t}</span>`)
    .join(' ');

  // 출처 뱃지 — GDELT는 "GDELT 🌐 + confidence" 포맷 (요구사항 §5)
  let sourceBadge;
  if (!isGdelt) {
    sourceBadge = '<span class="popup-badge popup-badge--acled">ACLED ✅</span>';
  } else {
    const conf     = props.confidence_score ?? 0.5;
    const confPct  = Math.round(conf * 100);
    const verified = conf >= 0.8;
    sourceBadge = verified
      ? `<span class="popup-badge popup-badge--gdelt-ok">GDELT 🌐 교차검증✓ <em>${confPct}%</em></span>`
      : `<span class="popup-badge popup-badge--gdelt-warn">GDELT 🌐 ⚠️ 미검증 <em>${confPct}%</em></span>`;
  }

  // GDELT description 블록 (요구사항 §4)
  const descHtml = isGdelt && props.description
    ? `<p class="popup-gdelt-desc">${props.description}</p>`
    : '';

  // ACLED ⭐ 이벤트: 한국어 번역 버튼 (importance ≥ 0.7만 Gemini API 허용)
  const translateBtn = !isGdelt && (props.importance_score ?? 0) >= IMP_HIGH
    ? `<button class="popup-translate-btn" data-text="${encodeURIComponent(props.title)}" data-importance="${props.importance_score ?? 0}">🌐 한국어로 보기</button>`
    : '';

  // 출처별 추가 행
  const extraRows = isGdelt ? `
    <tr><td>Goldstein</td><td>${props.goldstein ?? props.goldstein_scale ?? '-'}</td></tr>
    <tr><td>미디어 언급</td><td>${props.num_mentions ?? '-'}회</td></tr>
    ${props.actor1_ko ? `<tr><td>행위자1</td><td>${props.actor1_ko}</td></tr>` : ''}
    ${props.actor2_ko ? `<tr><td>행위자2</td><td>${props.actor2_ko}</td></tr>` : ''}
  ` : `
    <tr><td>행위자</td><td>${props.actor1 ?? '-'}</td></tr>
    ${props.actor2 ? `<tr><td>상대방</td><td>${props.actor2}</td></tr>` : ''}
    <tr><td>사망자</td><td>${props.fatalities ?? 0}명</td></tr>
    <tr><td>출처</td><td>${props.source ?? '-'}</td></tr>
  `;

  const sourceLink = isGdelt && props.source_url
    ? `<div class="base-popup__link"><a href="${props.source_url}" target="_blank" rel="noopener">원문 보기 →</a></div>`
    : '';

  const eventTypeKo = !isGdelt
    ? (EVENT_TYPE_KO[props.event_type] ?? props.event_type ?? '')
    : (props.quad_class >= 4 ? '물리적 충돌' : '언어적 충돌');

  // ── importance_score 섹션 (ACLED 전용, 요구사항 §7) ─────────────────
  let importanceHtml = '';
  if (!isGdelt && props.importance_score != null) {
    const imp    = props.importance_score;
    const tier   = importanceTier(imp);
    const pct    = Math.round(imp * 100);
    const bd     = props._score_breakdown || {};

    const clusterNote = (props.cluster_count ?? 1) > 1
      ? `<div class="popup-cluster-note">이 지역 유사 충돌 <strong>${props.cluster_count}건</strong> 통합됨</div>`
      : '';

    const bdRows = [
      ['심각도',         bd.severity        ?? 0],
      ['최신성',         bd.recency         ?? 0],
      ['Cascade 연계',   bd.cascade_hit     ?? 0],
      ['지역 반복',      bd.repeat_region   ?? 0],
      ['GDELT 교차확인', bd.gdelt_confirmed ?? 0],
    ].map(([label, val]) =>
      `<tr><td>${label}</td><td>${(val * 100).toFixed(1)}p</td></tr>`
    ).join('');

    importanceHtml = `
      <div class="popup-importance">
        <div class="popup-importance__bar-row">
          <span class="popup-importance__tier">${tier}</span>
          <div class="popup-importance__bar-wrap">
            <div class="popup-importance__bar" style="width:${pct}%"></div>
          </div>
          <span class="popup-importance__val">${pct}</span>
        </div>
        ${clusterNote}
        <details class="popup-importance__detail">
          <summary>점수 구성</summary>
          <table class="base-popup__table popup-importance__breakdown">${bdRows}</table>
        </details>
      </div>
    `;
  }

  return `
    <div class="base-popup">
      <h3 class="base-popup__name">${props.title}</h3>
      <p class="base-popup__name-en">${eventTypeKo} · ${date} · ${region}</p>
      <div class="base-popup__badge-row">${sourceBadge}</div>
      ${descHtml}
      <table class="base-popup__table">
        <tr><td>심각도</td><td><strong>${props.severity ?? 0}</strong> / 100</td></tr>
        ${extraRows}
      </table>
      ${importanceHtml}
      ${translateBtn}
      ${props.id ? `<button class="popup-reasoning-btn" data-event-id="${props.id}">🤖 AI 분析</button>` : ''}
      ${sourceLink}
      <div class="base-popup__tags">${tags}</div>
    </div>
  `;
}

export class ConflictEventsLayer {
  /**
   * @param {L.Map} map
   * @param {import('../core/EventBus.js').EventBus|null} eventBus
   */
  constructor(map, eventBus = null) {
    this.map          = map;
    this._eventBus    = eventBus;
    this._features    = [];   // ACLED + GDELT 통합
    this._layerGroup  = null;
    this._minSeverity = 0;
    this._periodDays  = 30;
    this._onZoomEnd   = () => this._applyFilter();
  }

  async load() {
    // ACLED + GDELT 병렬 fetch — 한쪽 실패해도 다른 쪽은 표시
    const [acledResult, gdeltResult] = await Promise.allSettled([
      api.get('/api/layers/conflict-events'),
      api.get('/api/layers/gdelt'),
    ]);

    const acledFeatures = acledResult.status === 'fulfilled'
      ? (acledResult.value.features ?? []).map(f => ({
          ...f,
          properties: { ...f.properties, data_source: 'ACLED' },
        }))
      : (() => { console.warn('[ConflictEventsLayer] ACLED 로드 실패'); return []; })();

    const gdeltFeatures = gdeltResult.status === 'fulfilled'
      ? (gdeltResult.value.features ?? [])
      : (() => { console.warn('[ConflictEventsLayer] GDELT 로드 실패'); return []; })();
    // GDELT GeoJSON은 이미 data_source: "GDELT" 포함

    this._features = [...acledFeatures, ...gdeltFeatures];

    // 기간 필터 기준: 전체 데이터의 최신 타임스탬프
    const timestamps = this._features
      .map(f => f.properties.timestamp ? Date.parse(f.properties.timestamp) : 0)
      .filter(Boolean);
    this._latestTs = timestamps.length ? Math.max(...timestamps) : Date.now();

    this._layerGroup = this._features.length >= CLUSTER_THRESHOLD
      ? L.markerClusterGroup({ chunkedLoading: true, maxClusterRadius: 50 })
      : L.layerGroup();

    this._applyFilter();
    this._layerGroup.addTo(this.map);
    this.map.on('zoomend', this._onZoomEnd);

    const acledCnt = acledFeatures.length;
    const gdeltCnt = gdeltFeatures.length;
    console.info(`[ConflictEventsLayer] ACLED ${acledCnt}개 + GDELT ${gdeltCnt}개 = 총 ${this._features.length}개`);
  }

  _applyFilter() {
    if (!this._layerGroup) return;

    const zoom   = this.map.getZoom();
    const cutoff = this._latestTs - this._periodDays * 86_400_000;

    this._layerGroup.clearLayers();

    this._features
      .filter(f => {
        const props = f.properties;

        // severity 슬라이더 필터
        if ((props.severity ?? 0) < this._minSeverity) return false;

        // GDELT: 항상 최신 데이터 → 기간·importance 필터 패스
        if (props.data_source === 'GDELT') return true;

        // 기간 필터
        const ts = props.timestamp ? Date.parse(props.timestamp) : 0;
        if (ts < cutoff) return false;

        // importance 기반 zoom 가시성 (요구사항 §4)
        const imp = props.importance_score ?? 0;
        if (imp >= IMP_HIGH)  return true;           // ⭐ 항상 표시
        if (imp >= IMP_MID)   return zoom >= 5;      // 📌 zoom ≥ 5
        return zoom >= 7;                             // 💤 zoom ≥ 7
      })
      .forEach(feature => {
        const [lon, lat] = feature.geometry.coordinates;
        const props      = feature.properties;
        const isGdelt    = props.data_source === 'GDELT';

        const marker = isGdelt
          ? buildGdeltMarker(lat, lon, props)
          : L.marker([lat, lon], {
              icon: buildAcledIcon(
                props.severity       ?? 0,
                props.cluster_count  ?? 1,
                props.importance_score ?? 0,
              ),
            });

        marker.bindTooltip(
          isGdelt && props.unverified ? `⚠️ ${props.title}` : props.title,
          { permanent: false, direction: 'top', className: 'geo-tooltip' }
        );

        const eb = this._eventBus;
        marker.on('click', function () {
          eb?.emit('marker:click', { ...props, _lon: lon, _lat: lat });
          if (!this._popup) {
            this.bindPopup(buildPopup(props), { maxWidth: 360, className: 'geo-popup' });
          }
          this.openPopup();
        });

        // 팝업 DOM이 렌더된 뒤 버튼 이벤트 등록
        marker.on('popupopen', function () {
          const popupEl = this.getPopup()?.getElement();
          if (!popupEl) return;

          // ── 🌐 한국어 번역 버튼 ──────────────────────────────────
          const translateBtn = popupEl.querySelector('.popup-translate-btn');
          if (translateBtn) {
            translateBtn.addEventListener('click', async () => {
              const rawText  = decodeURIComponent(translateBtn.dataset.text);
              const impScore = parseFloat(translateBtn.dataset.importance ?? '0');

              translateBtn.disabled    = true;
              translateBtn.textContent = '⏳ 번역 중…';

              try {
                const params = new URLSearchParams({
                  text:       rawText,
                  context:    'acled',
                  importance: impScore,
                });
                const res  = await fetch(`/api/translate?${params}`);
                const data = await res.json();

                if (!res.ok) {
                  translateBtn.textContent = '⚠️ 번역 불가';
                  return;
                }

                const cached = data.cached ? ' (캐시)' : '';
                const el = document.createElement('div');
                el.className   = 'popup-translated';
                el.textContent = data.text_ko;
                const note     = document.createElement('span');
                note.className = 'popup-translated__note';
                note.textContent = `🌐 한국어${cached}`;
                el.prepend(note);
                translateBtn.replaceWith(el);
              } catch {
                translateBtn.textContent = '⚠️ 네트워크 오류';
                translateBtn.disabled = false;
              }
            }, { once: true });
          }

          // ── 🤖 AI 분析 버튼 ──────────────────────────────────────
          const reasoningBtn = popupEl.querySelector('.popup-reasoning-btn');
          if (reasoningBtn) {
            reasoningBtn.addEventListener('click', () => {
              eb?.emit('reasoning:open', {
                event_id: reasoningBtn.dataset.eventId,
                title:    props.title,
              });
            }, { once: true });
          }
        });

        this._layerGroup.addLayer(marker);
      });
  }

  setSeverityMin(n) {
    this._minSeverity = n;
    this._applyFilter();
  }

  setPeriod(days) {
    this._periodDays = days;
    this._applyFilter();
  }

  setVisible(visible) {
    if (!this._layerGroup) return;
    if (visible) this._layerGroup.addTo(this.map);
    else         this._layerGroup.remove();
  }

  destroy() {
    this.map.off('zoomend', this._onZoomEnd);
    if (this._layerGroup) {
      this._layerGroup.clearLayers();
      this._layerGroup.remove();
    }
    this._features = [];
  }
}
