/**
 * MapController.js
 * Leaflet 지도 초기화 및 생명주기 관리.
 * EventBus / LayerManager를 소유하며, 레이어 등록은 index.html에서 수행한다.
 */

import { EventBus }    from './EventBus.js';
import { LayerManager } from './LayerManager.js';

// CartoDB Dark Matter — 무료, API 키 불필요, 다크 인텔리전스 분위기에 최적
const TILE_URL = 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png';
const TILE_ATTRIBUTION =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> ' +
  '&copy; <a href="https://carto.com/">CARTO</a>';

// 초기 뷰: 대만해협·한반도 중심 (CLAUDE.md 5대 섹터 — 인도-태평양 군사 대치 지역)
const INITIAL_CENTER = [25, 125];
const INITIAL_ZOOM   = 4;

export class MapController {
  constructor(containerId) {
    this.containerId  = containerId;
    this.map          = null;
    this.eventBus     = new EventBus();
    this.layerManager = null;
  }

  init() {
    // preferCanvas: true — 마커 1000개 이상 시 Canvas가 SVG보다 훨씬 빠름
    // zoomControl: false — 줌 버튼 숨김, 마우스 휠 줌만 사용 (사이드바와 공간 충돌 방지)
    this.map = L.map(this.containerId, { preferCanvas: true, zoomControl: false })
      .setView(INITIAL_CENTER, INITIAL_ZOOM);

    L.tileLayer(TILE_URL, {
      attribution: TILE_ATTRIBUTION,
      maxZoom: 19,
      subdomains: 'abcd',
    }).addTo(this.map);

    this.layerManager = new LayerManager(this.map, this.eventBus);

    return this;
  }

  destroy() {
    if (this.map) {
      this.map.remove();
      this.map = null;
    }
  }
}
