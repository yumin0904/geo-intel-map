/**
 * CascadeLayer.js
 * 인과(Cascade) 링크를 지도 위에 "trigger → response" 점선 화살표로 렌더링한다.
 * CLAUDE.md 3.4: 지도 뷰는 공간적 인과관계(점선 화살표)를 담당한다.
 *
 * 데이터: GET /api/cascade/links → { links, events, metadata }
 *   - link: source_event_id(트리거) → target_event_id(시장 반응)
 *   - 화살표는 "원인(분쟁) → 결과(유가)"의 방향을 시각화한다.
 *
 * 정치외교학 학습 포인트: 지역 분쟁(국지적 사건)이 SLOC(해상교통로)를 통해
 * 글로벌 시장 지표로 전이되는 과정을 한 화면에서 추적한다.
 */

import { api } from '../services/api.js';

const ARROW_COLOR    = '#ffe566'; // 노랑 — 눈에 잘 띄는 인과 전용 색
const TRIGGER_COLOR  = '#ff8c00'; // 트리거(분쟁) 출발점 오렌지
const RESPONSE_COLOR = '#ffe566'; // 반응(시장) 도착점 노랑

function fmtDelta(seconds) {
  const h = Math.round(seconds / 3600);
  if (h < 24) return `${h}시간`;
  return `${Math.round(h / 24)}일`;
}

function buildPopup(link, src, tgt) {
  const ev   = link.evidence;
  const pct  = ev.pct_change >= 0 ? `+${ev.pct_change}` : `${ev.pct_change}`;
  const dir  = ev.pct_change >= 0 ? '상승' : '하락';
  const wh   = ev.window_hours ?? Math.round(link.time_delta_seconds / 3600);
  const tags = (tgt.theory_tags ?? [])
    .map(t => `<span class="theory-tag">${t}</span>`)
    .join(' ');

  // 첫 줄에 한 문장 요약 — 비전공자도 즉시 이해할 수 있는 인과 서술
  const headline =
    `${src.title} (sev&nbsp;${src.severity}) → ${ev.ticker} ${pct}% ${dir} (${wh}시간 내)`;

  return `
    <div class="base-popup cascade-popup">
      <h3 class="base-popup__name">⛓ 인과 연쇄 — ${ev.region}</h3>
      <p class="cascade-popup__headline">${headline}</p>
      <table class="base-popup__table">
        <tr><td>① 원인</td><td><span style="color:${TRIGGER_COLOR}">${src.title}</span> (sev ${src.severity})</td></tr>
        <tr><td>② 결과</td><td><strong style="color:${RESPONSE_COLOR}">${ev.ticker} ${pct}% ${dir}</strong></td></tr>
        <tr><td>가격 변동</td><td>$${ev.baseline_price} → $${ev.extreme_price}</td></tr>
        <tr><td>반응 시간</td><td>${fmtDelta(link.time_delta_seconds)} 이내</td></tr>
        <tr><td>상관도</td><td>${(link.correlation_score * 100).toFixed(0)}%</td></tr>
      </table>
      <div class="base-popup__theory">
        <span class="theory-label">이론: ${(tgt.theory_tags ?? []).join(', ')}</span>
        <p>${link.theory_ref ?? ''}</p>
      </div>
      <div class="base-popup__tags">${tags}</div>
    </div>
  `;
}

export class CascadeLayer {
  /**
   * @param {L.Map}    map
   * @param {EventBus} eventBus  — cascade:loaded 이벤트로 TimelineView 등 구독자에게 데이터 공유
   */
  constructor(map, eventBus) {
    this.map = map;
    this._eventBus = eventBus;
    this._layerGroup = L.layerGroup();
    // 화살촉 갱신용: { marker, src:[lat,lon], tgt:[lat,lon] }
    this._arrows = [];
    this._onZoom = () => this._updateArrowheads();
  }

