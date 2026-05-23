#!/usr/bin/env bash
# deploy/backup.sh -- create encrypted local backups and deliver them to Telegram.
# Operator: run through duzman-backup.service. Codex/Claude MUST NOT execute this script.

set -euo pipefail
IFS=$'\n\t'

TARGET_DIR=/opt/duzman
BACKUP_DIR="$TARGET_DIR/backups"
CONFIG_DIR="$TARGET_DIR/config"
ENV_FILE="$TARGET_DIR/.env"
RETENTION_COUNT=7
TELEGRAM_MAX_BYTES=$((50 * 1024 * 1024))

CURRENT_STEP="startup"
WORKDIR=""
PARTIAL_FILE=""
FINAL_FILE=""
BACKUP_SIZE_MB=0
TELEGRAM_STATUS=""

trap report_failed_step ERR
trap cleanup_on_exit EXIT

log() {
  printf 'duzman_backup: %s\n' "$1"
}

step_error() {
  printf 'duzman_backup: ERROR: %s\n' "$1" >&2
  return 1
}

report_failed_step() {
  printf 'duzman_backup: failed step: %s\n' "$CURRENT_STEP" >&2
}

cleanup_on_exit() {
  local saved_exit=$?

  if ((saved_exit != 0)) && [[ -n "$PARTIAL_FILE" && -e "$PARTIAL_FILE" ]]; then
    rm -f -- "$PARTIAL_FILE"
    printf 'duzman_backup: cleanup: removed partial backup %s\n' "$PARTIAL_FILE" >&2
  fi
  if [[ -n "$WORKDIR" && -d "$WORKDIR" ]]; then
    rm -rf -- "$WORKDIR"
  fi
  exit "$saved_exit"
}

run_step() {
  CURRENT_STEP="$1"
  shift
  log "$CURRENT_STEP"
  "$@"
}

check_required_env() {
  [[ -n "${DATABASE_URL:-}" ]] || step_error "DATABASE_URL is required."
  [[ -n "${BACKUP_GPG_PASSPHRASE:-}" ]] || step_error "BACKUP_GPG_PASSPHRASE is required."
  [[ -n "${TELEGRAM_BOT_TOKEN:-}" ]] || step_error "TELEGRAM_BOT_TOKEN is required."
  [[ -n "${TELEGRAM_CHAT_ID_BACKUP:-}" ]] || step_error "TELEGRAM_CHAT_ID_BACKUP is required."
}

check_backup_dir() {
  [[ -d "$BACKUP_DIR" ]] || step_error "backup directory is missing: $BACKUP_DIR"
  [[ -w "$BACKUP_DIR" ]] || step_error "backup directory is not writable: $BACKUP_DIR"
}

check_commands() {
  local command_name
  local required_commands=(
    "pg_dump"
    "gpg"
    "tar"
    "curl"
    "sha256sum"
  )

  for command_name in "${required_commands[@]}"; do
    command -v "$command_name" >/dev/null 2>&1 ||
      step_error "required command is missing: $command_name"
  done
}

prepare_paths() {
  local ts

  ts="$(date -u +'%Y%m%d-%H%M%S')"
  FINAL_FILE="$BACKUP_DIR/duzman-${ts}.tar.gz.gpg"
  PARTIAL_FILE="$BACKUP_DIR/.duzman-${ts}.tar.gz.gpg.partial"
  WORKDIR="$(mktemp -d "/tmp/duzman_backup_${ts}.XXXXXX")"
}

dump_database() {
  pg_dump "$DATABASE_URL" \
    -t pattern_triggers \
    -t alerts_sent \
    -t etf_flows \
    -t alert_deliveries \
    -t telegram_channel_state \
    -t alembic_version \
    -f "$WORKDIR/db.sql"

  [[ -s "$WORKDIR/db.sql" ]] || step_error "pg_dump produced an empty db.sql"
}

