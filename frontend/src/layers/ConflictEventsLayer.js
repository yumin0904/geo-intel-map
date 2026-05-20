/**
 * ConflictEventsLayer.js
 * ACLED 분쟁 이벤트를 severity 기반 circleMarker로 렌더링한다.
 * CLAUDE.md 섹터: 인도-태평양 군사 대치 + 회색지대 & 비전통 안보
 */

import { api } from '../services/api.js';

// severity 0-100 → 마커 반지름/색상 매핑
// 심각도가 높을수록 크고 붉은 마커 — 지도에서 분쟁 강도를 직관적으로 파악
const SEVERITY_STYLES = [
  { min: 80, radius: 14, color: '#f85149' },  // 최고 강도: 빨강 (--color-danger)
  { min: 60, radius: 11, color: '#ff8c00' },  // 높은 강도: 주황
  { min: 30, radius:  8, color: '#d29922' },  // 중간 강도: 노랑 (--color-warning)
  { min:  0, radius:  5, color: '#3fb950' },  // 낮은 강도: 초록 (--color-success)
];

function getSeverityStyle(severity) {
  return SEVERITY_STYLES.find(s => severity >= s.min) ?? SEVERITY_STYLES.at(-1);
}

function buildPopup(props) {
  const tags = (props.theory_tags ?? [])
    .map(t => `<span class="theory-tag">${t}</span>`)
    .join(' ');
  const date = props.timestamp?.slice(0, 10) ?? '';

  return `
    <div class="base-popup">
      <h3 class="base-popup__name">${props.title}</h3>
      <p class="base-popup__name-en">${props.event_type ?? ''} · ${date}</p>
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
    this.map = map;
    this._layerGroup = L.layerGroup();
    this._markers    = [];
  }

  async load() {
    let geojson;
    try {
      geojson = await api.get('/api/layers/conflict-events');
    } catch (err) {
      console.error('[ConflictEventsLayer] 데이터 로드 실패:', err);
      throw err;
    }

    L.geoJSON(geojson, {
      // severity에 따라 크기·색상이 다른 circleMarker 생성
      pointToLayer: (feature, latlng) => {
        const props              = feature.properties;
        const { radius, color } = getSeverityStyle(props.severity ?? 0);

        const marker = L.circleMarker(latlng, {
          radius,
          color,
          fillColor:   color,
          fillOpacity: 0.75,
          weight:      1.5,
          opacity:     1,
        });

        this._markers.push({ marker, severity: props.severity });
        return marker;
      },
      onEachFeature: (feature, layer) => {
        layer.bindPopup(buildPopup(feature.properties), {
          maxWidth:  360,
          className: 'geo-popup',
        });
        layer.bindTooltip(feature.properties.title, {
          permanent: false,
          direction: 'top',
          className: 'geo-tooltip',
        });
      },
    }).addTo(this._layerGroup);

    this._layerGroup.addTo(this.map);
    console.info(`[ConflictEventsLayer] ${geojson.features.length}개 이벤트 로드 완료`);
  }

  setVisible(visible) {
    if (visible) {
      this._layerGroup.addTo(this.map);
    } else {
      this._layerGroup.remove();
    }
  }

  destroy() {
    this._layerGroup.clearLayers();
    this._layerGroup.remove();
    this._markers = [];
  }
}
