---
theory_id: techno_techno_nationalism
title: "기술 민족주의 (Techno-Nationalism)"
sector_tag: techno
theorists:
  - Koji Watanabe
  - Sylvia Ostry
  - Richard Nelson
year: 1995
summary: "기술 혁신 역량을 국가 경쟁력·안보의 핵심으로 보고, 핵심 기술의 자국 내 통제를 추구하는 전략적 기술 국유화 경향."
regions:
  - taiwan_strait
  - south_china_sea
  - east_china_sea
---

## 핵심 주장

기술 민족주의는 반도체·AI·양자컴퓨팅·우주 등 첨단 기술을
단순한 상업 자산이 아닌 **국가 안보 자산**으로 간주하는 전략 패러다임이다.

세 가지 정책 표현:
1. **수출 통제** — 적대국에 핵심 기술·부품 이전 금지
2. **국내 육성** — 보조금·R&D 투자로 자국 기술 생태계 구축
3. **외국인 투자 심사** — 첨단 기업 인수합병(M&A) 차단

## 현대 지정학과의 연결

### 미·중 반도체 전쟁
미국의 CHIPS Act(2022)와 대중 반도체 수출규제(EAR)는
기술 민족주의의 집약적 표현이다.
TSMC를 애리조나에 유치하고 SMIC의 최첨단 공정 접근을 차단하는 것은
반도체 공급망을 전략 자산으로 취급하겠다는 선언이다.

### 중국의 반격: 토종화(国产化)
화웨이의 Kirin 칩 자체 개발, SMIC의 7nm 공정 도전,
CIPS(위안화 결제망) 구축은 모두 외부 기술 의존도를 줄이려는
기술 민족주의적 응전이다.

### 일본·한국의 포지셔닝
삼성·SK하이닉스의 對中 HBM 수출 제한 압력,
일본 ASML 장비 수출 통제 참여는
동맹 기반 기술 민족주의 블록화의 증거다.

## Cascade 연결 포인트

| 트리거 이벤트 | 연쇄 반응 | 관련 룰 ID |
|---|---|---|
| 대만해협 군사 긴장 | TSMC 주가 하락 | `taiwan_strait_to_tsm` |
| 남중국해 분쟁 격화 | 반도체 ETF(SOXX) 하락 | `taiwan_strait_to_soxx` |
| 남중국해 군사훈련 | 방위산업 지수(ITA) 상승 | `south_china_sea_to_defense` |

## 학습 노트

> "기술은 더 이상 중립적 상품이 아니다. 기술이 곧 권력이다."
> — 현대 기술지정학의 핵심 명제

지도에서 ADS-B 레이어를 켜고 대만해협·남중국해의 군용기 활동을 보라.
그 비행 경로들은 기술 민족주의의 군사적 표현 — 첨단 무기체계의 실전 전개다.
Cascade 그래프에서 군용기 이벤트 → TSMC 주가 연결을 확인해보자.

## 참고 자료

- Ostry, S. & Nelson, R. (1995). *Techno-Nationalism and Techno-Globalism*. Brookings.
- Segal, A. (2011). *Advantage: How American Innovation Can Win the Future*. Norton.
- 김양규 (2023). "반도체 기술패권 경쟁과 한국의 전략." KIDA 연구보고서.
