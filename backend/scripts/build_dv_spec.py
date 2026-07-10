"""dv_spec.yaml 생성기 — 이론 프로파일 DV 스펙 (개선위 P4, 판례 20260710-engine-improvement-committee).

원천: db/library.db theories.dependent_var (이론 프로파일이 스스로 선언한 종속변수).
이 스크립트는 dependent_var 텍스트를 DV 클래스 별칭표와 기계 대조해 클래스를 배정한다
— 사람이 이론별로 클래스를 창작하지 않는다(선언문 기계 매핑, 재현 가능).

재생성: python3 scripts/build_dv_spec.py  → config/dv_spec.yaml 덮어쓰기.
클래스 별칭표를 고치면 여기서 고치고 재생성한다 (YAML 직접 편집 금지 — 생성물).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DB = BASE / "db" / "library.db"
OUT = BASE / "config" / "dv_spec.yaml"

# DV 클래스 별칭표 — 판정 라인의 예측/실측 구간을 분류하는 어휘.
# 넉넉하게(관대) 잡는다: 게이트는 클래스가 '서로소'일 때만 강등하므로
# 별칭 누락은 오탐(부당 강등)으로, 과잉은 미탐으로 기운다 — 오탐이 더 나쁘다.
CLASSES: dict[str, list[str]] = {
    "market_econ": [
        "유가", "가격", "운임", "보험료", "환율", "주가", "kospi", "pbr",
        "밸류에이션", "프리미엄", "gdp", "성장률", "금리", "인플레", "무역량",
        "시장", "해고",
    ],
    "trade_flow": [
        "무역", "수출", "수입", "교역", "물동량", "통과량", "공급량",
        "공급 차단", "데이터 흐름", "흐름 교란", "점유율", "hhi", "공급망",
        "의존도", "집중도",
    ],
    "conflict_event": [
        "분쟁", "무력", "충돌", "교전", "도발", "침략", "공격", "위기",
        "개시", "테러", "전쟁", "mid", "acled", "hiik", "사상", "폭력",
        "프록시", "행동 빈도", "활동 고조",
    ],
    "policy_concession": [
        "양보", "정책 변화", "수용", "철회", "요구 수락", "순응",
        "정책 지지", "의사결정", "대응 지연", "제재 목표", "협상",
    ],
    "military_posture": [
        "군비", "방위비", "국방비", "병력", "배치", "전개", "기지", "무장",
        "군사화", "투사", "작전", "훈련", "동원", "억지", "억제", "milex",
        "자율성", "군사 이용", "해군",
    ],
    "cyber_incident": [
        "사이버", "침해", "귀속", "apt", "인시던트", "해킹", "재공격",
    ],
    "governance_social": [
        "지지율", "여론", "양극화", "신뢰도", "민주주의", "민주화",
        "거버넌스", "정치 안정", "부패", "선거", "제도 신뢰", "v-dem",
    ],
    "territorial": [
        "점유", "영토", "기지화", "면적", "인공섬", "현상 변경", "점령",
    ],
    "cooperation": [
        "협력", "조약", "준수", "이행", "조정", "동맹", "통합", "제도화",
        "연루", "방기",
    ],
    "nuclear": [
        "핵무장", "핵 확산", "핵 보유", "핵 사용", "핵실험",
    ],
    "shipping_sloc": [
        "통항", "항행", "sloc", "해상", "호송", "해운", "선박", "교통로", "운송",
        "병참", "상선",
    ],
    "tech_capability": [
        "기술", "표준", "특허", "혁신", "반도체", "ooda", "격차 변화",
        "점유율", "r&d", "역량",
    ],
}

# 호환 그룹 — 같은 DV 차원의 양극단·인접 표현은 서로소로 취급하지 않는다.
# 실측 근거: 48케이스 드라이런에서 '양보 증가 vs 대응 강화(방산·훈련)' 류의
# 정당한 반대방향 판정(같은 차원 '대상국 반응'의 두 극)이 오폭됐다 — 오탐이 미탐보다 나쁘다.
COMPAT_GROUPS: dict[str, list[str]] = {
    # 대상국 반응 차원: 양보 ↔ 저항(군사 대응·도발 지속)은 한 DV의 양극
    "target_response": ["policy_concession", "military_posture", "conflict_event"],
    # 경제 차원: 가격과 물량·구조(집중도)는 인접 지표
    "economic": ["market_econ", "trade_flow"],
}


def _classify(dv_text: str) -> list[str]:
    """dependent_var 선언문 → 매칭 클래스 목록 (기계 대조)."""
    low = (dv_text or "").lower()
    return [cid for cid, aliases in CLASSES.items()
            if any(a in low for a in aliases)]


def _title_aliases(title: str) -> list[str]:
    """'상호의존의 무기화 (Weaponized Interdependence)' → 국문·영문 두 별칭."""
    title = (title or "").strip()
    if "(" in title:
        ko = title.split("(")[0].strip()
        en = title[title.index("(") + 1:].rstrip(") ").strip()
        return [a for a in (ko, en) if len(a) >= 3]
    return [title] if len(title) >= 3 else []


def main() -> None:
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT theory_id, title, dependent_var FROM theories "
        "WHERE independent_var IS NOT NULL ORDER BY theory_id"
    ).fetchall()

    lines = [
        "# dv_spec.yaml — 이론별 DV 스펙 (개선위 P4 DV 출처 게이트)",
        "# ⚠️ 생성물 — 직접 편집 금지. 재생성: python3 scripts/build_dv_spec.py",
        "# 원천: db/library.db theories.dependent_var (이론 프로파일 자기 선언) → 클래스 기계 매핑.",
        "# 소비자: services/dv_gate.py (판정 스탬프 강등 게이트).",
        "",
        "classes:",
    ]
    for cid, aliases in CLASSES.items():
        lines.append(f"  {cid}:")
        lines.append("    aliases: [" + ", ".join(f'"{a}"' for a in aliases) + "]")

    lines += ["", "compat_groups:"]
    for gid, members in COMPAT_GROUPS.items():
        lines.append(f"  {gid}: [" + ", ".join(members) + "]")

    lines += ["", "theories:"]
    unmapped = []
    for r in rows:
        classes = _classify(r["dependent_var"])
        if not classes:
            unmapped.append(r["theory_id"])
        lines.append(f"  {r['theory_id']}:")
        al = ", ".join(f'"{a}"' for a in _title_aliases(r["title"]))
        lines.append(f"    aliases: [{al}]")
        lines.append("    dv_classes: [" + ", ".join(classes) + "]")
        dv = (r["dependent_var"] or "").replace('"', "'")
        lines.append(f'    dv_source: "{dv}"   # 원천 선언문 (참조용)')

    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{OUT.name}: 이론 {len(rows)}건 기록, 클래스 미배정 {len(unmapped)}건")
    for t in unmapped:
        print(f"  - 미배정(게이트 불발화): {t}")


if __name__ == "__main__":
    main()
