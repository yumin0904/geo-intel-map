/**
 * api.js — 백엔드 HTTP 클라이언트
 * 모든 fetch 호출을 여기서 중앙화한다.
 * CLAUDE.md: 외부 API 응답은 Event로 정규화 후 반환 (백엔드 담당), 여기선 단순 GET/POST만.
 */

const BASE_URL = 'http://localhost:8000';

export const api = {
  BASE_URL,
  /**
   * GET 요청 — JSON 파싱 후 반환
   * @param {string} path - '/api/layers/military-bases' 등
   * @returns {Promise<any>}
   */
  async get(path) {
    const res = await fetch(`${BASE_URL}${path}`);
    if (!res.ok) {
      throw new Error(`API 오류 ${res.status}: ${path}`);
    }
    return res.json();
  },
};
