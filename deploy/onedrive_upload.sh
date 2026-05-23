#!/usr/bin/env bash
# deploy/onedrive_upload.sh -- upload latest encrypted backup to OneDrive.
# Operator: run through duzman-onedrive-backup.service after rclone OAuth setup.

set -euo pipefail
umask 077

RCLONE_CONFIG_PATH="/opt/duzman/.config/rclone/rclone.conf"
RCLONE_REMOTE="onedrive"
RCLONE_REMOTE_PATH="Duzman/Backups"
BACKUPS_DIR="/opt/duzman/backups"
MANIFEST_PATH="${BACKUPS_DIR}/onedrive_upload_manifest.jsonl"
FAILURE_MARKER="${BACKUPS_DIR}/.last_onedrive_upload_failed"
MAX_AGE_HOURS=26
RETENTION_COUNT=12
BACKUP_FILE_PATTERN="duzman-*.tar.gz.gpg"

CURRENT_STEP="startup"
LATEST_BACKUP=""
LATEST_BACKUP_NAME=""

log() {
  printf 'duzman_onedrive_backup: %s\n' "$1"
}

step_error() {
  printf 'duzman_onedrive_backup: ERROR: %s\n' "$1" >&2
  return 1
}

utc_now() {
  date -u +'%Y-%m-%dT%H:%M:%SZ'
}

run_step() {
  CURRENT_STEP="$1"
  shift
  log "$CURRENT_STEP"
  "$@"
}

run_step_or_notify() {
  local exit_code

  CURRENT_STEP="$1"
  shift
  log "$CURRENT_STEP"
  if "$@"; then
    return
  fi
  exit_code=$?
  fail_with_notification "${CURRENT_STEP} failed" "$exit_code"
}

fail_with_notification() {
  local reason="$1"
  local exit_code="${2:-1}"
  local file="${3:-${LATEST_BACKUP_NAME:-none}}"
  local timestamp

  timestamp="$(utc_now)"
  {
    printf 'timestamp=%s\n' "$timestamp"
    printf 'step=%s\n' "$CURRENT_STEP"
    printf 'exit_code=%s\n' "$exit_code"
    printf 'message=%s\n' "$reason"
    printf 'file=%s\n' "$file"
  } >"$FAILURE_MARKER"

  send_failure_notification "$CURRENT_STEP" "$file" "$reason" || true
  step_error "$reason"
}

load_environment() {
  set -a
  # shellcheck source=/dev/null
  source /opt/duzman/.env
  set +a

  [[ -n "${TELEGRAM_BOT_TOKEN:-}" ]] || step_error "TELEGRAM_BOT_TOKEN is required."
  [[ -n "${TELEGRAM_CHAT_ID_BACKUP:-}" ]] || step_error "TELEGRAM_CHAT_ID_BACKUP is required."
  [[ -n "${TELEGRAM_CHAT_ID_SYSTEM:-}" ]] || step_error "TELEGRAM_CHAT_ID_SYSTEM is required."
}

check_rclone_health() {
  local exit_code
  local output

  if output="$(rclone --version --config "${RCLONE_CONFIG_PATH}" 2>&1)"; then
    :
  else
    exit_code=$?
    fail_with_notification "rclone version check failed" "$exit_code"
  fi
  [[ "$output" == *"rclone v"* ]] ||
    fail_with_notification "rclone version output did not contain expected marker"
}

verify_rclone_config() {
  [[ -r "$RCLONE_CONFIG_PATH" ]] ||
    fail_with_notification "rclone config is missing or not readable"
}

find_latest_backup() {
  LATEST_BACKUP="$(
    find "$BACKUPS_DIR" -maxdepth 1 -name "$BACKUP_FILE_PATTERN" -type f -printf '%T@ %p\n' |
      sort -n |
      tail -1 |
      cut -d' ' -f2-
  )"

  [[ -n "$LATEST_BACKUP" ]] || fail_with_notification "no local encrypted backup found"
  LATEST_BACKUP_NAME="$(basename -- "$LATEST_BACKUP")"
}

check_backup_freshness() {
  local age_seconds
  local age_hours
  local mtime_epoch
  local now_epoch

  mtime_epoch="$(stat -c '%Y' -- "$LATEST_BACKUP")"
  now_epoch="$(date -u +'%s')"
  age_seconds=$((now_epoch - mtime_epoch))
  age_hours=$((age_seconds / 3600))

  if ((age_seconds > MAX_AGE_HOURS * 3600)); then
    fail_with_notification "latest backup is stale: ${LATEST_BACKUP_NAME} age_hours=${age_hours}"
  fi
}

compute_sha256() {
  sha256sum "$LATEST_BACKUP" | cut -d' ' -f1
}

remote_path_for() {
  local file_name="$1"
  printf '%s:%s/%s' "$RCLONE_REMOTE" "$RCLONE_REMOTE_PATH" "$file_name"
}

upload_backup() {
  local remote_path

  remote_path="$(remote_path_for "$LATEST_BACKUP_NAME")"
  if ! rclone copyto --config "${RCLONE_CONFIG_PATH}" "$LATEST_BACKUP" "$remote_path"; then
    fail_with_notification "rclone upload failed"
  fi
}

list_remote_json() {
  rclone lsjson --config "${RCLONE_CONFIG_PATH}" --files-only \
    "${RCLONE_REMOTE}:${RCLONE_REMOTE_PATH}"
}

