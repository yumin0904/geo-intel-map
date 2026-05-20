/**
 * EventBus.js
 * 싱글톤 pub/sub — 컴포넌트 간 직접 참조 없이 이벤트로 통신.
 *
 * 이벤트 목록:
 *   layer:toggle  { id }                          — 패널 버튼 클릭
 *   layer:changed { id, status, visible }          — 상태/가시성 변경
 */
export class EventBus {
  constructor() {
    // event → callback[] 맵
    this._listeners = {};
  }

  on(event, cb) {
    (this._listeners[event] ??= []).push(cb);
  }

  off(event, cb) {
    if (!this._listeners[event]) return;
    this._listeners[event] = this._listeners[event].filter(fn => fn !== cb);
  }

  emit(event, data) {
    // slice()로 복사 후 순회 — 핸들러 안에서 off() 해도 안전
    (this._listeners[event] ?? []).slice().forEach(cb => cb(data));
  }
}
