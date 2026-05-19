/**
 * MapController.js
 * Leaflet 지도 초기화 및 생명주기 관리.
 * 향후 레이어 추가, 이벤트 바인딩이 모두 이 클래스를 통해 이루어진다.
 */

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
    this.containerId = containerId;
    this.map = null; // init() 호출 전까지 null
  }

  init() {
    // preferCanvas: true — 마커 1000개 이상 시 Canvas가 SVG보다 훨씬 빠름
    // (CLAUDE.md 성능 원칙: 1000+ 마커 시 canvas 사용)
    this.map = L.map(this.containerId, { preferCanvas: true })
      .setView(INITIAL_CENTER, INITIAL_ZOOM);

    L.tileLayer(TILE_URL, {
      attribution: TILE_ATTRIBUTION,
      maxZoom: 19,
      subdomains: 'abcd', // 여러 서브도메인에서 병렬로 타일 수신 → 로딩 속도 향상
    }).addTo(this.map);

    return this; // 메서드 체이닝 허용
  }

  destroy() {
    // 컴포넌트 제거 시 Leaflet 리소스 정리 — 메모리 누수 방지
    if (this.map) {
      this.map.remove();
      this.map = null;
    }
  }
}
