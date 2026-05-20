/**
 * LayerManager.js
 * 레이어 등록·토글·상태 관리.
 * 새 레이어 추가 = register() 한 번 호출.
 *
 * 레이어 인터페이스 (각 레이어 클래스가 구현해야 할 메서드):
 *   load()              — 비동기 데이터 fetch + 지도에 추가
 *   setVisible(bool)    — 재요청 없이 show/hide
 *   destroy()           — 레이어 그룹 정리
 */
export class LayerManager {
  /**
   * @param {L.Map}    map
   * @param {EventBus} eventBus
   */
  constructor(map, eventBus) {
    this._map = map;
    this._bus = eventBus;
    // Map<id, { instance, meta, visible, status }>
    this._registry = new Map();

    // LayerPanel이 emit한 toggle 이벤트를 여기서 처리
    this._bus.on('layer:toggle', ({ id }) => this.toggle(id));
  }

  /**
   * 레이어를 레지스트리에 등록한다.
   * @param {string} id
   * @param {object} instance
   * @param {{ name: string, icon: string, defaultVisible?: boolean, filters?: object[] }} meta
   */
  register(id, instance, meta) {
    this._registry.set(id, {
      instance,
      meta,
      visible: false,
      // 'idle' | 'loading' | 'loaded' | 'error'
      status: 'idle',
    });

    if (meta.defaultVisible) {
      this._loadLayer(id);
    }
  }

  /** 토글: idle이면 처음 로드, 그 외엔 show/hide */
  toggle(id) {
    const entry = this._registry.get(id);
    if (!entry) return;

    if (entry.status === 'idle') {
      this._loadLayer(id);
    } else if (entry.status !== 'loading') {
      // loading 중 클릭은 무시 — 중복 요청 방지
      this.setVisible(id, !entry.visible);
    }
  }

  /** 데이터 재요청 없이 가시성만 변경 */
  setVisible(id, visible) {
    const entry = this._registry.get(id);
    if (!entry || entry.status !== 'loaded') return;

    entry.visible = visible;
    entry.instance.setVisible(visible);
    this._emitChanged(id);
  }

  /** LayerPanel이 현재 상태를 읽기 위해 사용 */
  getAll() {
    return Array.from(this._registry.entries()).map(([id, e]) => ({
      id,
      instance: e.instance,
      meta:     e.meta,
      visible:  e.visible,
      status:   e.status,
    }));
  }

  async _loadLayer(id) {
    const entry = this._registry.get(id);
    entry.status  = 'loading';
    entry.visible = true;
    this._emitChanged(id);

    try {
      await entry.instance.load();
      entry.status = 'loaded';
    } catch (err) {
      entry.status  = 'error';
      entry.visible = false;
      console.error(`[LayerManager] ${id} 로드 실패:`, err);
    }

    this._emitChanged(id);
  }

  _emitChanged(id) {
    const e = this._registry.get(id);
    this._bus.emit('layer:changed', { id, status: e.status, visible: e.visible });
  }
}
