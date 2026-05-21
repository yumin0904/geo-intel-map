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

// 초기 뷰: 경도 175° — 날짜변경선 기준
// 진주만(-157° = 203°)이 중심 기준 +28° 우측, 일본(140°)이 -35° 좌측
// 태평양 케이블 전체 가시 + 아시아-하와이 균형
const INITIAL_CENTER = [20.0, 175.0];
const INITIAL_ZOOM   = 3;

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
    // worldCopyJump: 날짜변경선을 넘어 패닝할 때 지도가 자연스럽게 이어지도록
    this.map = L.map(this.containerId, { preferCanvas: true, zoomControl: false, worldCopyJump: true })
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
