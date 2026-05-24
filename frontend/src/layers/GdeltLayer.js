/**
 * GdeltLayer.js — GDELT 3-Stage Funnel 분쟁 이벤트 레이어
 *
 * confidence_score 체계:
 *   1.0 (ACLED 수준) — 현재 GDELT에서는 미사용
 *   0.8 교차검증    — 실선 원형 마커, 정상 투명도
 *   0.5 미검증      — 점선 테두리 + ⚠️ 뱃지, 낮은 투명도
 *
 * severity → 마커 반경 (5~18px)
 * QuadClass 4(물리적 충돌) → 빨강, QuadClass 3(언어) → 주황
 */

import { api } from '../services/api.js';

const GDELT_COLOR_HIGH = '#ff4444';   // QuadClass 4: Material Conflict
const GDELT_COLOR_LOW  = '#ff8800';   // QuadClass 3: Verbal Conflict
const UNVERIFIED_OPACITY = 0.55;
const VERIFIED_OPACITY   = 0.85;

export class GdeltLayer {
  constructor(map, eventBus = null) {
    this._map     = map;
    this._bus     = eventBus;
    this._layer   = null;
    this._visible = false;
    this._data    = null;
  }

  async load() {
    try {
      this._data = await api.get('/api/layers/gdelt');
    } catch (err) {
      console.warn('[GdeltLayer] 로드 실패:', err);
      this._data = { type: 'FeatureCollection', features: [] };
    }
    this._render();
  }

  _render() {
    if (this._layer) {
      this._map.removeLayer(this._layer);
      this._layer = null;
    }
    if (!this._data?.features?.length) return;

    this._layer = L.geoJSON(this._data, {
      pointToLayer: (feature, latlng) => this._makeMarker(feature, latlng),
      onEachFeature: (feature, layer) => this._bindEvents(feature, layer),
    });

    this._visible = true;
    this._layer.addTo(this._map);
  }

  _makeMarker(feature, latlng) {
    const p         = feature.properties;
    const verified  = !p.unverified;
    const quadClass = p.quad_class || 3;
    const color     = quadClass >= 4 ? GDELT_COLOR_HIGH : GDELT_COLOR_LOW;
    const radius    = 5 + Math.round((p.severity || 50) / 10);
    const opacity   = verified ? VERIFIED_OPACITY : UNVERIFIED_OPACITY;

    return L.circleMarker(latlng, {
      radius,
      color,
      fillColor:   color,
      fillOpacity: opacity,
      opacity,
      // 미검증 이벤트는 dashArray로 점선 테두리 표시
      dashArray: verified ? null : '4 3',
      weight:    verified ? 1.5 : 2,
    });
  }

  _bindEvents(feature, layer) {
    const p = feature.properties;
    const verified = !p.unverified;

    const badge    = verified
      ? '<span style="color:#4aff91;font-size:10px">✓ 교차검증</span>'
      : '<span style="color:#ffcc00;font-size:10px">⚠️ 미검증 (confidence=0.5)</span>';

    const urlLink = p.source_url
      ? `<a href="${p.source_url}" target="_blank" rel="noopener" style="color:#4a9eff;font-size:10px">출처 링크 →</a>`
      : '';

    layer.bindTooltip(
      `<b>${p.title}</b><br>severity ${p.severity} | ${badge}`,
      { sticky: true, className: 'gdelt-tooltip' }
    );

    layer.on('click', () => {
      layer.bindPopup(`
        <div style="min-width:220px;font-size:12px">
          <div style="font-weight:700;margin-bottom:4px">${p.title}</div>
          <div style="margin-bottom:6px">${badge}</div>
          <div>severity: ${p.severity} | Goldstein: ${p.goldstein ?? '—'}</div>
          <div>언급 횟수: ${p.num_mentions ?? '—'}</div>
          <div>지역: ${p.region_code || '—'}</div>
          <div style="margin-top:6px">${urlLink}</div>
        </div>
      `).openPopup();

      // TheoryPanel 연동
      if (this._bus) this._bus.emit('marker:click', {
        source_type:      p.source_type,
        theory_tags:      p.theory_tags || [],
        region_code:      p.region_code,
        title:            p.title,
        confidence_score: p.confidence_score,
      });
    });
  }

  setVisible(visible) {
    this._visible = visible;
    if (!this._layer) return;
    if (visible) this._layer.addTo(this._map);
    else         this._map.removeLayer(this._layer);
  }

  get featureCount() {
    return this._data?.features?.length ?? 0;
  }
}
