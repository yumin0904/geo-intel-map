/**
 * MilitaryBasesLayer.js
 * 군사기지 GeoJSON을 백엔드에서 받아 Leaflet circleMarker로 렌더링한다.
 * CLAUDE.md 섹터: 인도-태평양 군사 대치 + 해양 초점주의
 */

import { api } from '../services/api.js';

// 국가별 마커 색상 — 미국(파랑), 중국(빨강), 러시아(노랑), 동맹(초록)
const COUNTRY_COLORS = {
  USA:     '#4a9eff',
  China:   '#ff4a4a',
  Russia:  '#ffd700',
  Allied:  '#4aff91',
};

// 기지 유형별 반지름 (naval > air > multi > army 순으로 시각 강조)
const TYPE_RADIUS = {
  naval: 9,
  air:   8,
  multi: 8,
  army:  7,
};

// 팝업 HTML 생성 — 학습 정보 포함
function buildPopup(props) {
  const tags = (props.theory_tags ?? [])
    .map(t => `<span class="theory-tag">${t}</span>`)
    .join(' ');

  return `
    <div class="base-popup">
      <h3 class="base-popup__name">${props.name}</h3>
      <p class="base-popup__name-en">${props.name_en}</p>
      <table class="base-popup__table">
        <tr><td>보유국</td><td><strong>${props.country}</strong></td></tr>
        <tr><td>유형</td><td>${props.type}</td></tr>
        <tr><td>설치연도</td><td>${props.established_year ?? '미상'}</td></tr>
        <tr><td>섹터</td><td>${props.sector ?? '-'}</td></tr>
      </table>
      <p class="base-popup__purpose">⚑ ${props.purpose}</p>
      <p class="base-popup__significance">${props.significance}</p>
      <div class="base-popup__tags">${tags}</div>
    </div>
  `;
}

export class MilitaryBasesLayer {
  /**
   * @param {L.Map} map - MapController.map 인스턴스
   * @param {import('../core/EventBus.js').EventBus|null} eventBus
   *   클릭 시 'marker:click' emit → TheoryPanel 연동
   */
  constructor(map, eventBus = null) {
    this.map = map;
    this._eventBus = eventBus;
    // 레이어 그룹으로 관리 — 토글 시 레이어 전체를 한번에 숨김/표시 가능
    this._layerGroup = L.layerGroup();
    // setFilter에서 개별 마커 스타일 제어를 위해 보관
    this._markers = [];
  }

  async load() {
    let geojson;
    try {
      geojson = await api.get('/api/layers/military-bases');
    } catch (err) {
      console.error('[MilitaryBasesLayer] 데이터 로드 실패:', err);
      throw err; // LayerManager가 error 상태로 처리하도록 re-throw
    }

    L.geoJSON(geojson, {
      // GeoJSON Point를 L.circleMarker로 변환
      // 1000개 미만이므로 circleMarker 직접 사용 (Canvas 모드에서 빠름)
      pointToLayer: (feature, latlng) => {
        const props  = feature.properties;
        const color  = COUNTRY_COLORS[props.country] ?? '#ffffff';
        const radius = TYPE_RADIUS[props.type]       ?? 7;

        const marker = L.circleMarker(latlng, {
          radius,
          color,
          fillColor:   color,
          fillOpacity: 0.85,
          weight:      1.5,
          opacity:     1,
        });

        this._markers.push({ marker, country: props.country });
        return marker;
      },
      // 각 마커에 학습 정보 팝업 바인딩
      onEachFeature: (feature, layer) => {
        layer.bindPopup(buildPopup(feature.properties), {
          maxWidth: 360,
          className: 'geo-popup',
        });

        // 마우스 오버 시 기지명 툴팁 표시
        layer.bindTooltip(feature.properties.name, {
          permanent: false,
          direction: 'top',
          className: 'geo-tooltip',
        });

        // TheoryPanel 연동 — 좌표를 함께 emit해 cascade rule 지역 판정에 사용
        const eb  = this._eventBus;
        const [lon, lat] = feature.geometry.coordinates;
        layer.on('click', () => {
          eb?.emit('marker:click', { ...feature.properties, _lon: lon, _lat: lat });
        });
      },
    }).addTo(this._layerGroup);

    this._layerGroup.addTo(this.map);
    console.info(`[MilitaryBasesLayer] ${geojson.features.length}개 기지 로드 완료`);
  }

  /** 레이어 표시/숨김 */
  setVisible(visible) {
    if (visible) {
      this._layerGroup.addTo(this.map);
    } else {
      this._layerGroup.remove();
    }
  }

  /**
   * 진영 필터 — 선택된 국가 마커만 강조, 나머지는 흐리게.
   * 완전 숨김 대신 dim 처리 → 위치 인식을 유지하면서 비교 학습 가능.
   * @param {string[]} countries - 활성화할 국가 배열 (예: ['USA', 'China'])
   */
  setFilter(countries) {
    const active = new Set(countries);
    this._markers.forEach(({ marker, country }) => {
      const show = active.has(country);
      marker.setStyle({
        opacity:     show ? 1    : 0.08,
        fillOpacity: show ? 0.85 : 0.05,
      });
    });
  }

  /** 레이어 그룹 및 마커 참조 정리 */
  destroy() {
    this._layerGroup.clearLayers();
    this._layerGroup.remove();
    this._markers = [];
  }
}
