#!/usr/bin/env bash
# db_backup.sh — geo-intel DB 주간 백업 (라이브 안전 스냅샷 → gzip → iCloud 오프사이트)
#
# 왜 sqlite3 .backup 인가 (cp 금지):
#   intel.db 는 WAL 모드로 수집 잡(collect_standalone)이 상시 쓴다. cp 는 WAL
#   미반영·찢긴 페이지를 복사해 복원 불능 백업을 만든다. .backup 은 SQLite 온라인
#   백업 API로 잠금 없이 일관된 스냅샷을 뜬다 (라이브 DB 안전).
# 왜 iCloud 인가:
#   로컬 디스크 장애 시 923MB DB가 통째 증발한다. iCloud로 오프사이트化(off-site).
# 실패 시:
#   침묵 실패 방지 — collect 잡과 동일한 osascript 알림 + 로그. 백업은 조용히
#   실패하면 안 되므로 어느 줄에서 깨져도 알린다(fail-loud).
#
# 수동 스냅샷 (마이그레이션 전):
#   ./db_backup.sh --tag pre-migration
#   → intel_pre-migration-<날짜>.db.gz 형태로 저장, 로테이션 glob(${name}_[0-9]*)에
#     안 걸려 주간 로테이션이 지워가지 않는다. 스키마 마이그레이션 등 "되돌릴 지점이
#     필요한 순간" 직전에 실행할 것.

set -euo pipefail

# --- 상수 (매직 경로/숫자 금지 — 한곳에서 관리) ---
BACKEND="/Users/kang-yumin/Projects/geo-intel-map/backend"
DB_DIR="$BACKEND/db"
LOG_FILE="$BACKEND/logs/db_backup.log"          # collect 로그 컨벤션(backend/logs) 따름
DEST_DIR="$HOME/Library/Mobile Documents/com~apple~CloudDocs/geo-intel-backups"
# KEEP=8 (구 2주 → 8주): 이 시스템이 실측한 결함 탐지 지연이 근거 —
# region 오염 발견까지 5주, ACLED 정체 발견까지 6주 걸린 전례가 있다. 보존 2주 시절엔
# 오염을 발견한 시점에 이미 깨끗한 세대가 로테이션으로 밀려나 있는 구조였다.
# 8주 = 최장 탐지 지연(6주) + 여유. 용량 근거: gzip 후 세대당 ~127MB(923MB 원본 기준
# 실측) × 8 ≈ 1GB — iCloud 무료 5GB의 20% 수준으로 여유 있음.
KEEP=8
SQLITE="/usr/bin/sqlite3"                         # macOS 기본 제공
STAMP="$(date +%Y%m%d)"

# 백업 대상: "논리이름:파일명" — 논리이름이 출력/로테이션 파일 prefix
DBS=("intel:intel.db" "library:library.db")

# --- 인자 파싱: --tag <이름> (마이그레이션 전 수동 스냅샷용) ---
TAG=""
if [[ "${1:-}" == "--tag" ]]; then
    TAG="${2:?--tag 뒤에 태그 이름이 필요합니다 (예: --tag pre-migration)}"
    # 태그가 숫자로 시작하면 로테이션 glob(${name}_[0-9]*)에 걸려 정기 로테이션에 삭제될 수 있음
    if [[ "$TAG" =~ ^[0-9] ]]; then
        echo "에러: --tag 값은 숫자로 시작할 수 없습니다 (로테이션 오삭제 방지): $TAG" >&2
        exit 1
    fi
fi

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >> "$LOG_FILE"; }

notify_failure() {
    # collect_standalone.py 와 동일한 알림 방식 — launchd엔 실패 훅이 없어 잡이 직접 알린다
    local msg="$1"
    osascript -e "display notification \"$msg\" with title \"geo-intel DB 백업\" sound name \"Basso\"" || true
}

# 어느 줄에서 실패하든 로그 + 알림 후 종료 (부분 성공 없이 fail-loud)
trap 'rc=$?; log "실패(exit $rc) at line $LINENO"; notify_failure "DB 백업 실패 (exit $rc) — 로그 확인: $LOG_FILE"; exit $rc' ERR

mkdir -p "$(dirname "$LOG_FILE")"
mkdir -p "$DEST_DIR"                              # 목적지 없으면 생성
log "=== 백업 시작 (stamp=$STAMP) ==="

for entry in "${DBS[@]}"; do
    name="${entry%%:*}"
    file="${entry##*:}"
    src="$DB_DIR/$file"

    if [[ ! -f "$src" ]]; then
        log "SKIP: $src 없음"
        continue
    fi

    # 백업 직전 무결성 검사 — 손상 스냅샷이 로테이션으로 건강한 세대를 밀어내는 것을 차단.
    # quick_check 선택 이유: full integrity_check는 페이지 전수 검사라 922MB DB엔 과도하고
    # 주간 잡 러닝타임을 늘린다. quick_check는 헤더/구조 위주라 빠르면서도 손상 탐지엔 충분.
    log "$name: 무결성 검사 (quick_check)"
    check="$("$SQLITE" "$src" "PRAGMA quick_check;")"
    if [[ "$check" != "ok" ]]; then
        log "$name: 무결성 검사 실패 — $check (백업 중단, 로테이션 미실행)"
        false   # 0이 아닌 종료로 trap ERR을 태워 알림+로그+중단 (기존 fail-loud 경로 재사용)
    fi

    # 임시 스냅샷은 로컬에 (iCloud에 찢긴 중간파일을 만들지 않도록) → gzip 후 목적지로
    tmp="$(mktemp -t "geo_${name}")"
    if [[ -n "$TAG" ]]; then
        out="$DEST_DIR/${name}_${TAG}-${STAMP}.db.gz"   # 로테이션 glob(${name}_[0-9]*) 밖 — 태그 스냅샷은 로테이션에서 제외
    else
        out="$DEST_DIR/${name}_${STAMP}.db.gz"
    fi

    log "$name: .backup → 임시 스냅샷"
    "$SQLITE" "$src" ".backup '$tmp'"            # 온라인 백업 API (WAL 일관 스냅샷)
    log "$name: gzip → $out"
    gzip -c "$tmp" > "$out"
    rm -f "$tmp"

    if [[ -n "$TAG" ]]; then
        # 수동 태그 스냅샷은 로테이션 대상이 아님 — 여기서 끝
        log "$name: 태그 스냅샷 완료 ($(du -h "$out" | cut -f1))"
        continue
    fi

    # 로테이션: mtime 최신 KEEP개만 유지, 나머지 삭제 (방금 쓴 것이 가장 최신)
    # glob을 [0-9]로 제한해 태그 스냅샷(${name}_<태그>-<날짜>.db.gz)을 로테이션 대상에서 제외
    old_files="$(ls -1t "$DEST_DIR/${name}_"[0-9]*.db.gz 2>/dev/null | tail -n +$((KEEP + 1)) || true)"
    if [[ -n "$old_files" ]]; then
        while IFS= read -r old; do
            [[ -n "$old" ]] || continue
            log "$name: 로테이션 삭제 $old"
            rm -f "$old"
        done <<< "$old_files"
    fi

    log "$name: 완료 ($(du -h "$out" | cut -f1))"
done

log "=== 백업 완료 ==="