verify_upload() {
  local expected_size="$1"
  local remote_json="$2"

  python3 -c '
import json
import sys

name = sys.argv[1]
expected_size = int(sys.argv[2])
entries = json.load(sys.stdin)
for entry in entries:
    if entry.get("Name") == name and int(entry.get("Size", -1)) == expected_size:
        raise SystemExit(0)
raise SystemExit(1)
' "$LATEST_BACKUP_NAME" "$expected_size" <<<"$remote_json"
}

append_manifest() {
  local remote_path="$1"
  local sha256="$2"
  local size_bytes="$3"
  local uploaded_at

  uploaded_at="$(utc_now)"
  python3 - "$MANIFEST_PATH" "$uploaded_at" "$LATEST_BACKUP_NAME" "$sha256" "$size_bytes" "$remote_path" <<'PY'
import json
import sys

manifest_path, uploaded_at, file_name, sha256, size_bytes, remote = sys.argv[1:]
entry = {
    "uploaded_at": uploaded_at,
    "file": file_name,
    "sha256": sha256,
    "size_bytes": int(size_bytes),
    "remote": remote,
}
with open(manifest_path, "a", encoding="utf-8") as handle:
    handle.write(json.dumps(entry, separators=(",", ":")) + "\n")
PY
}

retention_names_to_delete() {
  local remote_json="$1"

  python3 -c '
import fnmatch
import json
import sys

pattern = sys.argv[1]
retention_count = int(sys.argv[2])
entries = json.load(sys.stdin)
names = sorted(
    entry.get("Name", "")
    for entry in entries
    if fnmatch.fnmatch(entry.get("Name", ""), pattern)
)
extras = max(0, len(names) - retention_count)
for name in names[:extras]:
    print(name)
' "$BACKUP_FILE_PATTERN" "$RETENTION_COUNT" <<<"$remote_json"
}

apply_remote_retention() {
  local name
  local remote_json="$1"

  while IFS= read -r name; do
    [[ -n "$name" ]] || continue
    log "retention_delete remote=$(remote_path_for "$name")"
    rclone deletefile --config "${RCLONE_CONFIG_PATH}" "$(remote_path_for "$name")" ||
      fail_with_notification "rclone deletefile failed" 1 "$name"
  done < <(retention_names_to_delete "$remote_json")
}

remote_backup_count() {
  local remote_json="$1"

  python3 -c '
import fnmatch
import json
import sys

pattern = sys.argv[1]
entries = json.load(sys.stdin)
print(sum(1 for entry in entries if fnmatch.fnmatch(entry.get("Name", ""), pattern)))
' "$BACKUP_FILE_PATTERN" <<<"$remote_json"
}

telegram_send_text() {
  local chat_id="$1"
  local text="$2"

  curl --retry 2 --retry-delay 5 -fsS -K - \
    -G \
    --data-urlencode "chat_id=${chat_id}" \
    --data-urlencode "text=${text}" \
    >/dev/null <<EOF
url = "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage"
EOF
}

send_failure_notification() {
  local step="$1"
  local file="$2"
  local reason="$3"
  local text

  text="Weekly OneDrive backup FAILED: step=${step}, file=${file}, reason=${reason}"
  telegram_send_text "$TELEGRAM_CHAT_ID_SYSTEM" "$text"
  telegram_send_text "$TELEGRAM_CHAT_ID_BACKUP" "$text"
}

send_success_notification() {
  local remote_count="$1"
  local size_mb="$2"
  local text

  text="Weekly OneDrive backup uploaded: ${LATEST_BACKUP_NAME}, size=${size_mb}MB, retention=${remote_count}/12"
  telegram_send_text "$TELEGRAM_CHAT_ID_BACKUP" "$text"
}

main() {
  local remote_json
  local remote_path
  local remote_count
  local sha256
  local size_bytes
  local size_mb

  run_step load_environment load_environment
  run_step check_rclone_health check_rclone_health
  run_step verify_rclone_config verify_rclone_config
  run_step find_latest_backup find_latest_backup
  run_step check_backup_freshness check_backup_freshness

  CURRENT_STEP="compute_sha256"
  log "$CURRENT_STEP"
  if ! sha256="$(compute_sha256)"; then
    fail_with_notification "sha256 calculation failed"
  fi
  size_bytes="$(stat -c '%s' -- "$LATEST_BACKUP")"
  size_mb=$((size_bytes / 1024 / 1024))
  remote_path="$(remote_path_for "$LATEST_BACKUP_NAME")"

  run_step upload_backup upload_backup
  CURRENT_STEP="verify_upload"
  log "$CURRENT_STEP"
  if ! remote_json="$(list_remote_json)"; then
    fail_with_notification "rclone lsjson failed"
  fi
  verify_upload "$size_bytes" "$remote_json" ||
    fail_with_notification "uploaded file not found in remote listing"

  run_step_or_notify append_manifest append_manifest "$remote_path" "$sha256" "$size_bytes"
  run_step_or_notify apply_remote_retention apply_remote_retention "$remote_json"

  if ! remote_json="$(list_remote_json)"; then
    fail_with_notification "rclone lsjson failed after retention"
  fi
  remote_count="$(remote_backup_count "$remote_json")"

  run_step_or_notify clear_failure_marker rm -f -- "$FAILURE_MARKER"
  run_step_or_notify send_success_notification send_success_notification "$remote_count" "$size_mb"
  log "onedrive_upload_completed file=${LATEST_BACKUP_NAME} size_mb=${size_mb} retention=${remote_count}/12"
}

main "$@"
