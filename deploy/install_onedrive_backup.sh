#!/usr/bin/env bash
# deploy/install_onedrive_backup.sh -- install Day 10B OneDrive backup units.
# Operator: run with root privileges after rclone binary installation.

set -euo pipefail

TARGET_DIR=/opt/duzman
SERVICE_USER=duzman
SERVICE_GROUP=duzman
SYSTEMD_DIR=/etc/systemd/system
RCLONE_CONFIG_DIR="$TARGET_DIR/.config/rclone"
RCLONE_CONFIG_PATH="$RCLONE_CONFIG_DIR/rclone.conf"
UNIT_SOURCE_DIR=""
UNIT_FILES=(
  "duzman-onedrive-backup.service"
  "duzman-onedrive-backup.timer"
)

usage() {
  cat <<'EOF'
Usage: deploy/install_onedrive_backup.sh

Install Day 10B OneDrive backup systemd units. Run with root privileges.
EOF
}

step_error() {
  printf 'install_onedrive_backup: ERROR: %s\n' "$1" >&2
  return 1
}

run_step() {
  printf 'install_onedrive_backup: %s\n' "$1"
  shift
  "$@"
}

resolve_paths() {
  local script_dir

  script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
  UNIT_SOURCE_DIR="$script_dir/systemd"
}

check_running_as_root() {
  if ((EUID != 0)); then
    step_error "run as root."
  fi
}

check_rclone_binary() {
  command -v rclone >/dev/null 2>&1 ||
    step_error "rclone is not installed; see deploy/README.md section \"Weekly OneDrive backup\"."
  rclone version
}

create_config_dir() {
  install -d -o "$SERVICE_USER" -g "$SERVICE_GROUP" -m 700 "$TARGET_DIR/.config"
  install -d -o "$SERVICE_USER" -g "$SERVICE_GROUP" -m 700 "$RCLONE_CONFIG_DIR"
}

warn_missing_config() {
  if [[ ! -f "$RCLONE_CONFIG_PATH" ]]; then
    printf 'install_onedrive_backup: WARNING: %s is missing; complete rclone OAuth before the timer fires.\n' "$RCLONE_CONFIG_PATH" >&2
  fi
}

check_unit_sources() {
  local unit_file

  for unit_file in "${UNIT_FILES[@]}"; do
    [[ -f "$UNIT_SOURCE_DIR/$unit_file" ]] ||
      step_error "unit source file is missing: $UNIT_SOURCE_DIR/$unit_file"
  done
}

install_units() {
  local unit_file

  for unit_file in "${UNIT_FILES[@]}"; do
    cp -- "$UNIT_SOURCE_DIR/$unit_file" "$SYSTEMD_DIR/$unit_file"
    chmod 644 -- "$SYSTEMD_DIR/$unit_file"
    chown root:root -- "$SYSTEMD_DIR/$unit_file"
  done
  systemctl daemon-reload
  systemctl enable duzman-onedrive-backup.timer
}

print_summary() {
  printf 'install_onedrive_backup: config_path=%s\n' "$RCLONE_CONFIG_PATH"
  systemctl status duzman-onedrive-backup.timer --no-pager || true
  systemctl list-timers --all duzman-onedrive-backup.timer --no-pager || true
  printf 'install_onedrive_backup: runbook=deploy/README.md#weekly-onedrive-backup\n'
  printf 'install_onedrive_backup: success\n'
}

main() {
  if (($# > 0)); then
    case "$1" in
      -h | --help)
        usage
        exit 0
        ;;
      *)
        usage >&2
        exit 1
        ;;
    esac
  fi

  run_step resolve_paths resolve_paths
  run_step check_running_as_root check_running_as_root
  run_step check_rclone_binary check_rclone_binary
  run_step create_config_dir create_config_dir
  run_step warn_missing_config warn_missing_config
  run_step check_unit_sources check_unit_sources
  run_step install_units install_units
  run_step print_summary print_summary
}

main "$@"
