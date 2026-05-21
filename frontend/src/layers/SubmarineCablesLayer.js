/**
 * SubmarineCablesLayer.js
 * 전략적 해저 광케이블을 strategic_risk 등급별 색상 폴리라인으로 렌더링한다.
 * CLAUDE.md 섹터: 기술 패권 & 보이지 않는 인프라
 * 이론 연결: Techno-nationalism, Digital Iron Curtain, Platform Power
 */

import { api } from '../services/api.js';

// strategic_risk → 색상 (빨강=중국주도, 주황=혼합, 파랑=미국/동맹)
const RISK_COLOR = {
  high:   '#f85149',
  medium: '#ff8c00',
  low:    '#4a9eff',
};

const RISK_WEIGHT = {
  high:   2.5,
  medium: 1.8,
  low:    1.2,
};

const RISK_LABEL = {
  high:   '고위험 (중국 주도)',
  medium: '중위험 (혼합 소유)',
  low:    '저위험 (미국/동맹)',
};

function getStyle(props) {
  const risk = props.strategic_risk ?? 'medium';
  return {
    color:   RISK_COLOR[risk]  ?? RISK_COLOR.medium,
    weight:  RISK_WEIGHT[risk] ?? RISK_WEIGHT.medium,
    opacity: 0.72,
  };
}

function buildPopup(props) {
  const tags = (props.theory_tags ?? [])
    .map(t => `<span class="theory-tag">${t}</span>`)
    .join(' ');
  const risk      = props.strategic_risk ?? 'medium';
  const owners    = (props.owners ?? []).join(', ');
  const countries = (props.landing_countries ?? []).join(' → ');

  return `
    <div class="base-popup">
      <h3 class="base-popup__name">${props.name}</h3>
      <p class="base-popup__name-en">${props.name_en ?? ''}</p>
      <table class="base-popup__table">
        <tr><td>전략 위험</td>
            <td><strong style="color:${RISK_COLOR[risk]}">${RISK_LABEL[risk]}</strong></td></tr>
        <tr><td>개통</td><td>${props.rfs_year ?? '-'}년</td></tr>
        <tr><td>길이</td><td>${props.length_km ? props.length_km.toLocaleString() + ' km' : '-'}</td></tr>
        <tr><td>주요 소유자</td><td>${owners || '-'}</td></tr>
        <tr><td>경유 국가</td><td>${countries}</td></tr>
      </table>
      <p class="base-popup__significance">${props.significance ?? ''}</p>
      <p class="base-popup__purpose" style="color:${RISK_COLOR[risk]};font-size:11px">${props.theory_ref ?? ''}</p>
      <div class="base-popup__tags">${tags}</div>
    </div>
  `;
}

export class SubmarineCablesLayer {
  /** @param {L.Map} map */
  constructor(map) {
    this.map         = map;
    this._layerGroup = L.layerGroup();
  }

  async load() {
    let geojson;
    try {
      geojson = await api.get('/api/layers/submarine-cables');
    } catch (err) {
      console.error('[SubmarineCablesLayer] 데이터 로드 실패:', err);
      throw err;
    }

    L.geoJSON(geojson, {
      style: (feature) => getStyle(feature.properties),

      onEachFeature: (feature, layer) => {
        const props = feature.properties;
        const risk  = props.strategic_risk ?? 'medium';

        layer.bindPopup(buildPopup(props), {
          maxWidth:  420,
          className: 'geo-popup',
        });

        layer.bindTooltip(
          `${props.name}  ·  ${RISK_LABEL[risk]}`,
          { sticky: true, className: 'geo-tooltip' }
        );

        // 호버 시 강조 — 두께 증가 + 완전 불투명
        layer.on('mouseover', () => {
          layer.setStyle({ opacity: 1, weight: RISK_WEIGHT[risk] + 1.5 });
          layer.bringToFront();
        });
        layer.on('mouseout', () => layer.setStyle(getStyle(props)));
      },
    }).addTo(this._layerGroup);

    // 각 케이블 양 끝점(상륙 지점)을 작은 원으로 표시
    // MultiLineString: 전체 coords 배열의 첫·끝 segment 첫·끝 점 사용
    geojson.features.forEach(feature => {
      const geom  = feature.geometry;
      const risk  = feature.properties.strategic_risk ?? 'medium';
      const color = RISK_COLOR[risk];

      // LineString: coords[0] / MultiLineString: coords[0][0]
      const allSegments = geom.type === 'MultiLineString'
        ? geom.coordinates
        : [geom.coordinates];

      const endpoints = [
        allSegments[0][0],
        allSegments.at(-1).at(-1),
      ];

      endpoints.forEach(([lon, lat]) => {
        L.circleMarker([lat, lon], {
          radius:      3,
          color,
          fillColor:   color,
          fillOpacity: 0.9,
          weight:      1,
          opacity:     0.8,
          interactive: false,
        }).addTo(this._layerGroup);
      });
    });

    this._layerGroup.addTo(this.map);
    console.info(`[SubmarineCablesLayer] ${geojson.features.length}개 케이블 로드 완료`);
  }

  setVisible(visible) {
    if (visible) this._layerGroup.addTo(this.map);
    else         this._layerGroup.remove();
  }

  destroy() {
    this._layerGroup.clearLayers();
    this._layerGroup.remove();
  }
}
