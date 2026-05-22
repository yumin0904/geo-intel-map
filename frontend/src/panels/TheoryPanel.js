/**
 * TheoryPanel.js
 * 마커 클릭 시 우측에서 슬라이드인 — theory_tags를 이론 카드로 변환해 표시.
 * CLAUDE.md 6.1 Theory Panel 명세 구현.
 *
 * EventBus 이벤트:
 *   수신: marker:click { theory_tags, title, timestamp, severity, ... }
 *   수신: marker:close  (지도 클릭, ESC 등)
 *
 * 추천 자료 원칙 (한양대 정치외교학과 학부생 기준):
 *   1. 한국어 자료 우선 — KIMS, EAI, KIEP, KIDA, KINU, KREI 등
 *   2. 무료 접근 가능 우선 — 기관 공개 보고서, Gutenberg, 정부 사이트
 *   3. 학부 수준 — 대학원 전문 논문보다 정책 브리핑·단행본 우선
 */

// ── 이론 데이터베이스 ────────────────────────────────────────────────
// theory_tag → 카드 데이터. 새 이론 추가 시 여기에만 추가하면 됨.
// reading 링크 원칙: RISS/DBpia 검색 결과 URL 우선 (항상 유효), 고전 원문은 Gutenberg/DOI 직링크.
export const THEORY_DB = {

  gray_zone: {
    name: 'Gray Zone Strategy',
    scholars: 'Hoffman (2007), Mazarr (2015)',
    summary: '선전포고 없이 현상변경을 시도하는 모호한 강압 전술의 총칭.',
    detail: '국가·비국가 행위자가 군사적 충돌 임계점 직하에서 심리전·경제압박·해상민병대를 조합해 상대방의 대응을 어렵게 만드는 전략. 후티의 홍해 공격이 전형적 사례.',
    cascade_rules: ['bab_el_mandeb_tension_to_oil'],
    reading: [
      { title: '🔍 RISS에서 "회색지대 전략" 검색', url: 'https://www.riss.kr/search/Search.do?queryText=회색지대+전략&searchGubun=true' },
      { title: '🔍 DBpia에서 "회색지대전략" 검색', url: 'https://www.dbpia.co.kr/search/searchResult?searchStr=회색지대전략' },
      { title: '🔗 Hoffman (2007) — Conflict in the 21st Century (무료 PDF)', url: 'https://www.potomacinstitute.org/images/stories/publications/potomac_hybridwar_0108.pdf' },
    ],
    library_tip: {
      riss:  "'회색지대 전략' 또는 '하이브리드 위협' 검색",
      dbpia: "'비국가행위자 강압전략 SLOC' 검색",
    },
  },

  hybrid_warfare: {
    name: 'Hybrid Warfare',
    scholars: 'Gerasimov (2013), Hoffman (2007)',
    summary: '정규전·비정규전·정보전·사이버전을 동시에 구사하는 복합 전쟁 방식.',
    detail: '러시아의 2014 우크라이나 개입과 2022 전면전이 대표 사례. 군사력·경제·선전을 혼합해 상대방의 대응 수단을 무력화한다. 식량·에너지 무기화와 연결.',
    cascade_rules: ['ukraine_conflict_to_wheat'],
    reading: [
      { title: '🔍 RISS에서 "하이브리드 전쟁 러시아" 검색', url: 'https://www.riss.kr/search/Search.do?queryText=하이브리드+전쟁+러시아&searchGubun=true' },
      { title: '🔍 DBpia에서 "복합전 사이버 정보전" 검색', url: 'https://www.dbpia.co.kr/search/searchResult?searchStr=복합전+사이버+정보전' },
      { title: '🔗 Gerasimov (2013) — The Value of Science (무료 PDF)', url: 'https://www.armyupress.army.mil/Portals/7/military-review/Archives/English/MilitaryReview_20160228_art008.pdf' },
    ],
    library_tip: {
      riss:  "'하이브리드 전쟁 러시아 우크라이나' 검색",
      dbpia: "'복합전 사이버 정보전' 검색",
    },
  },

  A2AD: {
    name: 'A2/AD Strategy (반접근/지역거부)',
    scholars: 'Krepinevich (2010), CSBA',
    summary: '적 전력이 특정 해역·공역에 접근하거나 작전하지 못하도록 막는 군사전략.',
    detail: '중국의 DF-21D 대함탄도미사일·잠수함·해상민병대가 미군의 제1열도선 내 자유항행을 차단하는 것이 전형적 사례. 대만해협·남중국해가 핵심 마찰 공간.',
    geo_filter: ['taiwan_strait', 'south_china_sea', 'east_china_sea'],
    cascade_rules: ['taiwan_strait_to_tsm', 'taiwan_strait_to_soxx', 'south_china_sea_to_defense'],
    reading: [
      { title: '🔍 RISS에서 "A2AD 중국" 검색', url: 'https://www.riss.kr/search/Search.do?queryText=A2AD+중국&searchGubun=true' },
      { title: '🔍 DBpia에서 "반접근 지역거부" 검색', url: 'https://www.dbpia.co.kr/search/searchResult?searchStr=반접근+지역거부' },
      { title: '🔗 CSBA — AirSea Battle (2010, 무료)', url: 'https://csbaonline.org/research/publications/airsea-battle-a-point-of-departure-operational-concept' },
    ],
    library_tip: {
      riss:  "'A2AD 중국 군사전략 제1열도선' 검색",
      dbpia: "'반접근 지역거부 대만해협' 검색",
    },
  },

  conventional_warfare: {
    name: 'Conventional Warfare',
    scholars: 'Clausewitz (1832)',
    summary: '국가 간 선포된 정규 군사력 충돌.',
    detail: '규칙과 국제법 틀 안에서 군대 간 직접 교전. 현대에는 순수 재래전은 드물며, 회색지대·하이브리드전과 혼합되는 경우가 많다.',
    cascade_rules: [],
    reading: [
      { title: '🔍 RISS에서 "재래전 국제인도법" 검색', url: 'https://www.riss.kr/search/Search.do?queryText=재래전+국제인도법&searchGubun=true' },
      { title: '🔍 DBpia에서 "클라우제비츠 정규전" 검색', url: 'https://www.dbpia.co.kr/search/searchResult?searchStr=클라우제비츠+정규전' },
      { title: '🔗 Clausewitz — On War (1832, Project Gutenberg 무료)', url: 'https://www.gutenberg.org/ebooks/1946' },
    ],
    library_tip: {
      riss:  "'재래전 국제인도법 전쟁론' 검색",
      dbpia: "'클라우제비츠 정규전 현대전쟁' 검색",
    },
  },

  irregular_warfare: {
    name: 'Irregular Warfare',
    scholars: 'Galula (1964), Kilcullen (2009)',
    summary: '비정규 전투원이 참여하는 비전통적 무력분쟁.',
    detail: '게릴라전·반란진압·테러 등이 포함. ACLED 데이터의 상당 부분이 이 유형. 약소 행위자가 강대국에 비대칭적으로 대응하는 방식이다.',
    cascade_rules: [],
    reading: [
      { title: '🔍 RISS에서 "비정규전 반란진압" 검색', url: 'https://www.riss.kr/search/Search.do?queryText=비정규전+반란진압&searchGubun=true' },
      { title: '🔍 DBpia에서 "게릴라 테러리즘 비국가행위자" 검색', url: 'https://www.dbpia.co.kr/search/searchResult?searchStr=게릴라+테러리즘+비국가행위자' },
    ],
    library_tip: {
      riss:  "'비정규전 반란진압 COIN' 검색",
      dbpia: "'게릴라 테러리즘 비국가행위자' 검색",
    },
  },

  political_instability: {
    name: 'Political Instability / 국가 취약성',
    scholars: 'Rotberg (2004), Fund for Peace (FSI)',
    summary: '정권 정당성 약화·경제 위기·사회 분열로 국가 기능이 붕괴하는 과정.',
    detail: 'ACLED 분쟁 데이터와 높은 상관관계. 취약국은 강대국의 대리전 무대가 되기 쉽고, 지역 패권 경쟁의 진공 지대를 형성한다.',
    cascade_rules: [],
    reading: [
      { title: '🔍 RISS에서 "국가취약성 실패국가" 검색', url: 'https://www.riss.kr/search/Search.do?queryText=국가취약성+실패국가&searchGubun=true' },
      { title: '🔍 DBpia에서 "정치불안정 분쟁 대리전" 검색', url: 'https://www.dbpia.co.kr/search/searchResult?searchStr=정치불안정+분쟁+대리전' },
      { title: '🔗 Fund for Peace — Fragile States Index (무료)', url: 'https://fragilestatesindex.org/' },
    ],
    library_tip: {
      riss:  "'국가취약성 실패국가 FSI' 검색",
      dbpia: "'정치불안정 분쟁 대리전' 검색",
    },
  },

  // ── 미래 확장 태그 (현재 ACLED 이벤트엔 없지만 룰북과 연결됨) ───

  sloc: {
    name: 'SLOC Interdiction (Mahan 해양력)',
    scholars: 'Mahan (1890), Till (2004)',
    summary: '해상교통로(SLOC) 통제권이 국가 패권의 핵심 조건.',
    detail: '호르무즈·바브엘만데브·말라카·수에즈 등 초크포인트가 전략적 가치를 갖는 이유. 통제하거나 차단하면 세계 무역·에너지 흐름을 좌우할 수 있다.',
    geo_filter: ['taiwan_strait', 'south_china_sea', 'east_china_sea', 'hormuz', 'bab_el_mandeb', 'suez', 'malacca'],
    cascade_rules: ['bab_el_mandeb_tension_to_oil', 'hormuz_tension_to_oil', 'suez_tension_to_shipping'],
    reading: [
      { title: '🔍 RISS에서 "해상교통로 안보" 검색', url: 'https://www.riss.kr/search/Search.do?queryText=해상교통로+안보&searchGubun=true' },
      { title: '🔍 KIMS에서 "해상교통로" 검색', url: 'https://kims.or.kr/?s=해상교통로' },
      { title: '🔗 Mahan — The Influence of Sea Power (1890, Gutenberg 무료)', url: 'https://www.gutenberg.org/ebooks/13529' },
    ],
    library_tip: {
      riss:  "'해상교통로 SLOC 초크포인트' 검색",
      dbpia: "'말라카 딜레마 해양력 마한' 검색",
    },
  },

  resource_weaponization: {
    name: 'Resource Weaponization',
    scholars: 'Hirschman (1945), Drezner (2015)',
    summary: '에너지·식량·금융 등 경제적 상호의존을 강압 수단으로 전환하는 전략.',
    detail: '러시아의 가스 외교, 중국의 희토류 수출 제한이 대표 사례. 수입국의 취약성이 높을수록 무기화 효과가 크다.',
    cascade_rules: ['hormuz_tension_to_oil', 'ukraine_conflict_to_wheat', 'south_china_sea_to_lng'],
    reading: [
      { title: '🔍 RISS에서 "에너지 무기화" 검색', url: 'https://www.riss.kr/search/Search.do?queryText=에너지+무기화&searchGubun=true' },
      { title: '🔍 KIEP에서 "에너지안보" 검색', url: 'https://www.kiep.go.kr/search/total.es?mid=a30000000000&query=에너지안보' },
      { title: '🔍 DBpia에서 "상호의존 경제강압 희토류" 검색', url: 'https://www.dbpia.co.kr/search/searchResult?searchStr=상호의존+경제강압+희토류' },
    ],
    library_tip: {
      riss:  "'자원무기화 에너지안보 경제제재' 검색",
      dbpia: "'상호의존 경제강압 희토류' 검색",
    },
  },

  weaponized_interdependence: {
    name: 'Weaponized Interdependence',
    scholars: 'Farrell & Newman (2019)',
    summary: '글로벌 네트워크 허브 지위를 전략적 강압 수단으로 전환하는 메커니즘.',
    detail: '달러 결제망(SWIFT), 반도체 공급망, 클라우드 인프라 등이 특정 국가에 집중될 때 그 국가가 갖는 비대칭적 권력.',
    cascade_rules: ['taiwan_strait_to_tsm', 'taiwan_strait_to_soxx'],
    reading: [
      { title: '🔍 RISS에서 "무기화된 상호의존" 검색', url: 'https://www.riss.kr/search/Search.do?queryText=무기화된+상호의존&searchGubun=true' },
      { title: '🔍 EAI에서 "상호의존" 검색', url: 'https://www.eai.or.kr/new/ko/search/index.asp?q=상호의존' },
      { title: '🔗 Farrell & Newman (2019) — Weaponized Interdependence (DOI)', url: 'https://doi.org/10.1162/isec_a_00351' },
    ],
    library_tip: {
      riss:  "'무기화된 상호의존 반도체 공급망' 검색",
      dbpia: "'기술패권 SWIFT 디지털경제안보' 검색",
    },
  },

  safe_haven: {
    name: 'Safe Haven Theory',
    scholars: 'Baur & Lucey (2010), Erb & Harvey (2013)',
    summary: '지정학 위기 시 투자자가 국가 신용리스크 없는 자산으로 이동.',
    detail: '금·미국채·스위스프랑이 대표적 안전자산. "Risk-off" 심리가 강해지면 주식·이머징 자산에서 자금이 이탈한다.',
    cascade_rules: ['middle_east_conflict_to_gold'],
    reading: [
      { title: '🔍 RISS에서 "안전자산 지정학" 검색', url: 'https://www.riss.kr/search/Search.do?queryText=안전자산+지정학&searchGubun=true' },
      { title: '🔍 DBpia에서 "리스크오프 투자 지정학" 검색', url: 'https://www.dbpia.co.kr/search/searchResult?searchStr=리스크오프+투자+지정학' },
    ],
    library_tip: {
      riss:  "'안전자산 금 지정학 리스크' 검색",
      dbpia: "'리스크오프 투자 지정학 프리미엄' 검색",
    },
  },

  korea_discount: {
    name: 'Korea Discount / Extended Deterrence',
    scholars: 'Cha (2002), 국제금융센터',
    summary: '한반도 지정학 리스크가 한국 자산 밸류에이션을 구조적으로 낮추는 현상.',
    detail: '미국 핵우산(확장억제) 신뢰성이 흔들릴 때마다 원화 약세·KOSPI 하락이 동반된다.',
    cascade_rules: ['north_korea_missile_to_krw', 'korean_tension_to_kospi'],
    reading: [
      { title: '🔍 통일연구원(KINU)에서 "한반도 안보" 검색', url: 'https://www.kinu.or.kr/search?query=한반도+안보' },
      { title: '🔍 RISS에서 "코리아 디스카운트" 검색', url: 'https://www.riss.kr/search/Search.do?queryText=코리아+디스카운트&searchGubun=true' },
      { title: '🔍 DBpia에서 "코리아디스카운트" 검색', url: 'https://www.dbpia.co.kr/search/searchResult?searchStr=코리아디스카운트' },
    ],
    library_tip: {
      riss:  "'코리아 디스카운트 지정학 리스크' 검색",
      dbpia: "'한국증시 북한리스크 확장억제' 검색",
    },
  },

  food_security: {
    name: 'Food Security as Geopolitical Weapon',
    scholars: 'Patel & Moore (2009), FAO',
    summary: '식량 공급망 집중이 정치적 강압 수단이 되는 구조.',
    detail: '우크라이나·러시아가 세계 밀 28% 담당. 봉쇄 시 식량 수입 의존국에서 정치 불안 발생 (아랍의 봄 패턴).',
    cascade_rules: ['ukraine_conflict_to_wheat'],
    reading: [
      { title: '🔍 RISS에서 "식량안보 지정학" 검색', url: 'https://www.riss.kr/search/Search.do?queryText=식량안보+지정학&searchGubun=true' },
      { title: '🔍 KREI에서 "식량안보" 검색', url: 'https://www.krei.re.kr/krei/searchList.do?query=식량안보' },
      { title: '🔍 DBpia에서 "식량위기 지정학" 검색', url: 'https://www.dbpia.co.kr/search/searchResult?searchStr=식량위기+지정학' },
    ],
    library_tip: {
      riss:  "'식량안보 우크라이나 밀 수출' 검색",
      dbpia: "'식량위기 지정학 아랍의봄' 검색",
    },
  },

  forward_deployment: {
    name: 'Forward Deployment (전진배치)',
    scholars: 'Posen (2003), Brose (2020)',
    summary: '본토에서 멀리 떨어진 거점에 군사력을 미리 배치해 억제력을 투사하는 전략.',
    detail: '미국의 괌·오키나와·한국 주둔이 대표 사례. 신속 대응 능력을 높이지만 현지 사회·정치적 마찰을 유발한다.',
    cascade_rules: ['south_china_sea_to_defense', 'taiwan_strait_to_tsm'],
    reading: [
      { title: '🔍 RISS에서 "전진배치 주한미군" 검색', url: 'https://www.riss.kr/search/Search.do?queryText=전진배치+주한미군&searchGubun=true' },
      { title: '🔍 DBpia에서 "해외군사기지 전력투사" 검색', url: 'https://www.dbpia.co.kr/search/searchResult?searchStr=해외군사기지+전력투사' },
    ],
    library_tip: {
      riss:  "'전진배치 주한미군 억제전략' 검색",
      dbpia: "'해외군사기지 전력투사 인도태평양' 검색",
    },
  },

  alliance_theory: {
    name: 'Alliance Theory',
    scholars: 'Waltz (1979), Walt (1987)',
    summary: '국가들이 위협에 대응해 동맹을 형성하고 유지하는 방식에 관한 이론.',
    detail: '세력균형(Waltz): 강대국 부상에 대항해 연합. 위협균형(Walt): 능력뿐 아니라 의도·인접성도 고려. 비대칭 동맹에서 안보-자율성 교환 딜레마가 핵심.',
    cascade_rules: ['south_china_sea_to_defense', 'korean_tension_to_kospi'],
    reading: [
      { title: '🔍 RISS에서 "동맹이론 한미동맹" 검색', url: 'https://www.riss.kr/search/Search.do?queryText=동맹이론+한미동맹&searchGubun=true' },
      { title: '🔍 EAI에서 "동맹이론" 검색', url: 'https://www.eai.or.kr/new/ko/search/index.asp?q=동맹이론' },
      { title: '🔍 통일연구원(KINU)에서 "한미동맹" 검색', url: 'https://www.kinu.or.kr/search?query=한미동맹+동맹이론' },
    ],
    library_tip: {
      riss:  "'동맹이론 한미동맹 세력균형' 검색",
      dbpia: "'위협균형 안보자율성 비대칭동맹' 검색",
    },
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
export const RULE_LABEL = {
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

// ── 한국 관련도 (지역별) ─────────────────────────────────────────────
// 이벤트 좌표 기반으로 자동 판별. stars: 1-5, bbox: [minLon, minLat, maxLon, maxLat].
// 한국이 각 지역 분쟁에 얼마나 직접·간접 영향을 받는지를 나타냄.
const KOREA_RELEVANCE = {
  korean_peninsula: {
    stars: 5,
    reason: '직접 안보 위협, KOSPI·원화 직결, 주한미군',
    bbox: [124.0, 33.5, 130.5, 43.0],
  },
  taiwan_strait: {
    stars: 5,
    reason: 'TSMC→삼성 반도체 공급망, 주한미군 연동, 한국 수출 1위국(중국) 직결',
    bbox: [118.0, 22.0, 122.0, 26.0],
  },
  hormuz: {
    stars: 5,
    reason: '한국 원유 수입 70%+ 통과, 중동 의존도 세계 최고 수준',
    bbox: [53.0, 23.0, 60.0, 30.0],
  },
  south_china_sea: {
    stars: 5,
    reason: '한국 수출입 물동량 30% 통과, 말라카 해협 경유 원유 수입',
    bbox: [105.0, 3.0, 122.0, 22.0],
  },
  malacca: {
    stars: 5,
    reason: '동아시아 에너지·물류 핵심 길목, 한국 원유·LNG 수입 주요 경유',
    bbox: [98.0, 1.0, 104.0, 6.5],
  },
  bab_el_mandeb: {
    stars: 4,
    reason: '한국 원유 수입 경로, 현대·삼성 선박 통과, 해운비 직결',
    bbox: [42.0, 11.0, 45.5, 14.5],
  },
  suez: {
    stars: 4,
    reason: '유럽향 수출 경로, 우회 시 해운비 급등',
    bbox: [31.5, 28.0, 34.5, 32.5],
  },
  east_china_sea: {
    stars: 4,
    reason: '제1열도선·센카쿠 긴장이 한미일 협력 직결, 한국 해운 항로 인접',
    bbox: [118.0, 24.0, 132.0, 40.0],
  },
  middle_east: {
    stars: 4,
    reason: '원유 의존도, 건설·플랜트 수주 시장',
    bbox: [35.0, 15.0, 65.0, 37.0],
  },
  ukraine: {
    stars: 3,
    reason: '에너지 가격 간접 영향, 방산 수출 기회',
    bbox: [22.0, 44.0, 40.5, 52.5],
  },
  myanmar: {
    stars: 2,
    reason: '간접적 지역 불안정',
    bbox: [92.0, 9.5, 101.5, 28.5],
  },
};

// 좁은 bbox를 먼저 검사해야 정확도가 높음 (middle_east는 겹치므로 마지막에)
const KOREA_RELEVANCE_ORDER = [
  'korean_peninsula', 'taiwan_strait', 'bab_el_mandeb', 'hormuz',
  'suez', 'malacca', 'east_china_sea', 'south_china_sea',
  'ukraine', 'myanmar', 'middle_east',
];

/** 별점 색상 — 5·4 고위험은 warm color, 3 보통, 2 이하 흐림 */
const STAR_COLOR = { 5: '#f85149', 4: '#e07b33', 3: '#d29922', 2: '#8b949e', 1: '#8b949e' };

/** n개 채운별 + (5-n)개 빈별 */
function starsLabel(n) { return '★'.repeat(n) + '☆'.repeat(5 - n); }

/** 이벤트 좌표에서 한국 관련도 객체를 반환. 매칭 없으면 null. */
function getKoreaRelevance(lon, lat) {
  if (lon == null || lat == null) return null;
  for (const key of KOREA_RELEVANCE_ORDER) {
    const entry = KOREA_RELEVANCE[key];
    const [minLon, minLat, maxLon, maxLat] = entry.bbox;
    if (lon >= minLon && lon <= maxLon && lat >= minLat && lat <= maxLat) {
      return { key, ...entry };
    }
  }
  return null;
}

// ── 패널 컴포넌트 ────────────────────────────────────────────────────
export class TheoryPanel {
  /** @param {import('../core/EventBus.js').EventBus} eventBus */
  constructor(eventBus) {
    this._eventBus    = eventBus;
    this._el          = null;
    this._cascadeLinks = [];  // /api/cascade/links 캐시
    this._notebook    = null; // NotebookPanel (선택적) — setNotebook()으로 주입
  }

  /**
   * Study Mode 노트 패널 주입.
   * @param {import('./NotebookPanel.js').NotebookPanel} nb
   */
  setNotebook(nb) { this._notebook = nb; }

  mount(containerId) {
    this._el = document.getElementById(containerId);
    if (!this._el) return;

    this._eventBus.on('marker:click', (props) => this._show(props));
    this._eventBus.on('marker:close', ()       => this._hide());

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
      this._cascadeLinks = [];
    }
  }

  _show(props) {
    const tags = props.theory_tags ?? [];
    const lon  = props._lon ?? null;
    const lat  = props._lat ?? null;

    const theories = tags
      .map(t => THEORY_DB[t])
      .filter(Boolean)
      .filter(t => {
        if (!t.geo_filter) return true;
        if (lon == null || lat == null) return true;
        return isInAnyTheoryRegion(lon, lat, t.geo_filter);
      });

    const tagRuleIds   = new Set(theories.flatMap(t => t.cascade_rules ?? []));
    const coordRuleIds = (lon != null && lat != null)
      ? new Set(Object.keys(RULE_REGIONS).filter(id => isInRegion(lon, lat, id)))
      : new Set();
    const allRuleIds   = new Set([...tagRuleIds, ...coordRuleIds]);
    const matchedLinks = this._cascadeLinks.filter(l => allRuleIds.has(l.rule_id));

    this._el.innerHTML = this._buildHTML(props, theories, matchedLinks, allRuleIds, lon, lat);
    this._el.classList.add('is-open');
    this._el.querySelector('.theory-panel__close')
      ?.addEventListener('click', () => this._hide());

    // Study Mode: 노트 패널 초기화 (Study Mode CSS로 show/hide)
    // props.id(UUID) 우선, 없으면 source_id, 둘 다 없으면 좌표 key로 fallback
    const noteKey = props.id ?? props.source_id ?? (lon != null ? `${lon},${lat}` : null);
    const slotEl  = this._el.querySelector('.notebook-slot');
    if (noteKey) this._notebook?.show(noteKey, slotEl);
  }

  _hide() {
    this._el?.classList.remove('is-open');
    this._notebook?.hide();
  }

  _buildHTML(props, theories, matchedLinks, allRuleIds, lon, lat) {
    const date = props.timestamp?.slice(0, 10) ?? '';

    const theoriesHTML = theories.length
      ? theories.map(t => this._buildCard(t, matchedLinks, lon, lat)).join('')
      : `<p class="theory-panel__empty">이 이벤트에 매핑된 이론이 없습니다.<br>theory_tags: ${(props.theory_tags ?? []).join(', ') || '(없음)'}</p>`;

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
          ${date         ? `<span>${date}</span>`           : ''}
          ${props.severity != null ? `<span class="theory-panel__sev">sev ${props.severity}</span>` : ''}
        </div>
      </div>
      <div class="theory-panel__body">
        ${theoriesHTML}
        ${cascadeHTML}
        <div class="notebook-slot"></div>
      </div>
    `;
  }

  _buildCard(theory, matchedLinks, lon, lat) {
    const locationFilteredRules = (theory.cascade_rules ?? []).filter(id =>
      lon == null || isInRegion(lon, lat, id)
    );
    const linkedMatches = matchedLinks.filter(l =>
      locationFilteredRules.includes(l.rule_id)
    );
    const pendingRuleIds = locationFilteredRules.filter(id =>
      !matchedLinks.some(l => l.rule_id === id)
    );

    const confirmedHTML = linkedMatches.map(l => {
      const ev    = l.evidence ?? {};
      const pct   = ev.pct_change != null ? `${ev.pct_change > 0 ? '+' : ''}${ev.pct_change.toFixed(2)}%` : '';
      const label = RULE_LABEL[l.rule_id] ?? l.rule_id;
      return `<div class="theory-card__confirmed">⛓ ${label} <span class="theory-card__pct">${pct}</span></div>`;
    }).join('');

    const pendingHTML = pendingRuleIds
      .map(id => `<div class="theory-card__pending">◌ ${RULE_LABEL[id] ?? id} <span class="theory-card__pending-note">대기</span></div>`)
      .join('');

    const readingHTML = theory.reading
      .map(r => r.url
        ? `<a class="theory-card__link" href="${r.url}" target="_blank" rel="noopener">${r.title}</a>`
        : `<span class="theory-card__link-text">${r.title}</span>`
      )
      .join('');

    const koreaHTML = this._buildKoreaRelevanceHTML(lon, lat);

    // 도서관 검색 팁 — <details>로 접어두어 패널 공간 절약
    const tipHTML = theory.library_tip ? `
      <details class="theory-card__tip">
        <summary class="theory-card__tip-summary">💡 도서관 검색 팁</summary>
        <div class="theory-card__tip-body">
          ${theory.library_tip.riss  ? `<div><span class="theory-card__tip-db">RISS</span>${theory.library_tip.riss}</div>`  : ''}
          ${theory.library_tip.dbpia ? `<div><span class="theory-card__tip-db">DBpia</span>${theory.library_tip.dbpia}</div>` : ''}
        </div>
      </details>
    ` : '';

    return `
      <div class="theory-card">
        <div class="theory-card__header">
          <span class="theory-card__icon">📚</span>
          <div>
            <div class="theory-card__name">${theory.name}</div>
            <div class="theory-card__scholars">${theory.scholars}</div>
          </div>
        </div>
        ${koreaHTML}
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
        ${tipHTML}
      </div>
    `;
  }

  /** 이벤트 좌표 기반 한국 관련도 배지 HTML */
  _buildKoreaRelevanceHTML(lon, lat) {
    const r = getKoreaRelevance(lon, lat);
    if (!r) return '';
    const color = STAR_COLOR[r.stars] ?? '#8b949e';
    return `
      <div class="theory-card__korea">
        <div class="theory-card__korea-row">
          <span class="theory-card__korea-flag">🇰🇷</span>
          <span class="theory-card__korea-label">한국 관련도</span>
          <span class="theory-card__korea-stars" style="color:${color}">${starsLabel(r.stars)}</span>
        </div>
        <div class="theory-card__korea-reason">${r.reason}</div>
      </div>
    `;
  }

  _buildCascadeSection(allRuleIds, matchedLinks) {
    if (allRuleIds.size === 0 || matchedLinks.length === 0) return '';

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
