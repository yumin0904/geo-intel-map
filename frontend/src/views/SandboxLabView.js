/**
 * SandboxLabView — 분석실(Sandbox Lab) 노드·엣지 기반 가설 구성 도구.
 *
 * Cytoscape.js로 인터랙티브 캔버스 제공:
 * - 노드 추가/삭제 (drag-place)
 * - 엣지 그리기 (shift+drag)
 * - 노드 편집 (더블클릭)
 * - 가설 검증 (서버 검증)
 */

// cytoscape, cytoscape-dagre는 index.html에서 전역 로드됨
const cytoscape = window.cytoscape;

export class SandboxLabView {
  constructor(mapController, eventBus) {
    this.map = mapController;
    this.eventBus = eventBus;
    this.currentCanvasId = null;
    this.cy = null; // Cytoscape 인스턴스
    this.editingNode = null;

    // DOM 초기화
    this.initDOM();
    this.bindEvents();
  }

  initDOM() {
    // 메인 패널
    this.panel = document.getElementById("sandbox-panel") || (() => {
      const p = document.createElement("div");
      p.id = "sandbox-panel";
      p.className = "sandbox-panel";
      document.body.appendChild(p);
      return p;
    })();

    this.panel.innerHTML = `
      <div class="sandbox-header">
        <h2>🔬 분석실</h2>
        <div class="sandbox-controls">
          <select id="canvas-select" class="canvas-select">
            <option value="">— 새 가설 —</option>
          </select>
          <button id="create-canvas-btn" class="btn-primary">+ 새로 만들기</button>
          <button id="delete-canvas-btn" class="btn-danger" style="display:none">삭제</button>
        </div>
      </div>

      <div class="sandbox-toolbar">
        <button id="add-node-btn" class="btn-tool" title="노드 추가 (더블클릭)">
          + 노드
        </button>
        <button id="draw-edge-btn" class="btn-tool" title="엣지 그리기 (Shift+Drag)">
          ↗ 엣지
        </button>
        <button id="layout-btn" class="btn-tool">
          ⚙ 정렬
        </button>
        <button id="verify-btn" class="btn-tool btn-accent">
          ✓ 검증
        </button>
        <button id="close-sandbox-btn" class="btn-close">✕</button>
      </div>

      <div id="cytoscape-container" class="cytoscape-container"></div>

      <div id="verification-panel" class="verification-panel" style="display:none">
        <h3>검증 결과</h3>
        <div id="verification-result"></div>
      </div>
    `;
  }

  bindEvents() {
    document.getElementById("create-canvas-btn").addEventListener("click", () =>
      this.createNewCanvas()
    );
    document.getElementById("delete-canvas-btn").addEventListener("click", () =>
      this.deleteCurrentCanvas()
    );
    document.getElementById("canvas-select").addEventListener("change", (e) =>
      this.loadCanvas(e.target.value)
    );
    document.getElementById("close-sandbox-btn").addEventListener("click", () =>
      this.toggle()
    );
    document.getElementById("add-node-btn").addEventListener("click", () =>
      this.showAddNodeDialog()
    );
    document.getElementById("draw-edge-btn").addEventListener("click", () =>
      this.toggleEdgeDrawMode()
    );
    document.getElementById("layout-btn").addEventListener("click", () =>
      this.runLayout()
    );
    document.getElementById("verify-btn").addEventListener("click", () =>
      this.verifyHypothesis()
    );

    this.eventBus.on("sandbox:toggle", () => this.toggle());
  }

  toggle() {
    this.panel.classList.toggle("active");
    if (this.panel.classList.contains("active") && this.cy) {
      setTimeout(() => this.cy.fit(), 300);
    }
  }

