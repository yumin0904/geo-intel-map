/**
 * CountryLayer.js — 국가 폴리곤 경계 + 하이라이트 레이어
 *
 * 흐름:
 *   load() 호출 → CDN에서 Natural Earth 110m GeoJSON fetch (sessionStorage 캐시)
 *   → Leaflet GeoJSON 폴리곤 레이어 추가 (z-index 201)
 *   → 호버 시 반투명 하이라이트
 *
 * 국가 선택: LayerPanel 검색 드롭다운 → EventBus country:flyto { iso3 } 수신
 *   → flyToCountry(iso3) : 지도 이동 + 폴리곤 하이라이트
 *
 * z-index 설계:
 *   countryPane = 201 (tilePane 200 바로 위, overlayPane 400·markerPane 600 아래)
 *   → 마커·파이프라인 클릭을 절대 막지 않는다.
 *   fillOpacity: 0.01 — SVG pointer-events: visiblePainted는 완전 투명 영역을
 *   무시하므로 최소 불투명도 0.01로 fill hit-area를 활성화한다.
 *
 * EventBus:
 *   수신: country:flyto  { iso3 }
 *
 * GeoJSON 소스:
 *   datasets/geo-countries — ISO_A3 프로퍼티 포함, 110m 해상도
 *   jsDelivr CDN 캐시 → 빠른 로드, sessionStorage 2차 캐시
 */

const GEOJSON_URL =
  'https://cdn.jsdelivr.net/gh/datasets/geo-countries/data/countries.geojson';

const SESSION_KEY = 'geo-intel:countries-geojson';

const STYLE_DEFAULT = {
  fillColor:   '#000000',
  // 0.01: 육안으로 불가시하지만 SVG pointer-events: visiblePainted 히트 영역 활성화
  fillOpacity: 0.01,
  color:       '#58a6ff',
  weight:      0.4,
  opacity:     0.25,
};

const STYLE_HOVER = {
  fillColor:   '#58a6ff',
  fillOpacity: 0.12,
  color:       '#58a6ff',
  weight:      1.2,
  opacity:     0.7,
};

const STYLE_SELECTED = {
  fillColor:   '#58a6ff',
  fillOpacity: 0.20,
  color:       '#58a6ff',
  weight:      2.0,
  opacity:     1.0,
};

export class CountryLayer {
  /**
   * @param {L.Map}    map
   * @param {import('../core/EventBus.js').EventBus} eventBus
   */
  constructor(map, eventBus) {
    this._map      = map;
    this._bus      = eventBus;
    this._layer    = null;
    this._pane     = null;
    this._visible  = false;
    this._hovered  = null;
    this._selected = null;

    this._initPane();
    this._bus.on('country:flyto', ({ iso3 }) => this.flyToCountry(iso3));
    // overlayPane 캔버스(z-index 400)가 GeoJSON 클릭을 가로막으므로
    // map 레벨 click 이벤트로 받아서 bounds 기반 국가 히트 테스트
    this._map.on('click', this._onMapClick, this);
  }

  _initPane() {
    if (!this._map.getPane('countryPane')) {
      this._pane = this._map.createPane('countryPane');
      this._pane.style.zIndex        = '201';
      this._pane.style.pointerEvents = 'auto';
    }
  }

  async load() {
    if (this._layer) {
      this._layer.addTo(this._map);
      this._visible = true;
      return;
    }

    let geojson;
    try {
      geojson = await this._fetchGeojson();
    } catch (err) {
      console.warn('[CountryLayer] GeoJSON 로드 실패:', err);
      return;
    }

    this._layer = L.geoJSON(geojson, {
      pane:        'countryPane',
      style:       () => ({ ...STYLE_DEFAULT }),
      onEachFeature: (feature, layerFeat) => {
        const name = feature.properties?.ADMIN || feature.properties?.name || '';
        if (name) {
          layerFeat.bindTooltip(name, {
            className: 'country-hover-tooltip',
            sticky:    true,
            direction: 'top',
            offset:    [0, -6],
          });
        }
        layerFeat.on({
          mouseover: () => this._onHover(layerFeat),
          mouseout:  () => this._onOut(layerFeat),
        });
      },
    }).addTo(this._map);

    this._visible = true;
  }

