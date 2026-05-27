/**
 * LayerPanel.js
 * 좌측 사이드바 레이어 토글 UI.
 * LayerManager 상태를 읽고 EventBus로 toggle 명령을 내린다.
 * 진영 필터는 meta.filters 선언만으로 자동 렌더링된다.
 *
 * 하단: 국가 검색 드롭다운 — /api/country/list 데이터 소스
 *   선택 시 country:open(CountryPanel 열기) + country:flyto(지도 이동) 발신
 */

const API_BASE = 'http://localhost:8000';

export class LayerPanel {
  /**
   * @param {LayerManager} layerManager
   * @param {EventBus}     eventBus
   */
  constructor(layerManager, eventBus) {
    this._lm       = layerManager;
    this._bus      = eventBus;
    this._el       = null;
    this._countries = [];   // { iso3, name_ko, name_en }[]
  }

  /** 패널을 DOM에 마운트하고 이벤트 구독 시작 */
  mount(containerId) {
    this._el = document.getElementById(containerId);
    this._render();
    this._bus.on('layer:changed', ({ id }) => this._updateToggleBtn(id));
    this._fetchCountries();
  }

  // ─── 렌더링 ────────────────────────────────────────────────────

  _render() {
    this._el.innerHTML = `
      <div class="layer-panel__title">LAYERS</div>
      <div class="layer-panel__list"></div>
      <button class="study-mode-btn" title="이론 태그를 마커에 표시">STUDY MODE</button>
      <button class="library-btn" title="통합 라이브러리 열기">📚 라이브러리</button>
      <button class="sandbox-btn" title="분석실 열기">🔬 분석실</button>
      <div class="country-search">
        <div class="country-search__label">COUNTRY</div>
        <div class="country-search__wrap">
          <input
            class="country-search__input"
            type="text"
            placeholder="국가 검색..."
            autocomplete="off"
            spellcheck="false"
          />
          <ul class="country-search__dropdown" hidden></ul>
        </div>
      </div>
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

    this._el.querySelector('.library-btn').addEventListener('click', () => {
      this._bus.emit('library:toggle');
    });

    this._el.querySelector('.sandbox-btn').addEventListener('click', () => {
      this._bus.emit('sandbox:toggle');
    });

    this._initCountrySearch();
  }

  _buildItem({ id, meta, status, visible }) {
    const wrapper = document.createElement('div');
    wrapper.className = 'layer-item';
    wrapper.dataset.layerId = id;

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
        btn.style.setProperty('--filter-color', opt.color);

        btn.addEventListener('click', () => {
          const idx = filter.active.indexOf(opt.value);
          if (idx >= 0) {
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

  // ─── 국가 검색 ─────────────────────────────────────────────────

  async _fetchCountries() {
    try {
      const res = await fetch(`${API_BASE}/api/country/list`);
      if (!res.ok) return;
      this._countries = await res.json();
    } catch {
      // 백엔드 미기동 시 조용히 무시
    }
  }

  _initCountrySearch() {
    const input    = this._el.querySelector('.country-search__input');
    const dropdown = this._el.querySelector('.country-search__dropdown');

    const show = (items) => {
      dropdown.innerHTML = '';
      if (!items.length) {
        dropdown.hidden = true;
        return;
      }
      items.forEach(({ iso3, name_ko, name_en }) => {
        const li = document.createElement('li');
        li.className = 'country-search__item';
        li.innerHTML = `<span class="cs-name-ko">${name_ko}</span><span class="cs-name-en">${name_en}</span>`;
        li.addEventListener('mousedown', (e) => {
          // mousedown 우선 — blur보다 먼저 실행해 dropdown이 사라지지 않게 함
          e.preventDefault();
          this._selectCountry(iso3, name_ko, name_en, input, dropdown);
        });
        dropdown.appendChild(li);
      });
      dropdown.hidden = false;
    };

    input.addEventListener('focus', () => {
      // 포커스 시 전체 목록 표시
      show(this._countries);
    });

    input.addEventListener('input', () => {
      const q = input.value.trim().toLowerCase();
      if (!q) {
        show(this._countries);
        return;
      }
      const filtered = this._countries.filter(c =>
        c.name_ko.includes(q) ||
        c.name_en.toLowerCase().includes(q) ||
        c.iso3.toLowerCase().includes(q),
      );
      show(filtered);
    });

    input.addEventListener('blur', () => {
      // mousedown에서 e.preventDefault() 했으므로 선택 후엔 이미 처리됨
      dropdown.hidden = true;
    });

    // ESC 키로 닫기
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        dropdown.hidden = true;
        input.blur();
      }
    });
  }

  _selectCountry(iso3, name_ko, name_en, input, dropdown) {
    input.value = `${name_ko} (${iso3})`;
    dropdown.hidden = true;

    this._bus.emit('country:open',  { iso3, name_en });
    this._bus.emit('country:flyto', { iso3 });
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

    const spinner = btn.querySelector('.layer-item__spinner');
    if (layer.status === 'loading' && !spinner) {
      btn.insertAdjacentHTML('beforeend', '<span class="layer-item__spinner"></span>');
    } else if (layer.status !== 'loading' && spinner) {
      spinner.remove();
    }
  }
}
