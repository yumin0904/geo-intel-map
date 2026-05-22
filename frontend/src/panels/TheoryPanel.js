/**
 * TheoryPanel.js
 * 마커 클릭 시 우측에서 슬라이드인 — theory_tags를 이론 카드로 변환해 표시.
 * CLAUDE.md 6.1 Theory Panel 명세 구현.
 *
 * EventBus 이벤트:
 *   수신: marker:click { theory_tags, title, timestamp, severity, ... }
 *   수신: marker:close  (지도 클릭, ESC 등)
 */

// ── 이론 데이터베이스 ────────────────────────────────────────────────
// theory_tag → 카드 데이터. 새 이론 추가 시 여기에만 추가하면 됨.
const THEORY_DB = {

  gray_zone: {
    name: 'Gray Zone Strategy',
    scholars: 'Hoffman (2007), Mazarr (2015)',
    summary: '선전포고 없이 현상변경을 시도하는 모호한 강압 전술의 총칭.',
    detail: '국가·비국가 행위자가 군사적 충돌 임계점 직하에서 심리전·경제압박·해상민병대를 조합해 상대방의 대응을 어렵게 만드는 전략. 후티의 홍해 공격이 전형적 사례.',
    cascade_rules: ['bab_el_mandeb_tension_to_oil'],
    reading: [
      { title: 'Hoffman (2007) — Conflict in the 21st Century', url: 'https://www.potomacinstitute.org/images/stories/publications/potomac_hybridwar_0108.pdf' },
      { title: 'Mazarr (2015) — Mastering the Gray Zone', url: 'https://press.armywarcollege.edu/cgi/viewcontent.cgi?article=1090&context=monographs' },
    ],
  },

  hybrid_warfare: {
    name: 'Hybrid Warfare',
    scholars: 'Gerasimov (2013), Hoffman (2007)',
    summary: '정규전·비정규전·정보전·사이버전을 동시에 구사하는 복합 전쟁 방식.',
    detail: '러시아의 2014 우크라이나 개입과 2022 전면전이 대표 사례. 군사력·경제·선전을 혼합해 상대방의 대응 수단을 무력화한다. 식량·에너지 무기화와 연결.',
    cascade_rules: ['ukraine_conflict_to_wheat'],
    reading: [
      { title: 'Gerasimov (2013) — The Value of Science Is in the Foresight', url: 'https://www.armyupress.army.mil/Portals/7/military-review/Archives/English/MilitaryReview_20160228_art008.pdf' },
    ],
  },

  A2AD: {
    name: 'A2/AD Strategy (반접근/지역거부)',
    scholars: 'Krepinevich (2010), CSBA',
    summary: '적 전력이 특정 해역·공역에 접근하거나 작전하지 못하도록 막는 군사전략.',
    detail: '중국의 DF-21D 대함탄도미사일·잠수함·해상민병대가 미군의 제1열도선 내 자유항행을 차단하는 것이 전형적 사례. 대만해협·남중국해가 핵심 마찰 공간.',
    // 해양 접근거부 전략 — 내륙 분쟁(미얀마·우크라이나 등)에서는 카드 숨김
    geo_filter: ['taiwan_strait', 'south_china_sea', 'east_china_sea'],
    cascade_rules: ['taiwan_strait_to_tsm', 'taiwan_strait_to_soxx', 'south_china_sea_to_defense'],
    reading: [
      { title: 'CSBA — AirSea Battle (2010)', url: 'https://csbaonline.org/research/publications/airsea-battle-a-point-of-departure-operational-concept' },
    ],
  },

  conventional_warfare: {
    name: 'Conventional Warfare',
    scholars: 'Clausewitz (1832)',
    summary: '국가 간 선포된 정규 군사력 충돌.',
    detail: '규칙과 국제법 틀 안에서 군대 간 직접 교전. 현대에는 순수 재래전은 드물며, 회색지대·하이브리드전과 혼합되는 경우가 많다.',
    cascade_rules: [],   // 재래전 자체는 지역 무관 — 좌표 기반 필터로 해당 지역 룰이 있으면 자동 표시
    reading: [
      { title: 'Clausewitz — On War (1832)', url: 'https://www.gutenberg.org/ebooks/1946' },
    ],
  },

  irregular_warfare: {
    name: 'Irregular Warfare',
    scholars: 'Galula (1964), Kilcullen (2009)',
    summary: '비정규 전투원이 참여하는 비전통적 무력분쟁.',
    detail: '게릴라전·반란진압·테러 등이 포함. ACLED 데이터의 상당 부분이 이 유형. 약소 행위자가 강대국에 비대칭적으로 대응하는 방식이다.',
    cascade_rules: [],   // 비정규전도 지역 무관 — 좌표 기반 필터가 해당 지역 룰 자동 선택
    reading: [
      { title: 'Kilcullen (2009) — The Accidental Guerrilla', url: null },
    ],
  },

  political_instability: {
    name: 'Political Instability / 국가 취약성',
    scholars: 'Rotberg (2004), Fund for Peace (FSI)',
    summary: '정권 정당성 약화·경제 위기·사회 분열로 국가 기능이 붕괴하는 과정.',
    detail: 'ACLED 분쟁 데이터와 높은 상관관계. 취약국은 강대국의 대리전 무대가 되기 쉽고, 지역 패권 경쟁의 진공 지대를 형성한다.',
    cascade_rules: [],   // 정치 불안도 지역 무관 — 좌표가 ukraine/middle_east bbox 안이면 자동 연결
    reading: [
      { title: 'Fund for Peace — Fragile States Index', url: 'https://fragilestatesindex.org/' },
    ],
  },

  // ── 미래 확장 태그 (현재 ACLED 이벤트엔 없지만 룰북과 연결됨) ───

  sloc: {
    name: 'SLOC Interdiction (Mahan 해양력)',
    scholars: 'Mahan (1890), Till (2004)',
    summary: '해상교통로(SLOC) 통제권이 국가 패권의 핵심 조건.',
    detail: '호르무즈·바브엘만데브·말라카·수에즈 등 초크포인트가 전략적 가치를 갖는 이유. 통제하거나 차단하면 세계 무역·에너지 흐름을 좌우할 수 있다.',
    // 해양 이론 — 내륙 분쟁에서는 카드 숨김
    geo_filter: ['taiwan_strait', 'south_china_sea', 'east_china_sea', 'hormuz', 'bab_el_mandeb', 'suez', 'malacca'],
    cascade_rules: ['bab_el_mandeb_tension_to_oil', 'hormuz_tension_to_oil', 'suez_tension_to_shipping'],
    reading: [
      { title: 'Mahan (1890) — The Influence of Sea Power upon History', url: 'https://www.gutenberg.org/ebooks/13529' },
    ],
  },

  resource_weaponization: {
    name: 'Resource Weaponization',
    scholars: 'Hirschman (1945), Drezner (2015)',
    summary: '에너지·식량·금융 등 경제적 상호의존을 강압 수단으로 전환하는 전략.',
    detail: '러시아의 가스 외교, 중국의 희토류 수출 제한이 대표 사례. 수입국의 취약성이 높을수록 무기화 효과가 크다.',
    cascade_rules: ['hormuz_tension_to_oil', 'ukraine_conflict_to_wheat', 'south_china_sea_to_lng'],
    reading: [
      { title: 'Hirschman (1945) — National Power and the Structure of Foreign Trade', url: null },
    ],
  },

  weaponized_interdependence: {
    name: 'Weaponized Interdependence',
    scholars: 'Farrell & Newman (2019)',
    summary: '글로벌 네트워크 허브 지위를 전략적 강압 수단으로 전환하는 메커니즘.',
    detail: '달러 결제망(SWIFT), 반도체 공급망, 클라우드 인프라 등이 특정 국가에 집중될 때 그 국가가 갖는 비대칭적 권력.',
    cascade_rules: ['taiwan_strait_to_tsm', 'taiwan_strait_to_soxx'],
    reading: [
      { title: 'Farrell & Newman (2019) — Weaponized Interdependence', url: 'https://www.journals.uchicago.edu/doi/10.1086/703642' },
    ],
  },

  safe_haven: {
    name: 'Safe Haven Theory',
    scholars: 'Baur & Lucey (2010), Erb & Harvey (2013)',
    summary: '지정학 위기 시 투자자가 국가 신용리스크 없는 자산으로 이동.',
    detail: '금·미국채·스위스프랑이 대표적 안전자산. "Risk-off" 심리가 강해지면 주식·이머징 자산에서 자금이 이탈한다.',
    cascade_rules: ['middle_east_conflict_to_gold'],
    reading: [
      { title: 'Baur & Lucey (2010) — Is Gold a Hedge or a Safe Haven?', url: null },
    ],
  },

  korea_discount: {
    name: 'Korea Discount / Extended Deterrence',
    scholars: 'Cha (2002), 국제금융센터',
    summary: '한반도 지정학 리스크가 한국 자산 밸류에이션을 구조적으로 낮추는 현상.',
    detail: '미국 핵우산(확장억제) 신뢰성이 흔들릴 때마다 원화 약세·KOSPI 하락이 동반된다.',
    cascade_rules: ['north_korea_missile_to_krw', 'korean_tension_to_kospi'],
    reading: [
      { title: 'Cha (2002) — Korea\'s Place in the Axis', url: null },
    ],
  },

  food_security: {
    name: 'Food Security as Geopolitical Weapon',
    scholars: 'Patel & Moore (2009), FAO',
    summary: '식량 공급망 집중이 정치적 강압 수단이 되는 구조.',
    detail: '우크라이나·러시아가 세계 밀 28% 담당. 봉쇄 시 식량 수입 의존국에서 정치 불안 발생 (아랍의 봄 패턴).',
    cascade_rules: ['ukraine_conflict_to_wheat'],
    reading: [
      { title: 'FAO — 흑해 곡물협정 보고서 (2022)', url: 'https://www.fao.org/newsroom/detail/ukraine-war-imposes-heavy-costs-on-world-food-systems/en' },
    ],
  },

  forward_deployment: {
    name: 'Forward Deployment (전진배치)',
    scholars: 'Posen (2003), Brose (2020)',
    summary: '본토에서 멀리 떨어진 거점에 군사력을 미리 배치해 억제력을 투사하는 전략.',
    detail: '미국의 괌·오키나와·한국 주둔이 대표 사례. 신속 대응 능력을 높이지만 현지 사회·정치적 마찰을 유발한다.',
    cascade_rules: ['south_china_sea_to_defense', 'taiwan_strait_to_tsm'],
    reading: [
      { title: 'Posen (2003) — Command of the Commons', url: 'https://www.jstor.org/stable/3092069' },
    ],
  },

  alliance_theory: {
    name: 'Alliance Theory',
    scholars: 'Waltz (1979), Walt (1987)',
    summary: '국가들이 위협에 대응해 동맹을 형성하고 유지하는 방식에 관한 이론.',
    detail: '세력균형(Waltz): 강대국 부상에 대항해 연합. 위협균형(Walt): 능력뿐 아니라 의도·인접성도 고려. 비대칭 동맹에서 안보-자율성 교환 딜레마가 핵심.',
    cascade_rules: ['south_china_sea_to_defense', 'korean_tension_to_kospi'],
    reading: [
      { title: 'Walt (1987) — The Origins of Alliances', url: null },
    ],
  },
};