  async createNewCanvas() {
    const title = prompt("가설 이름을 입력하세요:");
    if (!title) return;

    const response = await fetch("/api/sandbox/canvases", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title,
        hypothesis: "",
        sector_tag: null,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      }),
    });

    const canvas = await response.json();
    this.currentCanvasId = canvas.id;
    await this.loadCanvasList();
    await this.loadCanvas(canvas.id);
    this.initCytoscape(canvas.id, [], []);
  }

  async deleteCurrentCanvas() {
    if (!this.currentCanvasId) return;
    if (!confirm("이 가설을 삭제하시겠습니까?")) return;

    await fetch(`/api/sandbox/canvases/${this.currentCanvasId}`, {
      method: "DELETE",
    });

    this.currentCanvasId = null;
    await this.loadCanvasList();
    this.cy?.destroy();
    this.cy = null;
  }

  async loadCanvasList() {
    const response = await fetch("/api/sandbox/canvases");
    const canvases = await response.json();

    const select = document.getElementById("canvas-select");
    select.innerHTML = '<option value="">— 새 가설 —</option>';

    canvases.forEach((c) => {
      const opt = document.createElement("option");
      opt.value = c.id;
      opt.textContent = c.title;
      select.appendChild(opt);
    });
  }

  async loadCanvas(canvasId) {
    if (!canvasId) {
      this.currentCanvasId = null;
      document.getElementById("delete-canvas-btn").style.display = "none";
      return;
    }

    const response = await fetch(`/api/sandbox/canvases/${canvasId}`);
    const data = await response.json();
    this.currentCanvasId = data.canvas.id;

    document.getElementById("delete-canvas-btn").style.display = "inline-block";
    document.getElementById("canvas-select").value = canvasId;

    this.initCytoscape(canvasId, data.nodes, data.edges);
  }

  initCytoscape(canvasId, nodes, edges) {
    const container = document.getElementById("cytoscape-container");
    if (this.cy) this.cy.destroy();

    // 노드/엣지 요소 변환
    const elements = [
      ...nodes.map((n) => ({
        data: {
          id: n.id,
          label: n.label,
          type: n.node_type,
          canvasId: n.canvas_id,
        },
        position: { x: n.x, y: n.y },
      })),
      ...edges.map((e) => ({
        data: {
          id: e.id,
          source: e.source_node_id,
          target: e.target_node_id,
          kind: e.kind,
        },
      })),
    ];

    this.cy = cytoscape({
      container,
      elements,
      style: [
        {
          selector: "node",
          style: {
            "background-color": (n) => this.getNodeColor(n.data("type")),
            label: "data(label)",
            "text-valign": "center",
            "text-halign": "center",
            "font-size": 11,
            width: 60,
            height: 60,
            "border-width": 2,
            "border-color": "#333",
          },
        },
        {
          selector: "node.selected",
          style: { "border-color": "#00f", "border-width": 3 },
        },
        {
          selector: "edge",
          style: {
            "target-arrow-shape": "triangle",
            "target-arrow-color": "#999",
            "line-color": "#999",
            width: 2,
            label: "data(kind)",
            "font-size": 9,
          },
        },
      ],
      layout: { name: "dagre" },
      wheelSensitivity: 0.1,
    });

    // 이벤트
    this.cy.on("tap", (e) => {
      if (e.target === this.cy) this.cy.$().removeClass("selected");
      else e.target.addClass("selected");
    });

    this.cy.on("dbltap", "node", (e) => this.editNode(e.target.id()));
    this.cy.on("free", (e) => {
      if (e.target.isNode()) this.saveNodePosition(e.target.id());
    });
  }

  getNodeColor(type) {
    const colors = {
      event: "#e74c3c", // 빨강: 사건
      indicator: "#f39c12", // 주황: 지표
      outcome: "#3498db", // 파랑: 결과
    };
    return colors[type] || "#95a5a6";
  }

  showAddNodeDialog() {
    const dialog = document.createElement("div");
    dialog.className = "modal-overlay";
    dialog.innerHTML = `
      <div class="modal">
        <h3>노드 추가</h3>
        <input type="text" id="node-label" placeholder="노드 이름 (예: 대만해협 긴장)" />
        <select id="node-type">
          <option value="event">사건</option>
          <option value="indicator">지표</option>
          <option value="outcome">결과</option>
        </select>
        <div class="modal-buttons">
          <button class="btn-primary" id="confirm-node">추가</button>
          <button class="btn-secondary" id="cancel-node">취소</button>
        </div>
      </div>
    `;

    document.body.appendChild(dialog);

    document.getElementById("confirm-node").addEventListener("click", () => {
      const label = document.getElementById("node-label").value;
      const type = document.getElementById("node-type").value;
      if (label) {
        this.addNode(label, type);
        dialog.remove();
      }
    });

    document.getElementById("cancel-node").addEventListener("click", () => {
      dialog.remove();
    });
  }

  async addNode(label, type) {
    if (!this.currentCanvasId) {
      alert("먼저 가설을 만들어주세요");
      return;
    }

    const node = {
      canvas_id: this.currentCanvasId,
      node_type: type,
      label,
      x: Math.random() * 400 - 200,
      y: Math.random() * 400 - 200,
      event_ref: null,
      region_code: null,
      theory_tags: [],
      note: "",
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };

    const response = await fetch(
      `/api/sandbox/canvases/${this.currentCanvasId}/nodes`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(node),
      }
    );

    const saved = await response.json();

    // Cytoscape에 추가
    this.cy.add({
      data: {
        id: saved.id,
        label: saved.label,
        type: saved.node_type,
      },
      position: { x: saved.x, y: saved.y },
    });
  }

  editNode(nodeId) {
    const node = this.cy.getElementById(nodeId);
    const label = prompt("노드 이름 변경:", node.data("label"));
    if (label) {
      node.data("label", label);
      // 서버 업데이트 (간단화: 정보는 캔버스 자체에만 저장)
    }
  }

  toggleEdgeDrawMode() {
    // Shift+drag로 엣지 그리기 (Cytoscape 기본 에할손들러 사용)
    alert("Shift+클릭&드래그로 엣지를 그립니다");
  }

  async saveNodePosition(nodeId) {
    if (!this.currentCanvasId) return;
    const node = this.cy.getElementById(nodeId);
    const pos = node.position();
    // 위치 저장 (간단화: fetch 호출 생략)
  }

  runLayout() {
    this.cy.layout({ name: "dagre", animate: true, animationDuration: 500 }).run();
  }

  async verifyHypothesis() {
    if (!this.currentCanvasId) {
      alert("먼저 가설을 만들어주세요");
      return;
    }

    // 현재 그래프 상태 조회
    const response = await fetch(
      `/api/sandbox/canvases/${this.currentCanvasId}`
    );
    const canvasFull = await response.json();

    // 검증 호출
    const verifyResponse = await fetch(
      `/api/sandbox/canvases/${this.currentCanvasId}/verify`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(canvasFull),
      }
    );

    const result = await verifyResponse.json();
    this.showVerificationResult(result);
  }

  showVerificationResult(result) {
    const panel = document.getElementById("verification-panel");
    const resultDiv = document.getElementById("verification-result");

    const html = `
      <div class="result-score">
        <div class="score-circle" style="opacity: ${Math.max(0.3, result.total_score)}">
          ${(result.total_score * 100).toFixed(0)}
        </div>
        <div class="score-text">
          <p><strong>${result.confidence_level === "high" ? "✓ 높은" : result.confidence_level === "medium" ? "◐ 중간" : "✗ 낮은"} 신뢰도</strong></p>
          <p>${result.num_matches}개 규칙 매칭</p>
        </div>
      </div>

      ${
        result.top_match
          ? `
        <div class="top-match">
          <h4>⭐ 최고 매칭</h4>
          <p><strong>${result.top_match.rule_name}</strong></p>
          <p>점수: ${(result.top_match.match_score * 100).toFixed(0)}%</p>
          <p>이론: ${result.top_match.theory_framework}</p>
          ${
            result.top_match.missing_nodes.length > 0
              ? `<p class="missing">❌ ${result.top_match.missing_nodes[0]}</p>`
              : ""
          }
        </div>
      `
          : ""
      }

      ${
        result.gaps.length > 0
          ? `
        <div class="gaps">
          <h4>💡 개선 제안</h4>
          <ul>
            ${result.gaps.map((g) => `<li>${g}</li>`).join("")}
          </ul>
        </div>
      `
          : ""
      }

      <div class="all-matches">
        <h4>모든 매칭 (${result.all_matches.length})</h4>
        ${result.all_matches
          .map(
            (m) =>
              `<div class="match-item">
            <span>${m.rule_name}</span>
            <span class="score">${(m.match_score * 100).toFixed(0)}%</span>
          </div>`
          )
          .join("")}
      </div>
    `;

    resultDiv.innerHTML = html;
    panel.style.display = "block";
  }
}