  async load() {
    let data;
    try {
      data = await api.get('/api/cascade/links');
    } catch (err) {
      console.error('[CascadeLayer] 데이터 로드 실패:', err);
      throw err;
    }

    // id로 이벤트 조회 가능하도록 맵 구성
    const eventsById = new Map((data.events ?? []).map(e => [e.id, e]));

    for (const link of data.links ?? []) {
      const src = eventsById.get(link.source_event_id);
      const tgt = eventsById.get(link.target_event_id);
      if (!src || !tgt) continue;
      this._renderLink(link, src, tgt);
    }

    this._layerGroup.addTo(this.map);
    this.map.on('zoomend', this._onZoom);
    this._updateArrowheads();
    console.info(`[CascadeLayer] ${(data.links ?? []).length}개 인과 링크 로드 완료`);

    // API 응답을 EventBus로 브로드캐스트 — TimelineView 등 구독자가 재사용
    // (동일 엔드포인트 이중 호출 방지: 1h 서버 캐시 + 이 단일 발화)
    this._eventBus?.emit('cascade:loaded', data);
  }

  _renderLink(link, src, tgt) {
    const a  = src.location; // [lat, lon]
    const b  = tgt.location;
    const ev = link.evidence;

    const pctLabel = `유가 ${ev.pct_change >= 0 ? '+' : ''}${ev.pct_change}%`;

    // 점선 인과 화살표 — weight/dashArray 3배로 확대, 노랑으로 변경
    const line = L.polyline([a, b], {
      color: ARROW_COLOR,
      weight: 7.5,
      opacity: 0.95,
      dashArray: '18 12',
      className: 'cascade-arrow',
    });
    line.bindPopup(buildPopup(link, src, tgt), { maxWidth: 420, className: 'geo-popup' });
    this._layerGroup.addLayer(line);

    // 출발점(분쟁) 원 — 원인임을 강조하기 위해 크게
    this._layerGroup.addLayer(L.circleMarker(a, {
      radius: 12, color: TRIGGER_COLOR, fillColor: TRIGGER_COLOR,
      fillOpacity: 0.85, weight: 2,
    }));

    // 도착점(시장) 다이아몬드 + 가격 레이블
    const tgtMarker = L.marker(b, {
      icon: L.divIcon({
        className: 'cascade-target',
        html: `
          <span class="cascade-target__dot"></span>
          <span class="cascade-target__label">${pctLabel}</span>
        `,
        iconSize: [80, 40],
        iconAnchor: [15, 15],
      }),
    });
    tgtMarker.bindPopup(buildPopup(link, src, tgt), { maxWidth: 420, className: 'geo-popup' });
    this._layerGroup.addLayer(tgtMarker);

    // 화살촉 — 크기 3배, 줌마다 방위각 재계산
    const head = L.marker(b, {
      icon: L.divIcon({
        className: 'cascade-arrowhead',
        html: '<span class="cascade-arrowhead__glyph">▶</span>',
        iconSize: [28, 28],
        iconAnchor: [14, 14],
      }),
      interactive: false,
    });
    this._layerGroup.addLayer(head);
    this._arrows.push({ marker: head, src: a, tgt: b });
  }

  /** 화살촉을 출발→도착 방위각에 맞춰 회전시킨다 (화면 픽셀 기준). */
  _updateArrowheads() {
    for (const { marker, src, tgt } of this._arrows) {
      const pa = this.map.latLngToContainerPoint(src);
      const pb = this.map.latLngToContainerPoint(tgt);
      const angle = Math.atan2(pb.y - pa.y, pb.x - pa.x) * 180 / Math.PI;
      const el = marker.getElement();
      if (el) {
        const glyph = el.querySelector('.cascade-arrowhead__glyph');
        if (glyph) glyph.style.transform = `rotate(${angle}deg)`;
      }
    }
  }

  setVisible(visible) {
    if (visible) {
      this._layerGroup.addTo(this.map);
      this.map.on('zoomend', this._onZoom);
      this._updateArrowheads();
    } else {
      this._layerGroup.remove();
      this.map.off('zoomend', this._onZoom);
    }
  }

  destroy() {
    this.map.off('zoomend', this._onZoom);
    this._layerGroup.clearLayers();
    this._layerGroup.remove();
    this._arrows = [];
  }
}