  setVisible(bool) {
    this._visible = bool;
    if (!this._layer) return;
    if (bool) {
      this._layer.addTo(this._map);
    } else {
      this._layer.remove();
      this._hovered  = null;
      this._selected = null;
    }
  }

  destroy() {
    this._map.off('click', this._onMapClick, this);
    this._layer?.remove();
    this._layer = null;
  }

  /**
   * 지도 클릭 → 가장 작은 bounds를 가진 국가 폴리곤을 찾아 패널 오픈.
   * overlayPane 캔버스가 GeoJSON 이벤트를 가로막으므로 map 레벨에서 처리.
   */
  _onMapClick(e) {
    if (!this._layer || !this._visible) return;
    const latlng = e.latlng;
    let best = null;
    let bestArea = Infinity;
    this._layer.eachLayer(l => {
      if (!l.getBounds) return;
      const bounds = l.getBounds();
      if (!bounds.contains(latlng)) return;
      // bounds가 여러 개 매칭될 경우 가장 작은 것(더 정확한 국가) 선택
      const area = (bounds.getNorth() - bounds.getSouth()) * (bounds.getEast() - bounds.getWest());
      if (area < bestArea) { bestArea = area; best = l; }
    });
    if (!best) return;
    const props = best.feature?.properties ?? {};
    const iso3  = props.ISO_A3 || props.iso_a3 || '';
    const name  = props.ADMIN || props.name || '';
    if (!iso3 || iso3 === '-99') return;
    this.flyToCountry(iso3);
    this._bus.emit('country:open', { iso3, name_en: name });
  }

  /**
   * 지정 iso3 국가로 지도를 이동하고 폴리곤을 하이라이트한다.
   * LayerPanel 검색 드롭다운 선택 시 호출.
   * @param {string} iso3
   */
  flyToCountry(iso3) {
    if (!this._layer) return;

    let target = null;
    this._layer.eachLayer(l => {
      if (target) return;
      const props = l.feature?.properties ?? {};
      if ((props.ISO_A3 || props.iso_a3) === iso3) target = l;
    });
    if (!target) return;

    // 이전 선택 해제
    if (this._selected && this._selected !== target) {
      this._selected.setStyle(STYLE_DEFAULT);
    }
    target.setStyle(STYLE_SELECTED);
    this._selected = target;

    this._map.fitBounds(target.getBounds(), { padding: [60, 60], maxZoom: 6 });
  }

  // ── 이벤트 핸들러 ────────────────────────────────────────────────────────

  _onHover(layerFeat) {
    // 선택된 국가는 STYLE_SELECTED 유지
    if (layerFeat === this._selected) return;
    if (this._hovered && this._hovered !== layerFeat && this._hovered !== this._selected) {
      this._hovered.setStyle(STYLE_DEFAULT);
    }
    layerFeat.setStyle(STYLE_HOVER);
    layerFeat.bringToFront?.();
    this._hovered = layerFeat;
  }

  _onOut(layerFeat) {
    if (layerFeat === this._selected) return;
    layerFeat.setStyle(STYLE_DEFAULT);
    this._hovered = null;
  }

  // ── GeoJSON 로딩 (sessionStorage 캐시) ────────────────────────────────────

  async _fetchGeojson() {
    const cached = sessionStorage.getItem(SESSION_KEY);
    if (cached) {
      return JSON.parse(cached);
    }

    const res = await fetch(GEOJSON_URL);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    try {
      sessionStorage.setItem(SESSION_KEY, JSON.stringify(data));
    } catch {
      // sessionStorage 용량 초과 시 무시 (파이어폭스 Private 모드 등)
    }
    return data;
  }
}
