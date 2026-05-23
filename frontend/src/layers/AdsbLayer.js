/**
 * AdsbLayer.js
 * OpenSky Network 실시간 군용기 ADS-B 레이어.
 *
 * 대만해협·남중국해·동중국해의 군용기 위치를 ✈ 마커로 표시하고
 * COG(침로) 방향으로 마커를 회전시킨다.
 *
 * 이론 연결 (Farrell & Newman 2019 — Weaponized Interdependence):
 *   이 레이어에서 감지된 군용기 이벤트는 cascade 엔진의
 *   taiwan_strait_to_tsm / taiwan_strait_to_soxx 룰의 트리거 소스다.
 *   반도체 공급망 집중(대만 90%+ 파운드리)이 군사 긴장의 금융 전달 경로가 된다.
 *
 * 마커 회전 계산:
 *   ✈(U+2708)는 기본적으로 우상향(동북, ~45°)으로 렌더링된다.
 *   실제 방향 표시: rotate(trackDeg - 45)deg
 *
 * CLAUDE.md 섹터: 인도-태평양 군사 대치, A2/AD, 회색지대 전략
 */

import { api } from '../services/api.js';

// ── 항공기 유형 스타일 ───────────────────────────────────────────────────────
// opensky.py의 _infer_type() 반환값과 매핑 (한국어 포함 부분 매칭)
const AIRCRAFT_STYLES = {
  isr:      { color: '#ff1744', size: 18, cls: 'isr',      label: 'ISR (정찰)'   },
  bomber:   { color: '#d500f9', size: 18, cls: 'bomber',   label: '전략 폭격기'  },
  tanker:   { color: '#ff9100', size: 15, cls: 'tanker',   label: '공중급유기'   },
  patrol:   { color: '#ff6d00', size: 15, cls: 'patrol',   label: '해상초계기'   },
  transport:{ color: '#448aff', size: 14, cls: 'transport',label: '공수기'       },
  vip:      { color: '#ffd600', size: 14, cls: 'vip',      label: 'VIP 수송'    },
  tiltrotor:{ color: '#64ffda', size: 14, cls: 'tiltrotor',label: '틸트로터'    },
  military: { color: '#b0bec5', size: 13, cls: 'military', label: '군용기'       },
};

// 줌 5 이하: severity ≥ 60 항공기만 표시 (ISR·폭격기 중심)
const ZOOM_LOW_CUTOFF  = 5;
const MIN_SEV_LOW_ZOOM = 60;

// ── 유형 분류 ──────────────────────────────────────────────────────────────

function getAircraftStyle(aircraftType) {
  if (!aircraftType) return AIRCRAFT_STYLES.military;
  if (aircraftType.includes('ISR') || aircraftType.includes('정찰'))
    return AIRCRAFT_STYLES.isr;
  if (aircraftType.includes('폭격기'))  return AIRCRAFT_STYLES.bomber;
  if (aircraftType.includes('급유기')) return AIRCRAFT_STYLES.tanker;
  if (aircraftType.includes('초계기')) return AIRCRAFT_STYLES.patrol;
  if (aircraftType.includes('공수'))   return AIRCRAFT_STYLES.transport;
  if (aircraftType.includes('VIP'))    return AIRCRAFT_STYLES.vip;
  if (aircraftType.includes('틸트'))   return AIRCRAFT_STYLES.tiltrotor;
  return AIRCRAFT_STYLES.military;
}

// ── 마커 아이콘 ────────────────────────────────────────────────────────────
// ✈ 기본 방향: 우상향(~45°). rotate(track - 45)로 실제 침로를 가리킨다.
function buildIcon(aircraftType, trackDeg) {
  const style    = getAircraftStyle(aircraftType);
  const rotateDeg = ((trackDeg ?? 0) - 45 + 360) % 360;
  return L.divIcon({
    className: '',
    html: `<div class="adsb-marker adsb-marker--${style.cls}"
                style="font-size:${style.size}px;transform:rotate(${rotateDeg}deg)">✈</div>`,
    iconSize:   [style.size, style.size],
    iconAnchor: [style.size / 2, style.size / 2],
  });
}

// ── 툴팁 ──────────────────────────────────────────────────────────────────

function buildTooltip(props) {
  const style    = getAircraftStyle(props.aircraft_type);
  const callsign = props.callsign || props.icao24 || '미상';
  const altFt    = props.baro_altitude_m
    ? Math.round(props.baro_altitude_m * 3.281).toLocaleString()
    : '—';
  const velKts   = props.velocity_ms
    ? Math.round(props.velocity_ms * 1.944)
    : '—';
  return (
    `<span style="color:${style.color}">✈</span> `
    + `<strong>${callsign}</strong>`
    + ` &middot; ${style.label}`
    + ` &middot; ${altFt}ft &middot; ${velKts}kts`
  );
}

// ── 팝업 ──────────────────────────────────────────────────────────────────

