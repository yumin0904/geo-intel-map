# Theory Tag Validation Checklist

새 region·country·cascade 룰을 추가할 때 이 체크리스트를 순서대로 검토한다.  
구현 파일: `backend/connectors/acled.py` → `_build_theory_tags()`

---

## 1. region 추가 시

### 1-A. regions.yaml 등록
- [ ] `bbox: [min_lon, min_lat, max_lon, max_lat]` 정확한가?
- [ ] `center` 좌표가 대표점으로 적절한가?
- [ ] 기존 region bbox와 겹치지 않는가? (`region_for_point`는 첫 매칭만 반환)

### 1-B. 고정 태그 세트 결정 (`acled.py` 상수 4개 중 해당 항목에 추가)

| 상수 | 조건 | 태그 효과 |
|------|------|---------|
| `_A2AD_REGIONS` | 해양 접근거부 전략이 핵심인 해역 | `A2AD` 추가 |
| `_SLOC_DISRUPTION_REGIONS` | 주요 해상교통로(SLOC) 인근 | `SLOC_disruption` 추가 |
| `_RESOURCE_WEAPONIZATION_REGIONS` | 에너지 공급 통제 무기화 | `resource_weaponization`, `gray_zone` 추가 |
| `_FORCE_CONVENTIONAL_REGIONS` | 국가 간 정규전이 명백한 분쟁 | `conventional_warfare` 강제 / `irregular_warfare` 제거 |

- [ ] 위 4개 중 해당 region을 추가해야 하는 상수가 있는가?
- [ ] `_FORCE_CONVENTIONAL_REGIONS`에 추가하면 civil_war/insurgency 태그가 의도치 않게 제거되는 사례가 없는가?

### 1-C. Sanitization 예외 필요 여부 검토

- [ ] 해당 region에서 `conventional_warfare + insurgency` 공존 시 어느 쪽을 우선해야 하는가?  
  (기본: inter1=1이면 conventional 우선, inter1≠1이면 insurgency 우선)
- [ ] `south_china_sea`처럼 conventional_warfare를 강제 제거해야 하는 region인가?  
  (회색지대 전략이 본질인 해역 → `gray_zone` 강제)
- [ ] `suez`처럼 Explosions/Shelling 시 비대칭 태그를 제거해야 하는 region인가?  
  (SLOC 차단 학습 집중 목적)

### 1-D. cascade_rules.yaml 연동 확인

- [ ] 신규 region에 대응하는 cascade 룰이 있는가?
- [ ] `_TRIGGER_COUNTRIES`에 해당 region → ACLED 국가 매핑이 추가됐는가? (`engine.py`)
- [ ] 룰의 `theory.framework`가 배정되는 theory_tags와 일관성이 있는가?

### 1-E. 검증 명령

```bash
cd backend && .venv/bin/python -c "
import sys; sys.path.insert(0, '.')
from connectors.acled import _build_theory_tags

# 신규 region의 대표 시나리오 4개 이상 테스트
region = 'NEW_REGION'
for et, sub, i1, i2, country in [
    ('Battles', 'Armed clash', 1, 1, 'CountryA'),
    ('Battles', 'Armed clash', 2, 1, 'CountryA'),
    ('Explosions/Remote violence', 'Air/drone strike', 2, 1, 'CountryA'),
    ('Explosions/Remote violence', 'Shelling/artillery/missile attack', 1, 2, 'CountryA'),
]:
    tags = _build_theory_tags(et, sub, i1, i2, region, country)
    print(f'{et}/{sub} ({i1}vs{i2}): {tags}')
"
```

---

## 2. country 추가 시 (`_CIVIL_WAR_COUNTRIES`)

내전 국가 리스트에 국가를 추가하면 **해당 국가의 모든 Battles/Explosions 1vs1 이벤트**가  
`conventional_warfare` → `civil_war + asymmetric_warfare`로 변경된다.

추가 조건:
- [ ] ACLED `country` 필드값이 정확히 일치하는가? (대소문자 구분, 예: "Palestine" not "palestinian")
- [ ] 1vs1이어도 실질이 내전(파벌전)인가? 외부 침략국이 포함된 전쟁은 해당 안 됨
- [ ] 추가 후 기존 cascade 룰의 trigger에서 의도치 않은 태그 변경이 없는가?

