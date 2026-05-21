/**
 * ConflictEventsLayer.js
 * ACLED 분쟁 이벤트를 severity 기반 DivIcon 펄스 마커로 렌더링한다.
 * 군사기지(circleMarker)와 시각적으로 구분 — 펄스는 "지금 일어나고 있음"을 강조.
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
// duration: 낮을수록 빠른 펄스 → 긴박함을 직관적으로 표현
const SEVERITY_STYLES = [
  { min: 80, radius: 14, color: '#f85149', duration: 0.5 },  // 최고: 빨강, 매우 빠름
  { min: 60, radius: 11, color: '#ff8c00', duration: 1.0 },  // 높음: 주황, 빠름
  { min: 30, radius:  8, color: '#d29922', duration: 2.0 },  // 중간: 노랑
  { min:  0, radius:  5, color: '#3fb950', duration: 3.0 },  // 낮음: 초록, 느림
];

// 줌 6 이하: severity 60+ 만 표시 — 광역 뷰에서 노이즈 제거
const ZOOM_HIGH_SEVERITY_CUTOFF = 6;
const MIN_SEVERITY_LOW_ZOOM     = 60;

const CLUSTER_THRESHOLD = 1000;

function getSeverityStyle(severity) {
  return SEVERITY_STYLES.find(s => severity >= s.min) ?? SEVERITY_STYLES.at(-1);
}

/**
 * DivIcon 생성 — CSS 변수로 색상·크기·펄스 속도를 주입한다.
 * className: '' 로 Leaflet 기본 배경/테두리 제거 후 .conflict-icon으로 덮어씀.
 */
function buildIcon(severity) {
  const { radius, color, duration } = getSeverityStyle(severity);
  const size = radius * 2;
  return L.divIcon({
    className:   'conflict-icon',
    html:        `<div class="conflict-dot" style="--cdot-color:${color};--cdot-duration:${duration}s"></div>`,
    iconSize:    [size, size],
    iconAnchor:  [radius, radius],    // 마커 중심을 좌표에 정확히 맞춤
    popupAnchor: [0, -(radius + 4)],  // 팝업이 마커 위에 열리도록
  });
}

function buildPopup(props) {
  const tags = (props.theory_tags ?? [])
    .map(t => `<span class="theory-tag">${t}</span>`)
    .join(' ');
  const date        = props.timestamp?.slice(0, 10) ?? '';
  const eventTypeKo = EVENT_TYPE_KO[props.event_type] ?? props.event_type ?? '';

  return `
    <div class="base-popup">
      <h3 class="base-popup__name">${props.title}</h3>
      <p class="base-popup__name-en">${eventTypeKo} · ${date}</p>
      <table class="base-popup__table">
        <tr><td>국가</td><td><strong>${props.country ?? '-'}</strong></td></tr>
        <tr><td>행위자</td><td>${props.actor1 ?? '-'}</td></tr>
        ${props.actor2 ? `<tr><td>상대방</td><td>${props.actor2}</td></tr>` : ''}
        <tr><td>사망자</td><td>${props.fatalities ?? 0}명</td></tr>
        <tr><td>심각도</td><td>${props.severity ?? 0} / 100</td></tr>
        <tr><td>출처</td><td>${props.source ?? '-'}</td></tr>
      </table>
      <p class="base-popup__significance">${props.description ?? ''}</p>
      <div class="base-popup__tags">${tags}</div>
    </div>
  `;
}

export class ConflictEventsLayer {
  /** @param {L.Map} map */
  constructor(map) {
    this.map         = map;
    this._features   = [];
    this._layerGroup = null;
    this._minSeverity = 0;   // 슬라이더가 설정하는 최소 심각도
    this._periodDays  = 30;  // 기간 필터 (7 or 30)
    this._onZoomEnd   = () => this._applyFilter();
  }

  async load() {
    let geojson;
    try {
      geojson = await api.get('/api/layers/conflict-events');
    } catch (err) {
      console.error('[ConflictEventsLayer] 데이터 로드 실패:', err);
      throw err;
    }

    this._features = geojson.features ?? [];

    // 기간 필터 기준: 데이터 내 최신 타임스탬프 (과거 데이터에서도 정상 동작)
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

    console.info(`[ConflictEventsLayer] ${this._features.length}개 이벤트 로드 완료`);
  }

  _applyFilter() {
    if (!this._layerGroup) return;
    const zoom    = this.map.getZoom();
    // 줌 기반 최소 심각도와 슬라이더 값 중 큰 쪽을 적용
    const zoomMin = zoom <= ZOOM_HIGH_SEVERITY_CUTOFF ? MIN_SEVERITY_LOW_ZOOM : 0;
    const minSev  = Math.max(zoomMin, this._minSeverity);
    // 기간 필터: 데이터 내 최신 이벤트 기준 → 과거 데이터도 정상 동작
    const cutoff  = this._latestTs - this._periodDays * 86_400_000;

    this._layerGroup.clearLayers();

    this._features
      .filter(f => {
        if ((f.properties.severity ?? 0) < minSev) return false;
        const ts = f.properties.timestamp ? Date.parse(f.properties.timestamp) : 0;
        return ts >= cutoff;
      })
      .forEach(feature => {
        const [lon, lat] = feature.geometry.coordinates;
        const props      = feature.properties;

        const marker = L.marker([lat, lon], { icon: buildIcon(props.severity ?? 0) });

        marker.bindTooltip(props.title, {
          permanent: false, direction: 'top', className: 'geo-tooltip',
        });

        // 팝업: 클릭 시 최초 1회만 생성
        marker.on('click', function () {
          if (!this._popup) {
            this.bindPopup(buildPopup(props), { maxWidth: 360, className: 'geo-popup' });
          }
          this.openPopup();
        });

        this._layerGroup.addLayer(marker);
      });
  }

  /** 슬라이더 값 변경 시 호출 — 서버 재요청 없이 클라이언트 필터링 */
  setSeverityMin(n) {
    this._minSeverity = n;
    this._applyFilter();
  }

  /** 기간 토글 버튼 변경 시 호출 (7 or 30) */
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
