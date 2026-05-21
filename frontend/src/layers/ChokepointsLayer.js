/**
 * ChokepointsLayer.js
 * 전략적 해상 초점(Chokepoints)을 폴리곤으로 렌더링한다.
 * CLAUDE.md 섹터: 해양 초점주의 & SLOC (Mahan 해양력 이론)
 *
 * 색상 체계: importance 등급 → critical(적)/high(주황)/medium(황)
 * 이 시각화는 "어느 해협을 통제하느냐가 해상패권을 결정한다"는 Mahan 이론을 직관적으로 보여준다.
 */

import { api } from '../services/api.js';

// importance 등급별 색상 — 전략적 위험도를 직관적으로 표현
const IMPORTANCE_COLOR = {
  critical: '#ff3a3a',  // 빨강 — 봉쇄 시 즉각적 글로벌 충격
  high:     '#ff8c00',  // 주황 — 고위험, 지역 충격
  medium:   '#ffd700',  // 황금 — 중요하나 대체 경로 존재
};

// importance별 폴리곤 스타일 — 중요할수록 진하게
// dashArray: 점선 처리 → "경계 구역" 느낌, 단순 사각형처럼 안 보이게
const BASE_STYLE = {
  critical: { fillOpacity: 0.22, weight: 2.0, opacity: 0.90, dashArray: '8 5' },
  high:     { fillOpacity: 0.16, weight: 1.5, opacity: 0.80, dashArray: '6 5' },
  medium:   { fillOpacity: 0.10, weight: 1.2, opacity: 0.70, dashArray: '5 5' },
};

// importance 한국어 레이블
const IMPORTANCE_LABEL = {
  critical: '최고위험 (Critical)',
  high:     '고위험 (High)',
  medium:   '중간위험 (Medium)',
};

function getStyle(props) {
  const imp   = props.importance ?? 'medium';
  const color = IMPORTANCE_COLOR[imp] ?? '#ffffff';
  const base  = BASE_STYLE[imp] ?? BASE_STYLE.medium;
  return { color, fillColor: color, ...base };
}

function buildPopup(props) {
  const tags = (props.theory_tags ?? [])
    .map(t => `<span class="theory-tag">${t}</span>`)
    .join(' ');

  const impLabel = IMPORTANCE_LABEL[props.importance] ?? props.importance;

  return `
    <div class="base-popup">
      <h3 class="base-popup__name">${props.name}</h3>
      <p class="base-popup__name-en">${props.name_en}</p>
      <table class="base-popup__table">
        <tr><td>위험 등급</td><td><strong style="color:${IMPORTANCE_COLOR[props.importance]}">${impLabel}</strong></td></tr>
        <tr><td>심각도</td><td>${props.severity} / 100</td></tr>
        <tr><td>폭</td><td>${props.chokepoint_width_km ? props.chokepoint_width_km + ' km' : '-'}</td></tr>
        <tr><td>통제국</td><td>${(props.controlling_power ?? []).join(', ')}</td></tr>
      </table>
      <p class="base-popup__significance"><strong>물동량:</strong> ${props.throughput ?? '-'}</p>
      <p class="base-popup__significance">${props.significance ?? ''}</p>
      <div class="base-popup__theory">
        <span class="theory-label">이론적 연결</span>
        <p>${props.theory_ref ?? ''}</p>
      </div>
      <div class="base-popup__tags">${tags}</div>
    </div>
  `;
}

export class ChokepointsLayer {
  /** @param {L.Map} map */
  constructor(map) {
    this.map = map;
    this._layerGroup = L.layerGroup();
  }

  async load() {
    let geojson;
    try {
      geojson = await api.get('/api/layers/chokepoints');
    } catch (err) {
      console.error('[ChokepointsLayer] 데이터 로드 실패:', err);
      throw err;
    }

    L.geoJSON(geojson, {
      style: (feature) => getStyle(feature.properties),

      onEachFeature: (feature, layer) => {
        const props = feature.properties;

        layer.bindPopup(buildPopup(props), {
          maxWidth:  420,
          className: 'geo-popup',
        });

        // 툴팁: 해협명 + 위험 등급
        const impLabel = IMPORTANCE_LABEL[props.importance] ?? '';
        layer.bindTooltip(`${props.name}  ·  ${impLabel}`, {
          permanent:  false,
          direction:  'center',
          className:  'geo-tooltip',
          sticky:     true,
        });

        // 마우스 오버 시 폴리곤 강조 (dashArray 제거 → 실선으로)
        layer.on('mouseover', () => {
          layer.setStyle({ fillOpacity: 0.42, weight: 2.5, opacity: 1, dashArray: null });
          layer.bringToFront();
        });
        layer.on('mouseout', () => {
          layer.setStyle(getStyle(props));
        });

        // 폴리곤 중심에 이름 레이블 마커 — 구역 식별용, 클릭 이벤트 없음
        const bounds = layer.getBounds();
        const center = bounds.getCenter();
        const labelIcon = L.divIcon({
          className:  'chokepoint-label',
          html:       `<span class="chokepoint-label__inner">${props.name}</span>`,
          iconSize:   [0, 0],
          iconAnchor: [0, 0],
        });
        this._layerGroup.addLayer(
          L.marker(center, { icon: labelIcon, interactive: false, zIndexOffset: -100 })
        );
      },
    }).addTo(this._layerGroup);

    this._layerGroup.addTo(this.map);
    console.info(`[ChokepointsLayer] ${geojson.features.length}개 해상 초점 로드 완료`);
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
  }
}