copy_backup_inputs() {
  local config_file
  local copied_configs=0

  mkdir -p -- "$WORKDIR/config"

  if compgen -G "$CONFIG_DIR/*.yaml" >/dev/null; then
    for config_file in "$CONFIG_DIR"/*.yaml; do
      cp -- "$config_file" "$WORKDIR/config/"
      copied_configs=1
    done
  fi

  if ((copied_configs == 0)); then
    log "warning event=no_yaml_configs_found path=$CONFIG_DIR"
  fi

  cp -- "$ENV_FILE" "$WORKDIR/.env"
}

create_archive() {
  tar -C "$WORKDIR" -czf "$WORKDIR/backup.tar.gz" db.sql config .env
  [[ -s "$WORKDIR/backup.tar.gz" ]] || step_error "tar produced an empty archive"
}

encrypt_archive() {
  gpg --batch --yes --passphrase-fd 0 --symmetric --cipher-algo AES256 \
    --output "$PARTIAL_FILE" "$WORKDIR/backup.tar.gz" \
    <<<"$BACKUP_GPG_PASSPHRASE"

  [[ -s "$PARTIAL_FILE" ]] || step_error "gpg produced an empty encrypted backup"
}

verify_encrypted_file() {
  sha256sum "$PARTIAL_FILE" >/dev/null
}

finalize_backup() {
  mv -- "$PARTIAL_FILE" "$FINAL_FILE"
  PARTIAL_FILE=""
  chmod 600 -- "$FINAL_FILE"
}

deliver_to_telegram() {
  local size_bytes
  local size_mb
  local ts

  size_bytes="$(stat -c '%s' -- "$FINAL_FILE")"
  size_mb=$((size_bytes / 1024 / 1024))
  BACKUP_SIZE_MB="$size_mb"
  ts="$(basename -- "$FINAL_FILE")"
  ts="${ts#duzman-}"
  ts="${ts%.tar.gz.gpg}"

  if ((size_bytes <= TELEGRAM_MAX_BYTES)); then
    if ! curl --retry 2 --retry-delay 5 -fsS -K - \
      -F document=@"$FINAL_FILE" \
      -F chat_id="$TELEGRAM_CHAT_ID_BACKUP" \
      -F caption="Duzman backup ${ts} (${size_mb}MB)" \
      >/dev/null <<EOF
url = "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendDocument"
EOF
    then
      step_error "telegram delivery failed for ${ts}"
    fi
    TELEGRAM_STATUS="document"
  else
    if ! curl --retry 2 --retry-delay 5 -fsS -K - \
      -G \
      --data-urlencode "chat_id=${TELEGRAM_CHAT_ID_BACKUP}" \
      --data-urlencode "text=Duzman backup ${ts} skipped Telegram (size=${size_mb}MB > 50MB), local only at ${FINAL_FILE}" \
      >/dev/null <<EOF
url = "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage"
EOF
    then
      step_error "telegram delivery failed for ${ts}"
    fi
    TELEGRAM_STATUS="size_skipped"
  fi
}

apply_retention() {
  (
    cd -- "$BACKUP_DIR"
    ls -1 duzman-*.tar.gz.gpg 2>/dev/null | sort | head -n -"${RETENTION_COUNT}" |
      xargs -r rm -f --
  )
  log "retention: kept last 7 backups"
}

main() {
  run_step check_required_env check_required_env
  run_step check_backup_dir check_backup_dir
  run_step check_commands check_commands
  run_step prepare_paths prepare_paths
  run_step dump_database dump_database
  run_step copy_backup_inputs copy_backup_inputs
  run_step create_archive create_archive
  run_step encrypt_archive encrypt_archive
  run_step verify_encrypted_file verify_encrypted_file
  run_step finalize_backup finalize_backup
  run_step deliver_to_telegram deliver_to_telegram
  run_step apply_retention apply_retention
  log "backup_completed file=${FINAL_FILE} size_mb=${BACKUP_SIZE_MB} telegram=${TELEGRAM_STATUS}"
}

main "$@"
