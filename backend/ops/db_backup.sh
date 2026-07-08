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

set -euo pipefail

# --- 상수 (매직 경로/숫자 금지 — 한곳에서 관리) ---
BACKEND="/Users/kang-yumin/Projects/geo-intel-map/backend"
DB_DIR="$BACKEND/db"
LOG_FILE="$BACKEND/logs/db_backup.log"          # collect 로그 컨벤션(backend/logs) 따름
DEST_DIR="$HOME/Library/Mobile Documents/com~apple~CloudDocs/geo-intel-backups"
KEEP=2                                            # DB별 유지 개수 (iCloud 무료 5GB 고려)
SQLITE="/usr/bin/sqlite3"                         # macOS 기본 제공
STAMP="$(date +%Y%m%d)"

# 백업 대상: "논리이름:파일명" — 논리이름이 출력/로테이션 파일 prefix
DBS=("intel:intel.db" "library:library.db")

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

    # 임시 스냅샷은 로컬에 (iCloud에 찢긴 중간파일을 만들지 않도록) → gzip 후 목적지로
    tmp="$(mktemp -t "geo_${name}")"
    out="$DEST_DIR/${name}_${STAMP}.db.gz"

    log "$name: .backup → 임시 스냅샷"
    "$SQLITE" "$src" ".backup '$tmp'"            # 온라인 백업 API (WAL 일관 스냅샷)
    log "$name: gzip → $out"
    gzip -c "$tmp" > "$out"
    rm -f "$tmp"

    # 로테이션: mtime 최신 KEEP개만 유지, 나머지 삭제 (방금 쓴 것이 가장 최신)
    old_files="$(ls -1t "$DEST_DIR/${name}_"*.db.gz 2>/dev/null | tail -n +$((KEEP + 1)) || true)"
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
