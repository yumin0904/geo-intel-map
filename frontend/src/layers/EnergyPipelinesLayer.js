/**
 * EnergyPipelinesLayer.js
 * 에너지 파이프라인(가스관·송유관)을 Leaflet polyline으로 렌더링한다.
 * CLAUDE.md 섹터: 에너지 지정학 & 인프라 (Weaponized Interdependence)
 */

import { api } from '../services/api.js';

// type별 색상 — 가스(주황)/석유(노랑)
const TYPE_COLOR = {
  gas: '#ff8c00',
  oil: '#ffd700',
};

// status별 dashArray — 운용 중이면 실선, 아니면 점선 계열
// suspended/sabotaged는 시각적으로 '끊김' 강조
const STATUS_DASH = {
  active:    null,          // 실선
  planned:   '6, 5',        // 짧은 점선
  suspended: '10, 6',       // 긴 점선
  sabotaged: '4, 8',        // 파단선 (간격 넓음)
};

// status별 투명도 — 비활성 파이프라인은 흐리게
const STATUS_OPACITY = {
  active:    0.90,
  planned:   0.55,
  suspended: 0.55,
  sabotaged: 0.40,
};

function getLineStyle(props) {
  const color   = TYPE_COLOR[props.type]    ?? '#ffffff';
  const dash    = STATUS_DASH[props.status] ?? null;
  const opacity = STATUS_OPACITY[props.status] ?? 0.7;
  return { color, dashArray: dash, opacity, weight: 3.5 };
}

// status 한국어 레이블
const STATUS_LABEL = {
  active:    '운용 중',
  planned:   '계획/건설 중',
  suspended: '중단',
  sabotaged: '파괴됨',
};

function buildPopup(props) {
  const tags = (props.theory_tags ?? [])
    .map(t => `<span class="theory-tag">${t}</span>`)
    .join(' ');

  const statusLabel = STATUS_LABEL[props.status] ?? props.status;
  const capacity = props.capacity_bcm
    ? `${props.capacity_bcm} bcm/yr`
    : props.capacity_mbpd
    ? `${props.capacity_mbpd} mb/d`
    : '-';

  return `
    <div class="base-popup">
      <h3 class="base-popup__name">${props.name}</h3>
      <p class="base-popup__name-en">${props.name_en}</p>
      <table class="base-popup__table">
        <tr><td>유형</td><td><strong>${props.type === 'gas' ? '천연가스' : '원유'}</strong></td></tr>
        <tr><td>상태</td><td>${statusLabel}</td></tr>
        <tr><td>운영사</td><td>${props.operator ?? '-'}</td></tr>
        <tr><td>경로</td><td>${props.route ?? '-'}</td></tr>
        <tr><td>연장</td><td>${props.length_km ? props.length_km + ' km' : '-'}</td></tr>
        <tr><td>용량</td><td>${capacity}</td></tr>
        <tr><td>완공</td><td>${props.completed_year ?? '미완공'}</td></tr>
      </table>
      <p class="base-popup__significance">${props.significance ?? ''}</p>
      <div class="base-popup__tags">${tags}</div>
    </div>
  `;
}

export class EnergyPipelinesLayer {
  /** @param {L.Map} map */
  constructor(map) {
    this.map = map;
    this._layerGroup = L.layerGroup();
  }

  async load() {
    let geojson;
    try {
      geojson = await api.get('/api/layers/energy-pipelines');
    } catch (err) {
      console.error('[EnergyPipelinesLayer] 데이터 로드 실패:', err);
      throw err;
    }

    L.geoJSON(geojson, {
      // LineString은 pointToLayer 대신 style 함수로 스타일 적용
      style: (feature) => getLineStyle(feature.properties),

      onEachFeature: (feature, layer) => {
        const props = feature.properties;

        layer.bindPopup(buildPopup(props), {
          maxWidth:  400,
          className: 'geo-popup',
        });

        // 마우스 오버 시 파이프라인명 + 상태 툴팁
        const statusLabel = STATUS_LABEL[props.status] ?? props.status;
        layer.bindTooltip(`${props.name} (${statusLabel})`, {
          permanent:  false,
          direction:  'top',
          className:  'geo-tooltip',
          sticky:     true,   // 마우스 따라 이동 — 긴 선에 유용
        });

        // 마우스 오버 시 선 두께 강조
        layer.on('mouseover', () => {
          layer.setStyle({ weight: 5.5, opacity: 1 });
        });
        layer.on('mouseout', () => {
          layer.setStyle(getLineStyle(props));
        });
      },
    }).addTo(this._layerGroup);

    this._layerGroup.addTo(this.map);
    console.info(`[EnergyPipelinesLayer] ${geojson.features.length}개 파이프라인 로드 완료`);
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
