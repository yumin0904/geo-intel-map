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

// severity 0-100 → 마커 크기/색상/펄스 속도 매핑
const SEVERITY_STYLES = [
  { min: 80, radius: 14, color: '#f85149', duration: 0.5 },
  { min: 60, radius: 11, color: '#ff8c00', duration: 1.0 },
  { min: 30, radius:  8, color: '#d29922', duration: 2.0 },
  { min:  0, radius:  5, color: '#3fb950', duration: 3.0 },
];

const ZOOM_HIGH_SEVERITY_CUTOFF = 6;
const MIN_SEVERITY_LOW_ZOOM     = 60;
const CLUSTER_THRESHOLD         = 1000;

// GDELT 마커 색상
const GDELT_COLOR_HIGH = '#ff4444';  // QuadClass 4: Material Conflict
const GDELT_COLOR_LOW  = '#ff8800';  // QuadClass 3: Verbal Conflict

function getSeverityStyle(severity) {
  return SEVERITY_STYLES.find(s => severity >= s.min) ?? SEVERITY_STYLES.at(-1);
}

/** ACLED용 DivIcon 펄스 마커 */
function buildAcledIcon(severity, tags = []) {
  const { radius, color, duration } = getSeverityStyle(severity);
  const size    = radius * 2;
  const badgeHtml = tags.length
    ? `<div class="conflict-tags">${tags.map(t => `<span class="conflict-tag-badge">${t}</span>`).join('')}</div>`
    : '';
  return L.divIcon({
    className:   'conflict-icon',
    html:        `<div class="conflict-dot" style="--cdot-color:${color};--cdot-duration:${duration}s"></div>${badgeHtml}`,
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

  // 출처 뱃지
  let sourceBadge;
  if (!isGdelt) {
    sourceBadge = '<span class="popup-badge popup-badge--acled">ACLED ✅</span>';
  } else if ((props.confidence_score ?? 0) >= 0.8) {
    sourceBadge = '<span class="popup-badge popup-badge--gdelt-ok">GDELT 교차검증✓</span>';
  } else {
    sourceBadge = '<span class="popup-badge popup-badge--gdelt-warn">GDELT ⚠️ 미검증</span>';
  }

  // 출처별 추가 행
  const extraRows = isGdelt ? `
    <tr><td>신뢰도</td><td>${(props.confidence_score ?? 0.5).toFixed(1)}</td></tr>
    <tr><td>Goldstein</td><td>${props.goldstein_scale ?? '-'}</td></tr>
    <tr><td>미디어 언급</td><td>${props.num_mentions ?? '-'}회</td></tr>
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

  return `
    <div class="base-popup">
      <h3 class="base-popup__name">${props.title}</h3>
      <p class="base-popup__name-en">${eventTypeKo} · ${date} · ${region}</p>
      <div class="base-popup__badge-row">${sourceBadge}</div>
      <table class="base-popup__table">
        <tr><td>심각도</td><td><strong>${props.severity ?? 0}</strong> / 100</td></tr>
        ${extraRows}
      </table>
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
    const zoomMin = zoom <= ZOOM_HIGH_SEVERITY_CUTOFF ? MIN_SEVERITY_LOW_ZOOM : 0;
    const minSev  = Math.max(zoomMin, this._minSeverity);
    const cutoff  = this._latestTs - this._periodDays * 86_400_000;

    this._layerGroup.clearLayers();

    this._features
      .filter(f => {
        if ((f.properties.severity ?? 0) < minSev) return false;
        const ts = f.properties.timestamp ? Date.parse(f.properties.timestamp) : 0;
        // GDELT는 항상 최신 데이터 → 기간 필터 패스 처리
        if (f.properties.data_source === 'GDELT') return true;
        return ts >= cutoff;
      })
      .forEach(feature => {
        const [lon, lat] = feature.geometry.coordinates;
        const props      = feature.properties;
        const isGdelt    = props.data_source === 'GDELT';

        const marker = isGdelt
          ? buildGdeltMarker(lat, lon, props)
          : L.marker([lat, lon], { icon: buildAcledIcon(props.severity ?? 0, props.theory_tags ?? []) });

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