// 이론 카드의 geo_filter에서 사용하는 지역 bbox [minLon, minLat, maxLon, maxLat]
// regions.yaml의 theory_geo_filters와 동기화. RULE_REGIONS에 없는 지역도 포함.
const THEORY_GEO_BBOXES = {
  taiwan_strait:   [118.0, 22.0, 122.0, 26.0],
  south_china_sea: [105.0,  3.0, 122.0, 22.0],
  east_china_sea:  [118.0, 24.0, 132.0, 40.0],  // 동중국해 — A2AD 마찰 공간 북방
  hormuz:          [ 53.0, 23.0,  60.0, 30.0],
  bab_el_mandeb:   [ 42.0, 11.0,  45.5, 14.5],
  suez:            [ 31.5, 28.0,  34.5, 32.5],
  malacca:         [ 98.0,  1.0, 104.0,  6.5],
};

/** 좌표가 geo_filter 지역 중 하나라도 안에 있는지 판정 */
function isInAnyTheoryRegion(lon, lat, regionIds) {
  return regionIds.some(id => {
    const bbox = THEORY_GEO_BBOXES[id];
    if (!bbox) return false;
    const [minLon, minLat, maxLon, maxLat] = bbox;
    return lon >= minLon && lon <= maxLon && lat >= minLat && lat <= maxLat;
  });
}

