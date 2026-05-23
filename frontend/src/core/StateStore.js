/**
 * frontend/src/core/StateStore.js
 *
 * 경량 반응형 상태 저장소.
 * library 슬라이스를 포함하며, 향후 다른 전역 상태도 여기서 관리한다.
 *
 * 사용법:
 *   import { store } from './StateStore.js';
 *   const unsub = store.subscribe('library', state => render(state));
 *   store.setState('library', { sectorFilter: 'energy' });
 *   unsub(); // 구독 해제
 */

const _state = {
  library: {
    /** @type {Array<Object>} GET /api/library/theories 결과 */
    theories: [],
    /** @type {Record<string, string[]>} GET /api/library/region-index 결과 */
    regionIndex: {},
    /** 현재 열린 이론 ID (detail 뷰용) */
    selectedId: null,
    /** 'all' | 'maritime' | 'energy' | 'techno' | 'indo_pacific' | 'gray_zone' */
    sectorFilter: 'all',
    searchQuery: '',
    loading: false,
  },
};

/** @type {Record<string, Function[]>} */
const _listeners = {};

/**
 * 상태 슬라이스를 읽는다.
 * @param {string} key
 */
export function getState(key) {
  return _state[key];
}

/**
 * 상태를 업데이트하고 구독자에게 알린다.
 * @param {string} key
 * @param {Object|Function} updater  부분 객체 또는 prev => next 함수
 */
export function setState(key, updater) {
  const prev = _state[key];
  _state[key] = typeof updater === 'function'
    ? updater(prev)
    : { ...prev, ...updater };
  (_listeners[key] || []).forEach(cb => cb(_state[key]));
}

/**
 * 상태 변경을 구독한다.
 * @param {string}   key
 * @param {Function} callback
 * @returns {Function} unsubscribe 함수
 */
export function subscribe(key, callback) {
  if (!_listeners[key]) _listeners[key] = [];
  _listeners[key].push(callback);
  return () => {
    _listeners[key] = _listeners[key].filter(c => c !== callback);
  };
}

export const store = { getState, setState, subscribe };
