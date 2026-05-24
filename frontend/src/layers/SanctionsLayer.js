/**
 * SanctionsLayer.js — 제재 레짐 지도 레이어 (Phase 3 Step 8)
 *
 * sanctions.yaml → API → 국가 수준 버블 마커
 * 색상 체계:
 *   UN 다자 제재  → 보라 (#9b59b6)
 *   서방 다자 제재 → 주황 (#e67e22)
 *   단자(미국 등) → 파랑 (#3498db)
 *
 * 연관 이론:
 *   - Weaponized Interdependence (Farrell & Newman 2019)
 *   - Economic Coercion (Drezner 2011)
 */

import { api } from '../services/api.js';

const COLOR = {
  multilateral_un:      '#9b59b6',
  multilateral_western: '#e67e22',
  unilateral:           '#3498db',
};

const OPACITY = 0.55;

export class SanctionsLayer {
  /** @param {import('leaflet')} map  @param {object} [eventBus] */
  constructor(map, eventBus = null) {
    this._map      = map;
    this._bus      = eventBus;
    this._layer    = null;
    this._visible  = false;
    this._features = [];
  }

  async show() {
    if (this._visible) return;
    this._visible = true;

    if (!this._layer) {
      await this._load();
    } else {
      this._layer.addTo(this._map);
    }
  }

  hide() {
    if (!this._visible) return;
    this._visible = false;
    if (this._layer) this._map.removeLayer(this._layer);
  }

  async _load() {
    let data;
    try {
      data = await api.get('/api/layers/sanctions');
    } catch (err) {
      console.error('[Sanctions] API 오류:', err);
      return;
    }

    this._features = data.features || [];
    this._layer = this._buildLayer(this._features);
    if (this._visible) this._layer.addTo(this._map);
  }

  _buildLayer(features) {
    const circles = features.map(f => this._toCircle(f)).filter(Boolean);
    return L.layerGroup(circles);
  }

  _toCircle(feature) {
    const [lon, lat] = feature.geometry.coordinates;
    const p = feature.properties;

    const color   = COLOR[p.sanction_type] || COLOR.unilateral;
    const radius  = 20000 + p.severity * 1200;  // 심각도가 클수록 큰 원
    const bodies  = Array.isArray(p.sanctioning_bodies)
      ? p.sanctioning_bodies.join(', ')
      : p.sanctioning_bodies;

    const circle = L.circle([lat, lon], {
      radius,
      color,
      weight:      2,
      fillColor:   color,
      fillOpacity: OPACITY,
      opacity:     0.85,
    });

    const popupHtml = `
      <div class="sanction-popup">
        <div class="sanction-popup__title">${p.title}</div>
        <div class="sanction-popup__meta">
          <span class="tag">${p.target_country}</span>
          <span class="tag tag--year">${p.year_established}년~</span>
          <span class="tag tag--bodies">${bodies}</span>
        </div>
        <div class="sanction-popup__trigger">${p.trigger}</div>
        <div class="sanction-popup__severity">심각도 ${p.severity}</div>
      </div>
    `;

    circle.bindPopup(popupHtml, { maxWidth: 300 });

    circle.on('click', () => {
      if (this._bus) {
        this._bus.emit('marker:click', {
          id:          feature.id || p.regime_id,
          title:       p.title,
          description: p.description,
          theory_tags: p.theory_tags,
          source_type: 'sanction',
          region_code: p.region_code,
          severity:    p.severity,
          payload:     p,
        });
      }
    });

    return circle;
  }
}