// cascade rule별 trigger region bbox [minLon, minLat, maxLon, maxLat]
// regions.yaml과 동기화 — 이벤트 좌표가 이 안에 있을 때만 rule을 표시
const RULE_REGIONS = {
  bab_el_mandeb_tension_to_oil: [42.0,  11.0, 45.5,  14.5],
  hormuz_tension_to_oil:        [53.0,  23.0, 60.0,  30.0],
  taiwan_strait_to_tsm:         [118.0, 22.0, 122.0, 26.0],
  taiwan_strait_to_soxx:        [118.0, 22.0, 122.0, 26.0],
  south_china_sea_to_defense:   [105.0,  3.0, 122.0, 22.0],
  south_china_sea_to_lng:       [105.0,  3.0, 122.0, 22.0],
  north_korea_missile_to_krw:   [124.0, 37.5, 130.5, 42.7],
  suez_tension_to_shipping:     [31.5,  28.0,  34.5, 32.5],
  ukraine_conflict_to_wheat:    [22.0,  44.0,  40.5, 52.5],
  middle_east_conflict_to_gold: [35.0,  15.0,  65.0, 37.0],
  korean_tension_to_kospi:      [124.0, 33.5, 130.5, 43.0],
};

/** 이벤트 좌표가 rule의 trigger region 안에 있는지 판정 */
function isInRegion(lon, lat, ruleId) {
  const bbox = RULE_REGIONS[ruleId];
  if (!bbox) return false;
  const [minLon, minLat, maxLon, maxLat] = bbox;
  return lon >= minLon && lon <= maxLon && lat >= minLat && lat <= maxLat;
}

