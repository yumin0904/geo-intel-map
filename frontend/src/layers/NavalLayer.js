/**
 * NavalLayer.js
 * AISStream.io 실시간 선박 AIS 레이어.
 *
 * 전략 해역(호르무즈·바브엘만데브·말라카·대만해협·남중국해)의
 * 유조선·LNG선·화물선·군함 위치를 실시간으로 지도에 표시한다.
 *
 * 이론 연결 (Mahan 해양력 이론, 1890):
 *   초크포인트를 통과하는 선박의 밀집도·속력이 감소하면
 *   SLOC(해상교통로) 위협 수위의 직접적 지표다.
 *   특히 호르무즈·바브엘만데브의 유조선 이동이 WTI 유가와 연동된다
 *   (Cascade 룰: hormuz_tension_to_oil).
 *
 * CLAUDE.md 섹터: 해양 초점주의·에너지 지정학·인도-태평양 군사 대치
 */

import { api } from '../services/api.js';

// ── 선박 유형 스타일 ────────────────────────────────────────────────────────
// AIS ship type code → 마커 색상·크기·라벨 매핑
const SHIP_STYLES = {
  warship: { color: '#ff2040', radius: 8,  cls: 'warship', label: '군함'   },
  lng:     { color: '#00aaff', radius: 7,  cls: 'lng',     label: 'LNG/LPG' },
  tanker:  { color: '#ff8800', radius: 6,  cls: 'tanker',  label: '유조선'  },
  cargo:   { color: '#44cc55', radius: 5,  cls: 'cargo',   label: '화물선'  },
  unknown: { color: '#888888', radius: 4,  cls: 'unknown', label: '미분류'  },
};

// NavigationalStatus → 한국어
const NAV_STATUS = {
  0: '항해중', 1: '묘박중', 2: '기관고장', 3: '조종제한',
  4: '흘수제한', 5: '계류중', 6: '좌초', 7: '어로작업중', 15: '미정의',
};

// 줌 5 이하에서는 severity ≥ 45 (유조선+전략해역 이상) 선박만 표시
const ZOOM_LOW_CUTOFF   = 5;
const MIN_SEV_LOW_ZOOM  = 45;

// ── 선박 유형 분류 ─────────────────────────────────────────────────────────

function getShipStyle(shipType) {
  if (shipType === 35)               return SHIP_STYLES.warship;
  if (shipType === 84 || shipType === 85) return SHIP_STYLES.lng;
  if (shipType >= 80 && shipType <= 89)   return SHIP_STYLES.tanker;
  if (shipType >= 70 && shipType <= 79)   return SHIP_STYLES.cargo;
  return SHIP_STYLES.unknown;
}

// ── 마커 아이콘 ────────────────────────────────────────────────────────────
// ▲(삼각형) + COG(침로) 회전 — 선박 진행 방향을 직관적으로 표시
function buildIcon(shipType, cog) {
  const style = getShipStyle(shipType);
  const deg   = (cog > 0 && cog < 360) ? cog : 0;
  return L.divIcon({
    className: '',
    html: `<div class="ship-marker ship-marker--${style.cls}"
                style="transform:rotate(${deg}deg)">▲</div>`,
    iconSize:   [14, 14],
    iconAnchor: [7, 7],
  });
}

// ── 툴팁 ──────────────────────────────────────────────────────────────────

function buildTooltip(props) {
  const style    = getShipStyle(props.ship_type ?? 0);
  const speed    = (props.sog ?? 0).toFixed(1);
  const dest     = props.destination ? ` → ${props.destination}` : '';
  return `<span style="color:${style.color}">●</span> `
    + `<strong>${props.ship_name ?? props.title}</strong>`
    + ` &middot; ${style.label} &middot; ${speed} kn${dest}`;
}

// ── 팝업 ──────────────────────────────────────────────────────────────────

function buildPopup(props) {
  const style    = getShipStyle(props.ship_type ?? 0);
  const tags     = (props.theory_tags ?? [])
    .map(t => `<span class="theory-tag">${t}</span>`).join(' ');
  const date     = (props.timestamp ?? '').slice(0, 19).replace('T', ' ');
  const speed    = (props.sog ?? 0).toFixed(1);
  const cog      = (props.cog ?? 0).toFixed(0);
  const navLabel = NAV_STATUS[props.nav_status ?? 15] ?? '미정의';
  const dest     = props.destination || '—';
  const imo      = props.imo || '—';
  const heading  = props.true_heading != null ? `${props.true_heading}°` : '—';
  const hasStatic = props.has_static_data
    ? '<span style="color:#3fb950">정적데이터 있음</span>'
    : '<span style="color:#8b949e">유형 미확인(정적데이터 없음)</span>';

  return `
    <div class="base-popup">
      <h3 class="base-popup__name" style="color:${style.color}">
        ${props.ship_name ?? props.title}
      </h3>
      <p class="base-popup__name-en">
        ${style.label} &middot; MMSI ${props.mmsi ?? '—'} &middot; ${date} UTC
      </p>
      <table class="base-popup__table">
        <tr><td>항법 상태</td><td><strong>${navLabel}</strong></td></tr>
        <tr><td>속력 (SOG)</td><td>${speed} kn</td></tr>
        <tr><td>침로 (COG)</td><td>${cog}°</td></tr>
        <tr><td>선수 방향</td><td>${heading}</td></tr>
        <tr><td>목적지</td><td>${dest}</td></tr>
        <tr><td>IMO</td><td>${imo}</td></tr>
        <tr><td>심각도</td><td>${props.severity ?? 0} / 100</td></tr>
        <tr><td>데이터</td><td>${hasStatic}</td></tr>
      </table>
      <p class="base-popup__significance">${props.description ?? ''}</p>
      <div class="base-popup__tags">${tags}</div>
    </div>
  `;
}

// ── 레이어 클래스 ──────────────────────────────────────────────────────────

export class NavalLayer {
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
      geojson = await api.get('/api/layers/naval');
    } catch (err) {
      console.error('[NavalLayer] 데이터 로드 실패:', err);
      throw err;
    }

    this._features = geojson.features ?? [];

    // 선박은 초크포인트에 밀집 → MarkerCluster로 성능 확보 (CLAUDE.md 성능 원칙)
    this._cluster = L.markerClusterGroup({
      maxClusterRadius:        50,
      spiderfyOnMaxZoom:       true,
      disableClusteringAtZoom: 9,   // 줌 9 이상에서 개별 마커 표시
      iconCreateFunction: count => L.divIcon({
        html: `<div class="ship-cluster">${count.getChildCount()}</div>`,
        className: '',
        iconSize: [32, 32],
      }),
    });

    this._applyFilter();
    this._cluster.addTo(this._map);
    this._map.on('zoomend', this._onZoom);

    const meta = geojson.metadata ?? {};
    console.info(
      `[NavalLayer] ${this._features.length}척 로드 | ${meta.source ?? 'AISStream'}`
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
        const shipType   = props.ship_type ?? 0;
        const cog        = props.cog ?? 0;

        const marker = L.marker([lat, lon], {
          icon: buildIcon(shipType, cog),
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
              maxWidth:  380,
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