function buildPopup(props) {
  const style    = getAircraftStyle(props.aircraft_type);
  const callsign = props.callsign || props.icao24 || '미상';
  const tags     = (props.theory_tags ?? [])
    .map(t => `<span class="theory-tag">${t}</span>`).join(' ');
  const date     = (props.timestamp ?? '').slice(0, 19).replace('T', ' ');

  const altFt = props.baro_altitude_m
    ? Math.round(props.baro_altitude_m * 3.281).toLocaleString() + ' ft'
    : '—';
  const velKts = props.velocity_ms
    ? Math.round(props.velocity_ms * 1.944) + ' kts'
    : '—';
  const track  = props.true_track_deg != null
    ? `${Math.round(props.true_track_deg)}°`
    : '—';
  const ground = props.on_ground ? '지상 대기' : '비행 중';

  // 위치 소스: 0=ADS-B, 1=ASTERIX, 2=MLAT, 3=FLARM
  const srcLabel = ['ADS-B', 'ASTERIX', 'MLAT', 'FLARM'][props.position_source ?? 0] ?? 'ADS-B';

  return `
    <div class="base-popup">
      <h3 class="base-popup__name" style="color:${style.color}">
        ✈ ${callsign}
      </h3>
      <p class="base-popup__name-en">
        ${style.label} &middot; ICAO24 ${props.icao24 ?? '—'} &middot; ${date} UTC
      </p>
      <table class="base-popup__table">
        <tr><td>국적</td><td><strong>${props.origin_country ?? '—'}</strong></td></tr>
        <tr><td>상태</td><td>${ground}</td></tr>
        <tr><td>고도 (기압)</td><td>${altFt}</td></tr>
        <tr><td>속도 (지대공)</td><td>${velKts}</td></tr>
        <tr><td>침로 (Track)</td><td>${track}</td></tr>
        <tr><td>스쿼크</td><td>${props.squawk || '—'}</td></tr>
        <tr><td>위치 소스</td><td>${srcLabel}</td></tr>
        <tr><td>심각도</td><td>${props.severity ?? 0} / 100</td></tr>
      </table>
      <p class="base-popup__significance">${props.description ?? ''}</p>
      <div class="base-popup__tags">${tags}</div>
    </div>
  `;
}

// ── 레이어 클래스 ──────────────────────────────────────────────────────────

export class AdsbLayer {
  /**
   * @param {L.Map}    map
   * @param {EventBus} eventBus  - marker:click emit → TheoryPanel 연동
   */
  constructor(map, eventBus = null) {
    this._map      = map;
    this._eventBus = eventBus;
    this._features = [];
    this._cluster  = null;
    this._onZoom   = () => this._applyFilter();
  }

  async load() {
    let geojson;
    try {
      geojson = await api.get('/api/layers/adsb');
    } catch (err) {
      console.error('[AdsbLayer] 데이터 로드 실패:', err);
      throw err;
    }

    this._features = geojson.features ?? [];

    // 군용기는 선박보다 훨씬 적으므로 클러스터 반경을 작게 유지
    this._cluster = L.markerClusterGroup({
      maxClusterRadius:        40,
      spiderfyOnMaxZoom:       true,
      disableClusteringAtZoom: 7,
      iconCreateFunction: group => L.divIcon({
        html: `<div class="adsb-cluster">${group.getChildCount()}</div>`,
        className: '',
        iconSize: [30, 30],
      }),
    });

    this._applyFilter();
    this._cluster.addTo(this._map);
    this._map.on('zoomend', this._onZoom);

    const meta = geojson.metadata ?? {};
    console.info(
      `[AdsbLayer] ${this._features.length}대 로드 | ${meta.source ?? 'OpenSky'}`
    );
  }

  _applyFilter() {
    if (!this._cluster) return;

    const zoom   = this._map.getZoom();
    const minSev = zoom <= ZOOM_LOW_CUTOFF ? MIN_SEV_LOW_ZOOM : 0;

    this._cluster.clearLayers();

    this._features
      .filter(f => (f.properties.severity ?? 0) >= minSev)
      .forEach(feature => {
        const [lon, lat] = feature.geometry.coordinates;
        const props      = feature.properties;
        const trackDeg   = props.true_track_deg ?? 0;

        const marker = L.marker([lat, lon], {
          icon: buildIcon(props.aircraft_type, trackDeg),
        });

        marker.bindTooltip(buildTooltip(props), {
          permanent:  false,
          direction:  'top',
          className:  'geo-tooltip',
        });

        const eb = this._eventBus;
        marker.on('click', function () {
          eb?.emit('marker:click', { ...props, _lon: lon, _lat: lat });
          if (!this._popup) {
            this.bindPopup(buildPopup(props), {
              maxWidth:  400,
              className: 'geo-popup',
            });
          }
          this.openPopup();
        });

        this._cluster.addLayer(marker);
      });
  }

  setVisible(visible) {
    if (!this._cluster) return;
    if (visible) this._cluster.addTo(this._map);
    else         this._cluster.remove();
  }

  destroy() {
    this._map.off('zoomend', this._onZoom);
    if (this._cluster) {
      this._cluster.clearLayers();
      this._cluster.remove();
    }
    this._features = [];
  }
}
