#!/usr/bin/env bash
# deploy/install_systemd.sh -- install Duzman systemd unit files.
# Operator: run as root or via sudo. Codex/Claude MUST NOT execute this script.

set -euo pipefail

TARGET_DIR=/opt/duzman
SERVICE_USER=duzman
SERVICE_GROUP=duzman
SYSTEMD_DIR=/etc/systemd/system
UNIT_SOURCE_DIR=""
DRY_RUN=0
CURRENT_STEP="startup"
UNIT_FILES_COPIED=0

UNIT_FILES=(
  "duzman.service"
  "duzman-health.service"
  "duzman-scheduler.service"
  "duzman-backup.service"
  "duzman-backup.timer"
)

trap report_failed_step ERR
trap cleanup_on_exit EXIT

usage() {
  cat <<'EOF'
Usage: deploy/install_systemd.sh [--dry-run]

Options:
  --dry-run   Print planned install actions without writing files or calling systemctl.
  -h, --help  Show this help.
EOF
}

report_failed_step() {
  printf 'install_systemd: failed step: %s\n' "$CURRENT_STEP" >&2
}

cleanup_on_exit() {
  local saved_exit=$?

  if ((saved_exit != 0 && UNIT_FILES_COPIED == 1 && DRY_RUN == 0)); then
    systemctl daemon-reload || true
  fi
  exit "$saved_exit"
}

step_error() {
  printf 'ERROR: %s\n' "$1" >&2
  return 1
}

run_step() {
  CURRENT_STEP="$1"
  shift
  printf 'install_systemd: %s\n' "$CURRENT_STEP"
  "$@"
}

parse_args() {
  while (($# > 0)); do
    case "$1" in
      --dry-run)
        DRY_RUN=1
        shift
        ;;
      -h | --help)
        usage
        exit 0
        ;;
      *)
        printf 'ERROR: unknown argument: %s\n' "$1" >&2
        usage >&2
        exit 1
        ;;
    esac
  done
}

resolve_paths() {
  local script_dir

  script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
  UNIT_SOURCE_DIR="$script_dir/systemd"
}

check_running_as_root_or_sudo() {
  if ((EUID != 0)); then
    step_error "run as root or via sudo."
  fi
}

check_runtime_layout() {
  [[ -x "$TARGET_DIR/.venv/bin/python" ]] ||
    step_error "runtime python is missing or not executable: $TARGET_DIR/.venv/bin/python"
  [[ -f "$TARGET_DIR/src/duzman/runtime/run_health_server.py" ]] ||
    step_error "health runtime entrypoint is missing under $TARGET_DIR"
  [[ -f "$TARGET_DIR/src/duzman/runtime/run_scheduler.py" ]] ||
    step_error "scheduler runtime entrypoint is missing under $TARGET_DIR"

  if [[ ! -d "$TARGET_DIR/backups" ]]; then
    mkdir -- "$TARGET_DIR/backups"
    chown "$SERVICE_USER:$SERVICE_GROUP" -- "$TARGET_DIR/backups"
    return
  fi

  local backup_owner
  backup_owner="$(stat -c '%U:%G' -- "$TARGET_DIR/backups")"
  [[ "$backup_owner" == "$SERVICE_USER:$SERVICE_GROUP" ]] ||
    step_error "backup directory owner is $backup_owner; expected $SERVICE_USER:$SERVICE_GROUP"
}

check_env_file_stat_only() {
  local env_file="$TARGET_DIR/.env"
  local env_mode
  local env_owner

  [[ -f "$env_file" ]] || step_error ".env file is missing: $env_file"

  env_owner="$(stat -c '%U:%G' -- "$env_file")"
  [[ "$env_owner" == "$SERVICE_USER:$SERVICE_GROUP" ]] ||
    step_error ".env owner is $env_owner; expected $SERVICE_USER:$SERVICE_GROUP"

  env_mode="$(stat -c '%a' -- "$env_file")"
  [[ "$env_mode" == "600" ]] ||
    step_error ".env mode is $env_mode; expected 600"
}

check_systemctl_available() {
  command -v systemctl >/dev/null 2>&1 || step_error "systemctl is not available."
  [[ -d "$SYSTEMD_DIR" ]] || step_error "systemd unit directory is missing: $SYSTEMD_DIR"
}

check_unit_sources() {
  local unit_file

  for unit_file in "${UNIT_FILES[@]}"; do
    [[ -f "$UNIT_SOURCE_DIR/$unit_file" ]] ||
      step_error "unit source file is missing: $UNIT_SOURCE_DIR/$unit_file"
  done
}

print_plan() {
  local unit_file

  printf 'install_systemd: plan\n'
  for unit_file in "${UNIT_FILES[@]}"; do
    printf '  copy %s -> %s/%s\n' "$UNIT_SOURCE_DIR/$unit_file" "$SYSTEMD_DIR" "$unit_file"
  done
  printf '  chmod 644 installed unit files\n'
  printf '  chown root:root installed unit files\n'
  printf '  systemctl daemon-reload\n'
  printf '  systemctl enable duzman.service\n'
  printf '  systemctl enable duzman-backup.timer (timer only; service is static)\n'
  printf '  no units will be started by this script\n'
}

copy_unit_files() {
  local unit_file

  if ((DRY_RUN == 1)); then
    print_plan
    return
  fi

  for unit_file in "${UNIT_FILES[@]}"; do
    cp -- "$UNIT_SOURCE_DIR/$unit_file" "$SYSTEMD_DIR/$unit_file"
    UNIT_FILES_COPIED=1
  done
}

set_unit_file_ownership() {
  local unit_file

  if ((DRY_RUN == 1)); then
    return
  fi

  for unit_file in "${UNIT_FILES[@]}"; do
    chmod 644 -- "$SYSTEMD_DIR/$unit_file"
    chown root:root -- "$SYSTEMD_DIR/$unit_file"
  done
}

reload_systemd() {
  if ((DRY_RUN == 1)); then
    return
  fi

  systemctl daemon-reload
}

enable_units() {
  if ((DRY_RUN == 1)); then
    return
  fi

  systemctl enable duzman.service duzman-backup.timer
}

main() {
  parse_args "$@"
  run_step resolve_paths resolve_paths
  run_step check_running_as_root_or_sudo check_running_as_root_or_sudo
  run_step check_runtime_layout check_runtime_layout
  run_step check_env_file_stat_only check_env_file_stat_only
  run_step check_systemctl_available check_systemctl_available
  run_step check_unit_sources check_unit_sources
  run_step copy_unit_files copy_unit_files
  run_step set_unit_file_ownership set_unit_file_ownership
  run_step reload_systemd reload_systemd
  run_step enable_units enable_units

  if ((DRY_RUN == 0)); then
    printf 'install_systemd: enabled. Run `sudo systemctl start duzman` to start health + scheduler.\n'
  fi
  printf 'install_systemd: success\n'
}

main "$@"