// cascade_rules.yaml rule_id → 한국어 요약 (API 응답 보조)
const RULE_LABEL = {
  bab_el_mandeb_tension_to_oil: '바브엘만데브 → 유가(CL=F)',
  hormuz_tension_to_oil:         '호르무즈 → 유가(CL=F)',
  taiwan_strait_to_tsm:          '대만해협 → TSMC(TSM)',
  taiwan_strait_to_soxx:         '대만해협 → 반도체 ETF(SOXX)',
  south_china_sea_to_defense:    '남중국해 → 방산주(ITA)',
  south_china_sea_to_lng:        '남중국해 → 천연가스(NG=F)',
  north_korea_missile_to_krw:    '북한 도발 → 환율(KRW=X)',
  suez_tension_to_shipping:      '수에즈 → 해운주(ZIM)',
  ukraine_conflict_to_wheat:     '우크라이나 → 밀(ZW=F)',
  middle_east_conflict_to_gold:  '중동 → 금(GLD)',
  korean_tension_to_kospi:       '한반도 → KOSPI(^KS11)',
};

// ── 패널 컴포넌트 ────────────────────────────────────────────────────
export class TheoryPanel {
  /** @param {import('../core/EventBus.js').EventBus} eventBus */
  constructor(eventBus) {
    this._eventBus    = eventBus;
    this._el          = null;
    this._cascadeLinks = [];  // /api/cascade/links 캐시
  }

