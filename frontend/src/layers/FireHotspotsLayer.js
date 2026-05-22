/**
 * FireHotspotsLayer.js
 * NASA FIRMS VIIRS S-NPP NRT 위성 화재/열점 레이어.
 *
 * 분쟁 지역의 고FRP(Fire Radiative Power) 열점은 단순 산불이 아니라
 * 대규모 폭발·정유 시설 파괴·농경지 방화의 위성 신호다.
 * 예: 우크라이나 밀밭 화재 → Food Security 무기화 (Patel & Moore 2009)
 *     예멘/이라크 정유 시설 화재 → Resource Weaponization (Hirschman 1945)
 *
 * CLAUDE.md 섹터: 에너지 지정학 + 회색지대 & 비전통 안보
 */

import { api } from '../services/api.js';

// severity(0-100) → 원 크기·색상 매핑
// FRP 물리 의미를 색으로 표현: 노랑(소규모) → 주황 → 빨강(극대)
const FIRE_STYLES = [
  { min: 70, radius: 10, color: '#ff2020', fillOpacity: 0.85 }, // 극대: 정유·LNG 시설
  { min: 50, radius:  8, color: '#ff5500', fillOpacity: 0.80 }, // 대규모: 산업 인프라
  { min: 30, radius:  6, color: '#ff9a3c', fillOpacity: 0.75 }, // 중규모: 건물·차량
  { min:  0, radius:  4, color: '#ffdd57', fillOpacity: 0.65 }, // 소규모: 농업·소형
];

// 줌 5 이하에서는 고강도 열점만 표시 (광역 뷰 노이즈 제거)
const ZOOM_LOW_CUTOFF  = 5;
const MIN_SEV_LOW_ZOOM = 50;

const CONF_LABEL = { h: '높음 (H)', n: '보통 (N)', l: '낮음 (L)' };
const CONF_COLOR = { h: '#3fb950', n: '#d29922', l: '#8b949e' };
const DAYNIGHT   = { D: '낮 (Day)', N: '밤 (Night)' };

function getStyle(severity) {
  return FIRE_STYLES.find(s => severity >= s.min) ?? FIRE_STYLES.at(-1);
}

function buildPopup(props) {
  const tags     = (props.theory_tags ?? [])
    .map(t => `<span class="theory-tag">${t}</span>`).join(' ');
  const date     = props.timestamp?.slice(0, 10) ?? '';
  const conf     = (props.confidence ?? 'n').toLowerCase();
  const frp      = (props.frp ?? 0).toFixed(1);
  const ti4      = (props.bright_ti4 ?? 0).toFixed(1);
  const confKo   = CONF_LABEL[conf] ?? conf;
  const confCol  = CONF_COLOR[conf] ?? '#ccc';
  const dn       = DAYNIGHT[props.daynight] ?? '-';

  return `
    <div class="base-popup">
      <h3 class="base-popup__name">${props.title}</h3>
      <p class="base-popup__name-en">VIIRS S-NPP NRT &middot; ${date}</p>
      <table class="base-popup__table">
        <tr><td>FRP</td>
            <td><strong>${frp} MW</strong></td></tr>
        <tr><td>신뢰도</td>
            <td style="color:${confCol}">${confKo}</td></tr>
        <tr><td>관측 시간대</td>
            <td>${dn}</td></tr>
        <tr><td>밝기온도</td>
            <td>${ti4} K</td></tr>
        <tr><td>심각도</td>
            <td>${props.severity ?? 0} / 100</td></tr>
      </table>
      <p class="base-popup__significance">${props.description ?? ''}</p>
      <div class="base-popup__tags">${tags}</div>
    </div>
  `;
}

export class FireHotspotsLayer {
  /**
   * @param {L.Map}     map
   * @param {EventBus}  eventBus - marker:click emit → TheoryPanel 연동
   */
  constructor(map, eventBus = null) {
    this._map       = map;
    this._eventBus  = eventBus;
    this._features  = [];
    this._group     = null;
    this._onZoomEnd = () => this._applyFilter();
  }

  async load() {
    let geojson;
    try {
      geojson = await api.get('/api/layers/fire');
    } catch (err) {
      console.error('[FireHotspotsLayer] 데이터 로드 실패:', err);
      throw err;
    }

    this._features = geojson.features ?? [];
    // 화재 열점은 지리적으로 분산되므로 MarkerCluster 불필요 — 단순 layerGroup 사용
    this._group = L.layerGroup();

    this._applyFilter();
    this._group.addTo(this._map);
    this._map.on('zoomend', this._onZoomEnd);

    const src = geojson.metadata?.source ?? 'FIRMS';
    console.info(`[FireHotspotsLayer] ${this._features.length}개 열점 로드 | ${src}`);
  }

  _applyFilter() {
    if (!this._group) return;

    const zoom   = this._map.getZoom();
    const minSev = zoom <= ZOOM_LOW_CUTOFF ? MIN_SEV_LOW_ZOOM : 0;

    this._group.clearLayers();

    this._features
      .filter(f => (f.properties.severity ?? 0) >= minSev)
      .forEach(feature => {
        const [lon, lat] = feature.geometry.coordinates;
        const props      = feature.properties;
        const style      = getStyle(props.severity ?? 0);

        const marker = L.circleMarker([lat, lon], {
          radius:      style.radius,
          color:       style.color,
          weight:      1.5,
          opacity:     0.9,
          fillColor:   style.color,
          fillOpacity: style.fillOpacity,
        });

        const frpLabel = (props.frp ?? 0).toFixed(0);
        marker.bindTooltip(
          `🔥 ${props.title} &middot; FRP ${frpLabel} MW`,
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

        this._group.addLayer(marker);
      });
  }

  setVisible(visible) {
    if (!this._group) return;
    if (visible) this._group.addTo(this._map);
    else         this._group.remove();
  }

  destroy() {
    this._map.off('zoomend', this._onZoomEnd);
    if (this._group) {
      this._group.clearLayers();
      this._group.remove();
    }
    this._features = [];
  }
}
