/**
 * LayerPanel.js
 * 좌측 사이드바 레이어 토글 UI.
 * LayerManager 상태를 읽고 EventBus로 toggle 명령을 내린다.
 * 진영 필터는 meta.filters 선언만으로 자동 렌더링된다.
 */
export class LayerPanel {
  /**
   * @param {LayerManager} layerManager
   * @param {EventBus}     eventBus
   */
  constructor(layerManager, eventBus) {
    this._lm  = layerManager;
    this._bus = eventBus;
    this._el  = null;
  }

  /** 패널을 DOM에 마운트하고 이벤트 구독 시작 */
  mount(containerId) {
    this._el = document.getElementById(containerId);
    this._render();
    // 레이어 상태 변경 시 해당 버튼만 업데이트
    this._bus.on('layer:changed', ({ id }) => this._updateToggleBtn(id));
  }

  // ─── 렌더링 ────────────────────────────────────────────────────

  _render() {
    this._el.innerHTML = `
      <div class="layer-panel__title">LAYERS</div>
      <div class="layer-panel__list"></div>
      <button class="study-mode-btn" title="이론 태그를 마커에 표시">STUDY MODE</button>
    `;
    const list = this._el.querySelector('.layer-panel__list');
    for (const layer of this._lm.getAll()) {
      list.appendChild(this._buildItem(layer));
    }

    this._el.querySelector('.study-mode-btn').addEventListener('click', e => {
      const active = document.body.classList.toggle('study-mode');
      e.currentTarget.classList.toggle('is-active', active);
      this._bus.emit('studymode:changed', { active });
    });
  }

  _buildItem({ id, meta, status, visible }) {
    const wrapper = document.createElement('div');
    wrapper.className = 'layer-item';
    wrapper.dataset.layerId = id;

    // 토글 버튼 — 로딩 중이면 스피너 표시
    const btnEl = document.createElement('button');
    btnEl.className = `layer-item__btn${visible ? ' is-active' : ''}`;
    btnEl.dataset.id = id;
    btnEl.innerHTML = `
      <span class="layer-item__icon">${meta.icon}</span>
      <span class="layer-item__name">${meta.name}</span>
      ${status === 'loading' ? '<span class="layer-item__spinner"></span>' : ''}
    `;
    btnEl.addEventListener('click', () => this._bus.emit('layer:toggle', { id }));
    wrapper.appendChild(btnEl);

    // 진영 필터 — meta.filters 선언이 있는 레이어만 렌더링
    if (meta.filters) {
      wrapper.appendChild(this._buildFilters(id, meta.filters));
    }

    return wrapper;
  }

  /** meta.filters 배열로 필터 버튼 그룹을 동적 렌더링 */
  _buildFilters(layerId, filters) {
    const container = document.createElement('div');
    container.className = 'layer-filters-wrap';

    filters.forEach(filter => {
      const group = document.createElement('div');
      group.className = 'layer-filters';
      group.dataset.filterGroup = filter.id;

      filter.options.forEach(opt => {
        const btn = document.createElement('button');
        btn.className = `filter-btn${filter.active.includes(opt.value) ? ' is-active' : ''}`;
        btn.dataset.value = opt.value;
        btn.textContent = opt.label;
        // CSS 변수로 주입 — 컴포넌트 내 색상 하드코딩 금지
        btn.style.setProperty('--filter-color', opt.color);

        btn.addEventListener('click', () => {
          const idx = filter.active.indexOf(opt.value);
          if (idx >= 0) {
            // 마지막 하나는 끌 수 없음 — 항상 최소 1개 활성화
            if (filter.active.length === 1) return;
            filter.active.splice(idx, 1);
            btn.classList.remove('is-active');
          } else {
            filter.active.push(opt.value);
            btn.classList.add('is-active');
          }
          filter.onChange(filter.active.slice());
        });

        group.appendChild(btn);
      });

      container.appendChild(group);
    });

    return container;
  }

  // ─── 상태 업데이트 ─────────────────────────────────────────────

  /** layer:changed 이벤트 수신 시 토글 버튼만 업데이트 */
  _updateToggleBtn(id) {
    const wrapper = this._el?.querySelector(`[data-layer-id="${id}"]`);
    if (!wrapper) return;

    const layer = this._lm.getAll().find(l => l.id === id);
    if (!layer) return;

    const btn = wrapper.querySelector('.layer-item__btn');
    btn.classList.toggle('is-active', layer.visible);

    // 로딩 스피너 on/off
    const spinner = btn.querySelector('.layer-item__spinner');
    if (layer.status === 'loading' && !spinner) {
      btn.insertAdjacentHTML('beforeend', '<span class="layer-item__spinner"></span>');
    } else if (layer.status !== 'loading' && spinner) {
      spinner.remove();
    }
  }
}