  mount(containerId) {
    this._el = document.getElementById(containerId);
    if (!this._el) return;

    this._eventBus.on('marker:click', (props) => this._show(props));
    this._eventBus.on('marker:close', ()       => this._hide());

    // ESC 키로 닫기
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') this._hide();
    });

    this._loadCascadeLinks();
  }

  async _loadCascadeLinks() {
    try {
      const data = await fetch('/api/cascade/links').then(r => r.json());
      this._cascadeLinks = data.links ?? [];
    } catch {
      // 서버 미응답 시 빈 배열 유지 — 패널은 정상 표시
      this._cascadeLinks = [];
    }
  }

  _show(props) {
    const tags     = props.theory_tags ?? [];
    const lon      = props._lon ?? null;
    const lat      = props._lat ?? null;
    const theories = tags
      .map(t => THEORY_DB[t])
      .filter(Boolean)
      .filter(t => {
        // geo_filter가 없으면 항상 표시 (비지역 한정 이론)
        if (!t.geo_filter) return true;
        // 좌표 없으면 일단 표시 (군사기지 등 좌표 누락 방어)
        if (lon == null || lat == null) return true;
        // 좌표가 geo_filter 지역 중 하나라도 포함되면 표시
        return isInAnyTheoryRegion(lon, lat, t.geo_filter);
      });

    // 이 이벤트의 이론 태그 cascade_rules + 좌표가 region bbox 안에 있는 모든 룰 수집
    // 두 가지 소스를 합산: (1) 이론 태그 직접 연결, (2) 좌표 기반 자동 매핑
    const tagRuleIds = new Set(theories.flatMap(t => t.cascade_rules ?? []));

    const coordRuleIds = (lon != null && lat != null)
      ? new Set(Object.keys(RULE_REGIONS).filter(id => isInRegion(lon, lat, id)))
      : new Set();

    // 합집합 — 이론 태그 기반 + 좌표 기반
    const allRuleIds = new Set([...tagRuleIds, ...coordRuleIds]);

    // 실제 API에서 확인된 cascade 링크 중 관련 룰만
    const matchedLinks = this._cascadeLinks.filter(l => allRuleIds.has(l.rule_id));

    this._el.innerHTML = this._buildHTML(props, theories, matchedLinks, allRuleIds, lon, lat);
    this._el.classList.add('is-open');

    this._el.querySelector('.theory-panel__close')
      ?.addEventListener('click', () => this._hide());
  }

  _hide() {
    this._el?.classList.remove('is-open');
  }

  _buildHTML(props, theories, matchedLinks, allRuleIds, lon, lat) {
    const date = props.timestamp?.slice(0, 10) ?? '';

    const theoriesHTML = theories.length
      ? theories.map(t => this._buildCard(t, matchedLinks, lon, lat)).join('')
      : `<p class="theory-panel__empty">이 이벤트에 매핑된 이론이 없습니다.<br>theory_tags: ${(props.theory_tags ?? []).join(', ') || '(없음)'}</p>`;

    // 좌표 기반으로 추가된 cascade rule 섹션 (이론 카드에 없는 것)
    const cascadeHTML = this._buildCascadeSection(allRuleIds, matchedLinks);

    return `
      <div class="theory-panel__header">
        <div class="theory-panel__header-meta">
          <span class="theory-panel__label">이론 분석</span>
          <button class="theory-panel__close" title="닫기 (ESC)">✕</button>
        </div>
        <div class="theory-panel__event-title">${props.title ?? '이벤트'}</div>
        <div class="theory-panel__event-meta">
          ${props.country ? `<span>${props.country}</span>` : ''}
          ${date ? `<span>${date}</span>` : ''}
          ${props.severity != null ? `<span class="theory-panel__sev">sev ${props.severity}</span>` : ''}
        </div>
      </div>
      <div class="theory-panel__body">
        ${theoriesHTML}
        ${cascadeHTML}
      </div>
    `;
  }

  _buildCard(theory, matchedLinks, lon, lat) {
    // 이 이론의 cascade_rules 중 이벤트 좌표가 해당 region 안에 있는 것만
    const locationFilteredRules = (theory.cascade_rules ?? []).filter(id =>
      lon == null || isInRegion(lon, lat, id)
    );

    // 그 중 실제 API에서 확인된 링크
    const linkedMatches = matchedLinks.filter(l =>
      locationFilteredRules.includes(l.rule_id)
    );

    const readingHTML = theory.reading
      .filter(r => r.url)
      .map(r => `<a class="theory-card__link" href="${r.url}" target="_blank" rel="noopener">${r.title}</a>`)
      .join('');

    const confirmedHTML = linkedMatches.map(l => {
      const ev    = l.evidence ?? {};
      const pct   = ev.pct_change != null ? `${ev.pct_change > 0 ? '+' : ''}${ev.pct_change.toFixed(2)}%` : '';
      const label = RULE_LABEL[l.rule_id] ?? l.rule_id;
      return `<div class="theory-card__confirmed">⛓ ${label} <span class="theory-card__pct">${pct}</span></div>`;
    }).join('');

    // 잠재 룰: 좌표 필터를 통과했지만 아직 실제 데이터가 없는 룰
    const pendingRuleIds = locationFilteredRules.filter(id =>
      !matchedLinks.some(l => l.rule_id === id)
    );
    const pendingHTML = pendingRuleIds
      .map(id => `<div class="theory-card__pending">◌ ${RULE_LABEL[id] ?? id} <span class="theory-card__pending-note">대기</span></div>`)
      .join('');

    return `
      <div class="theory-card">
        <div class="theory-card__header">
          <span class="theory-card__icon">📚</span>
          <div>
            <div class="theory-card__name">${theory.name}</div>
            <div class="theory-card__scholars">${theory.scholars}</div>
          </div>
        </div>
        <p class="theory-card__summary">${theory.summary}</p>
        <p class="theory-card__detail">${theory.detail}</p>
        ${confirmedHTML || pendingHTML ? `
          <div class="theory-card__cascade">
            <div class="theory-card__cascade-title">관련 Cascade Rule</div>
            ${confirmedHTML}
            ${pendingHTML}
          </div>
        ` : ''}
        ${readingHTML ? `
          <div class="theory-card__reading">
            <div class="theory-card__reading-title">추천 자료</div>
            ${readingHTML}
          </div>
        ` : ''}
      </div>
    `;
  }

  _buildCascadeSection(allRuleIds, matchedLinks) {
    if (allRuleIds.size === 0) return '';

    // 이미 _buildCard에서 각 카드에 표시했으므로
    // 여기선 실제 확인된 링크만 요약 섹션으로 표시
    if (matchedLinks.length === 0) return '';

    const items = matchedLinks.map(l => {
      const ev    = l.evidence ?? {};
      const pct   = ev.pct_change != null ? `${ev.pct_change > 0 ? '+' : ''}${ev.pct_change.toFixed(2)}%` : '';
      const label = RULE_LABEL[l.rule_id] ?? l.rule_id;
      const score = (l.correlation_score * 100).toFixed(0);
      return `
        <div class="cascade-summary__item">
          <span class="cascade-summary__rule">${label}</span>
          <span class="cascade-summary__result ${pct.startsWith('+') ? 'is-up' : 'is-down'}">${pct}</span>
          <span class="cascade-summary__score">상관 ${score}%</span>
        </div>
      `;
    }).join('');

    return `
      <div class="cascade-summary">
        <div class="cascade-summary__title">⛓ 실제 확인된 인과 연쇄</div>
        ${items}
      </div>
    `;
  }
}
