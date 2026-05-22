/**
 * NotebookPanel.js
 * Study Mode 켜진 상태에서 TheoryPanel 하단에 노트 입력창을 표시한다.
 * 이벤트 id 기준으로 PUT /api/study/notes/:id 에 자동 저장 (1초 debounce).
 *
 * CLAUDE.md 6.3 Notebook 명세 구현:
 *   "이벤트별로 메모 저장 (로컬 SQLite)"
 *
 * 사용법:
 *   const nb = new NotebookPanel();
 *   theoryPanel.setNotebook(nb);
 *   // 이후 TheoryPanel이 _show()/_hide() 시 nb.show()/nb.hide() 자동 호출
 */

const SAVE_DEBOUNCE_MS = 1000;
const API_BASE = 'http://localhost:8000';

export class NotebookPanel {
  constructor() {
    this._eventId   = null;
    this._saveTimer = null;
  }

  /**
   * TheoryPanel._show() 이후 호출된다.
   * @param {string}      eventId  - Event.id (UUID4)
   * @param {HTMLElement} slotEl   - TheoryPanel 내 .notebook-slot 요소
   */
  async show(eventId, slotEl) {
    this._eventId = eventId;
    if (!slotEl) return;

    slotEl.innerHTML = this._buildHTML();

    const textarea = slotEl.querySelector('.notebook__textarea');
    const statusEl = slotEl.querySelector('.notebook__status');

    // 기존 저장 노트 불러오기
    try {
      const res  = await fetch(`${API_BASE}/api/study/notes/${encodeURIComponent(eventId)}`);
      const data = await res.json();
      if (data.content) textarea.value = data.content;
    } catch {
      // 실패해도 빈 창으로 계속 사용 가능
    }

    // 입력 시 debounce 자동 저장
    textarea.addEventListener('input', () => {
      statusEl.textContent = '';
      clearTimeout(this._saveTimer);
      this._saveTimer = setTimeout(
        () => this._save(textarea, statusEl),
        SAVE_DEBOUNCE_MS,
      );
    });
  }

  /** TheoryPanel._hide() 시 호출 — 진행 중인 저장 타이머 정리 */
  hide() {
    clearTimeout(this._saveTimer);
    this._eventId = null;
  }

  async _save(textarea, statusEl) {
    if (!this._eventId) return;
    statusEl.textContent = '저장 중...';
    try {
      const res = await fetch(
        `${API_BASE}/api/study/notes/${encodeURIComponent(this._eventId)}`,
        {
          method:  'PUT',
          headers: { 'Content-Type': 'application/json' },
          body:    JSON.stringify({ content: textarea.value }),
        },
      );
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      statusEl.textContent = '저장됨 ✓';
      // 2초 후 상태 메시지 제거
      setTimeout(() => { statusEl.textContent = ''; }, 2000);
    } catch (err) {
      statusEl.textContent = '저장 실패 ✗';
      console.error('[NotebookPanel] save error:', err);
    }
  }

  _buildHTML() {
    return `
      <div class="notebook">
        <div class="notebook__header">
          <span class="notebook__icon">📓</span>
          <span class="notebook__title">학습 노트</span>
          <span class="notebook__status"></span>
        </div>
        <textarea
          class="notebook__textarea"
          placeholder="이 이벤트에 대한 분석, 의문점, 이론 적용 메모를 남겨보세요..."
          rows="5"
        ></textarea>
      </div>
    `;
  }
}
