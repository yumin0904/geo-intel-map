#!/usr/bin/env python3
"""build_vault_maps.py

geo-intel-map/library/ 아래 모든 md 파일의 frontmatter(sector_tag, geopol_region)를
스캔해 옵시디언 허브 노트(MOC)를 library/00_maps/ 에 생성한다.

표준 라이브러리만 사용 (PyYAML 의존 없음). frontmatter는 `key: value`와
간단한 리스트(`key:\n  - item`)만 지원하는 자체 파서로 충분히 처리 가능.

재실행 시 00_maps/ 안의 기존 생성 파일만 덮어쓴다. 00_maps 밖의 파일은
절대 읽기 전용으로만 다루며 수정하지 않는다.
"""

from __future__ import annotations

import sys
import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LIBRARY_DIR = REPO_ROOT / "library"
MAPS_DIR = LIBRARY_DIR / "00_maps"

ASSET_TYPE_LABELS = {
    "theory": "이론",
    "briefing": "브리핑",
    "norm": "규범",
    "case_study": "케이스",
}
ASSET_TYPE_ORDER = ["theory", "briefing", "norm", "case_study"]

GENERATED_HEADER_PREFIX = "> ⚠️ 자동 생성 색인 (build_vault_maps.py)"


def parse_frontmatter(path: Path) -> dict | None:
    """아주 단순한 frontmatter 파서.

    `---` 로 시작/종료하는 블록 안에서 `key: value` 라인과
    `key:` 다음에 오는 `  - item` 리스트 라인만 처리한다.
    파싱 불가능하면 None을 반환한다.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        print(f"[WARN] 파일 읽기 실패, 건너뜀: {path} ({e})", file=sys.stderr)
        return None

    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        print(f"[WARN] frontmatter 시작 구분자(---) 없음, 건너뜀: {path}", file=sys.stderr)
        return None

    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break
    if end_idx is None:
        print(f"[WARN] frontmatter 종료 구분자(---) 없음, 건너뜀: {path}", file=sys.stderr)
        return None

    data: dict = {}
    current_list_key = None
    for line in lines[1:end_idx]:
        if not line.strip():
            continue
        # 리스트 아이템
        if line.startswith(("  - ", "- ")) and current_list_key is not None:
            item = line.strip()[2:].strip()
            item = _strip_quotes(item)
            data.setdefault(current_list_key, [])
            if isinstance(data[current_list_key], list):
                data[current_list_key].append(item)
            continue

        if ":" not in line:
            # 예상치 못한 형식의 라인 - 무시하고 계속 진행
            current_list_key = None
            continue

        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()

        if value == "":
            # 다음 줄부터 리스트일 가능성
            current_list_key = key
            data[key] = None
        else:
            current_list_key = None
            data[key] = _strip_quotes(value)

    return data


def _strip_quotes(s: str) -> str:
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"'):
        return s[1:-1]
    return s


def collect_entries() -> tuple[list[dict], int, int]:
    """library/**/*.md (00_maps 제외) 를 스캔해 엔트리 목록을 반환.

    Returns:
        (entries, parse_skipped, region_missing)
    """
    entries = []
    parse_skipped = 0
    region_missing = 0

    md_files = sorted(LIBRARY_DIR.rglob("*.md"))
    for f in md_files:
        try:
            f.relative_to(MAPS_DIR)
            continue  # 00_maps 자신은 제외
        except ValueError:
            pass

        fm = parse_frontmatter(f)
        if fm is None:
            parse_skipped += 1
            continue

        asset_type = fm.get("asset_type")
        title = fm.get("title") or f.stem
        sector_tag = fm.get("sector_tag")
        geopol_region = fm.get("geopol_region")

        if not asset_type or not sector_tag:
            print(f"[WARN] asset_type 또는 sector_tag 누락, 건너뜀: {f}", file=sys.stderr)
            parse_skipped += 1
            continue

        if not geopol_region or geopol_region.lower() == "null":
            region_missing += 1
            geopol_region = None

        entries.append(
            {
                "path": f,
                "stem": f.stem,
                "asset_type": asset_type,
                "title": title,
                "sector_tag": sector_tag,
                "geopol_region": geopol_region,
            }
        )

    return entries, parse_skipped, region_missing


def render_hub(title: str, groups: dict[str, list[dict]], now: str) -> str:
    lines = []
    lines.append(f"{GENERATED_HEADER_PREFIX} — 직접 편집 금지, 재실행으로 갱신. 생성: {now}")
    lines.append("")
    lines.append(f"# {title}")
    lines.append("")

    total = sum(len(v) for v in groups.values())
    lines.append(f"총 {total}편")
    lines.append("")

    for asset_type in ASSET_TYPE_ORDER:
        items = groups.get(asset_type, [])
        if not items:
            continue
        label = ASSET_TYPE_LABELS.get(asset_type, asset_type)
        lines.append(f"## {label} ({len(items)})")
        lines.append("")
        for item in sorted(items, key=lambda x: x["stem"]):
            lines.append(f"- [[{item['stem']}]] — {item['title']}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def build_maps() -> None:
    MAPS_DIR.mkdir(parents=True, exist_ok=True)

    entries, parse_skipped, region_missing = collect_entries()

    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    sector_map: dict[str, dict[str, list[dict]]] = {}
    region_map: dict[str, dict[str, list[dict]]] = {}

    for e in entries:
        sector_map.setdefault(e["sector_tag"], {}).setdefault(e["asset_type"], []).append(e)
        if e["geopol_region"]:
            region_map.setdefault(e["geopol_region"], {}).setdefault(e["asset_type"], []).append(e)

    generated_files: list[tuple[str, int]] = []  # (filename, link_count)

    for sector, groups in sorted(sector_map.items()):
        fname = f"sector_{sector}.md"
        content = render_hub(f"섹터 허브: {sector}", groups, now)
        (MAPS_DIR / fname).write_text(content, encoding="utf-8")
        link_count = sum(len(v) for v in groups.values())
        generated_files.append((fname, link_count))

    for region, groups in sorted(region_map.items()):
        fname = f"region_{region}.md"
        content = render_hub(f"지역 허브: {region}", groups, now)
        (MAPS_DIR / fname).write_text(content, encoding="utf-8")
        link_count = sum(len(v) for v in groups.values())
        generated_files.append((fname, link_count))

    # MAPS.md 최상위 안내판
    maps_lines = []
    maps_lines.append(f"{GENERATED_HEADER_PREFIX} — 직접 편집 금지, 재실행으로 갱신. 생성: {now}")
    maps_lines.append("")
    maps_lines.append("# MAPS — 볼트 허브 색인")
    maps_lines.append("")
    maps_lines.append(f"총 {len(entries)}편 (파싱 실패/필드 누락 {parse_skipped}편 제외) 기준 자동 생성.")
    maps_lines.append("")

    maps_lines.append("## 섹터")
    maps_lines.append("")
    for sector, groups in sorted(sector_map.items()):
        count = sum(len(v) for v in groups.values())
        maps_lines.append(f"- [[sector_{sector}]] ({count}편)")
    maps_lines.append("")

    maps_lines.append("## 지역")
    maps_lines.append("")
    for region, groups in sorted(region_map.items()):
        count = sum(len(v) for v in groups.values())
        maps_lines.append(f"- [[region_{region}]] ({count}편)")
    maps_lines.append("")

    (MAPS_DIR / "MAPS.md").write_text("\n".join(maps_lines).rstrip() + "\n", encoding="utf-8")
    generated_files.append(("MAPS.md", len(sector_map) + len(region_map)))

    total_links = sum(c for _, c in generated_files)

    print(f"생성 파일 수: {len(generated_files)}")
    print(f"총 위키링크 수(허브당 항목 합): {total_links}")
    print(f"파싱 실패/필수 필드 누락으로 건너뛴 파일: {parse_skipped}편")
    print(f"geopol_region 누락(null/미지정)으로 지역 허브에서 제외된 파일: {region_missing}편")
    for fname, count in generated_files:
        print(f"  - {fname}: {count}")


if __name__ == "__main__":
    build_maps()