현재 목록:
```python
_CIVIL_WAR_COUNTRIES = {
    "Yemen", "Myanmar", "Sudan", "Libya", "Syria",
    "Lebanon", "Palestine", "Gaza",
}
```

---

## 3. cascade 룰 추가 시

### 3-A. YAML 필드 체크
- [ ] `trigger.region`이 `regions.yaml`에 정의된 region_code인가?
- [ ] `trigger.severity_min`이 해당 지역 ACLED 데이터 분포와 맞는가?
  - 상시 교전: 40~50 / 주요 사건: 60~70 / 고강도만: 70~80
- [ ] `expected_response.window_hours`가 시장 반응 속도와 맞는가?
  - FX: 12h / 주식·에너지: 24~48h / 해운·곡물: 48~72h
- [ ] `theory.framework`에 명기된 이론이 theory_tags와 연결되는가?

### 3-B. 엔진 연동 확인
- [ ] `_TRIGGER_COUNTRIES`에 `trigger.region` → ACLED 국가 매핑 추가됐는가?
- [ ] 신규 region이라면 1-A~1-E를 먼저 완료했는가?

### 3-C. 활성화 검증 명령

```bash
cd backend && .venv/bin/python -c "
import asyncio, sys, os
sys.path.insert(0, '.'); os.chdir('.')
from dotenv import load_dotenv; load_dotenv()
from services.cascade.engine import _fetch_region_events, _sample_triggers
from services.cascade.rule_loader import load_rules

async def main():
    rules = {r.id: r for r in load_rules()}
    r = rules['NEW_RULE_ID']
    events = await _fetch_region_events(r.trigger.region)
    triggers = _sample_triggers(events, r.trigger.severity_min)
    print(f'region={r.trigger.region}: {len(events)}개 → sev>={r.trigger.severity_min}: {len(triggers)}개')
    for t in triggers[:3]:
        print(f'  {t.timestamp.date()} sev={t.severity} tags={t.theory_tags}')

asyncio.run(main())
"
```

---

## 4. 전체 태그 현황 빠른 확인 명령

```bash
cd backend && .venv/bin/python -c "
import sys; sys.path.insert(0, '.')
from connectors.acled import _build_theory_tags

# 6개 활성 region × 대표 시나리오
rows = [
    ('bab_el_mandeb', 'Battles', 'Armed clash', 1, 1, 'Yemen'),
    ('bab_el_mandeb', 'Explosions/Remote violence', 'Shelling/artillery/missile attack', 2, 1, 'Yemen'),
    ('suez',          'Explosions/Remote violence', 'Shelling/artillery/missile attack', 1, 2, 'Israel'),
    ('hormuz',        'Explosions/Remote violence', 'Shelling/artillery/missile attack', 2, 1, 'Iran'),
    ('ukraine',       'Battles', 'Armed clash', 1, 8, 'Ukraine'),
    ('middle_east',   'Battles', 'Armed clash', 1, 1, 'Lebanon'),
    ('south_china_sea','Battles', 'Armed clash', 0, 0, 'Philippines'),
    ('south_china_sea','Battles', 'Armed clash', 1, 1, 'Philippines'),
    ('taiwan_strait', 'Battles', 'Armed clash', 1, 1, 'Taiwan'),
    (None,            'Battles', 'Ambush',       2, 1, 'Myanmar'),
]
for (r, et, sub, i1, i2, c) in rows:
    tags = _build_theory_tags(et, sub, i1, i2, r, c)
    print(f'[{r or \"None\":<16}] {c:<12} → {tags}')
"
```

---

## 5. 알려진 한계 및 미해결 사항

| 이슈 | 원인 | 우회 방법 |
|------|------|---------|
| Philippines inter1=0 | ACLED이 필리핀 해안경비대를 비표준 분류로 반환 | south_china_sea `_변경4_`로 `gray_zone` fallback 처리 |
| 우크라이나 러시아군 inter2=8 | ACLED "External/Other Forces" 분류 | `_FORCE_CONVENTIONAL_REGIONS`으로 강제 보정 |
| Gaza vs Palestine country명 혼용 | ACLED 이벤트에 따라 다름 | 둘 다 `_CIVIL_WAR_COUNTRIES`에 등록 |
| 호르무즈 inter 과부하 (6~7개 태그) | 지역+비국가+미사일 조합 시 누적 | 향후 hormuz에도 suez 식 sanitization 검토 |
