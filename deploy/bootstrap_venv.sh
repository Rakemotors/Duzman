#!/usr/bin/env bash
# deploy/bootstrap_venv.sh — bootstrap /opt/duzman/.venv for production runtime
# Operator: run as root or via sudo. Codex/Claude MUST NOT execute this script.

set -euo pipefail

TARGET_DIR=/opt/duzman
VENV_DIR="$TARGET_DIR/.venv"
SERVICE_USER=duzman
MIN_PY_MAJOR=3
MIN_PY_MINOR=12
PIP_CACHE_DIR=/tmp/duzman_bootstrap_pip_cache
HEALTH_CHECK_FILE=/tmp/duzman_health_check.json
STALE_TARGET_MESSAGE="/opt/duzman is stale or missing required runtime files. Update deploy target first via the approved deploy flow (sudo deploy/deploy.sh --apply) before running bootstrap_venv.sh."

RECREATE=0
CURRENT_STEP="startup"
VENV_CREATED_BY_THIS_RUN=0
BOOTSTRAP_REACHED_SUCCESS=0

trap report_failed_step ERR
trap cleanup_on_exit EXIT

usage() {
  cat <<'EOF'
Usage: deploy/bootstrap_venv.sh [--recreate]

Options:
  --recreate  Remove an existing /opt/duzman/.venv and build it again.
  -h, --help  Show this help.
EOF
}

step_error() {
  printf 'ERROR: %s\n' "$1" >&2
  return 1
}

report_failed_step() {
  printf 'bootstrap_venv: failed step: %s\n' "$CURRENT_STEP" >&2
}

cleanup_on_exit() {
  local saved_exit=$?

  if [[ "$VENV_CREATED_BY_THIS_RUN" == "1" && "$BOOTSTRAP_REACHED_SUCCESS" == "0" ]]; then
    rm -rf -- "$VENV_DIR"
    printf 'bootstrap_venv: removed partial venv at %s (failed before success marker)\n' "$VENV_DIR" >&2
  fi
  rm -rf -- "$PIP_CACHE_DIR" 2>/dev/null || true
  rm -f -- "$HEALTH_CHECK_FILE" 2>/dev/null || true
  exit "$saved_exit"
}

run_step() {
  CURRENT_STEP="$1"
  shift
  printf 'bootstrap_venv: %s\n' "$CURRENT_STEP"
  "$@"
}

check_running_as_root_or_sudo() {
  if ((EUID != 0)); then
    step_error "run as root or via sudo."
  fi
}

check_target_exists() {
  if [[ ! -d "$TARGET_DIR" ]]; then
    step_error "target directory does not exist: $TARGET_DIR"
  fi
  if [[ ! -f "$TARGET_DIR/pyproject.toml" ]]; then
    step_error "Duzman pyproject marker is missing: $TARGET_DIR/pyproject.toml"
  fi
}

check_python_version() {
  local py_major
  local py_minor

  if [[ ! -x /usr/bin/python3 ]]; then
    step_error "python3 is not available at /usr/bin/python3."
  fi

  read -r py_major py_minor < <(
    /usr/bin/python3 -c 'import sys; print(sys.version_info.major, sys.version_info.minor)'
  )
  if ((py_major < MIN_PY_MAJOR || (py_major == MIN_PY_MAJOR && py_minor < MIN_PY_MINOR))); then
    step_error "python3 ${MIN_PY_MAJOR}.${MIN_PY_MINOR} or newer is required."
  fi
}

stale_target_error() {
  printf '%s\n' "$STALE_TARGET_MESSAGE" >&2
  return 1
}

check_target_freshness() {
  local dependency
  local required_file

  for required_file in \
    "src/duzman/health/app.py" \
    "src/duzman/health/server.py" \
    "src/duzman/runtime/run_health_server.py" \
    "src/duzman/runtime/run_scheduler.py"; do
    [[ -f "$TARGET_DIR/$required_file" ]] || stale_target_error
  done

  for dependency in \
    "fastapi" \
    "uvicorn" \
    "httpx" \
    "apscheduler" \
    "sqlalchemy" \
    "pydantic" \
    "psycopg2-binary"; do
    grep -F -- "$dependency" "$TARGET_DIR/pyproject.toml" >/dev/null ||
      stale_target_error
  done
}

run_target_python() {
  sudo -u "$SERVICE_USER" env PIP_CACHE_DIR="$PIP_CACHE_DIR" \
    bash -c 'cd "$0" && exec "$1" "${@:2}"' "$TARGET_DIR" "$VENV_DIR/bin/python" "$@"
}

validate_existing_venv() {
  run_target_python -c \
    'from importlib.metadata import version; v = version("duzman"); assert v == "0.1.0", v' &&
  run_target_python -c \
    'import duzman.health.app, duzman.runtime.run_health_server, duzman.runtime.run_scheduler'
}

handle_existing_venv() {
  if [[ ! -e "$VENV_DIR" && ! -L "$VENV_DIR" ]]; then
    return
  fi

  if ((RECREATE == 0)); then
    if validate_existing_venv; then
      printf 'venv at %s is valid; nothing to do\n' "$VENV_DIR"
      exit 0
    fi
    printf 'existing venv at %s is invalid; rerun with --recreate\n' "$VENV_DIR" >&2
    exit 1
  fi

  rm -rf -- "$VENV_DIR"
}

create_venv() {
  sudo -u "$SERVICE_USER" /usr/bin/python3 -m venv "$VENV_DIR"
  VENV_CREATED_BY_THIS_RUN=1
}

upgrade_pip() {
  sudo -u "$SERVICE_USER" env PIP_CACHE_DIR="$PIP_CACHE_DIR" \
    "$VENV_DIR/bin/python" -m pip install --upgrade pip
}

install_package_editable() {
  sudo -u "$SERVICE_USER" env PIP_CACHE_DIR="$PIP_CACHE_DIR" \
    "$VENV_DIR/bin/pip" install -e "$TARGET_DIR"
}

verify_imports() {
  run_target_python -c "
from importlib.metadata import version
v = version('duzman')
assert v == '0.1.0', f'unexpected duzman version: {v}'
import duzman.health.app
import duzman.runtime.run_health_server
import duzman.runtime.run_scheduler
import fastapi, uvicorn, apscheduler, sqlalchemy, pydantic, httpx
print(f'verify_imports: duzman={v} ok')
"
}

check_no_cache_leak() {
  if [[ -e "$TARGET_DIR/.cache" || -L "$TARGET_DIR/.cache" ]]; then
    printf 'pip cache leaked into /opt/duzman/.cache (bootstrap_venv regression)\n' >&2
    exit 1
  fi
}

verify_health_smoke() {
  local attempt
  local port=8080
  local smoke_pid
  local smoke_ready=0

  if ss -tln "sport = :$port" | grep -q LISTEN; then
    echo "ERROR: 8080 already in use" >&2
    exit 1
  fi

  sudo -u "$SERVICE_USER" /usr/bin/timeout 6 \
    bash -c 'cd "$0" && exec /usr/bin/timeout 6 "$1" -m duzman.runtime.run_health_server' \
    "$TARGET_DIR" "$VENV_DIR/bin/python" &
  smoke_pid=$!

  for attempt in {1..10}; do
    if curl -fsS http://127.0.0.1:8080/health -o "$HEALTH_CHECK_FILE"; then
      smoke_ready=1
      break
    fi
    sleep 0.5
  done

  if ((smoke_ready == 0)); then
    wait "$smoke_pid" || true
    step_error "health smoke did not respond on 127.0.0.1:8080."
  fi

  grep -q '"status":"ok"' "$HEALTH_CHECK_FILE"
  wait "$smoke_pid" || true
}

parse_args() {
  while (($# > 0)); do
    case "$1" in
      --recreate)
        RECREATE=1
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

main() {
  parse_args "$@"
  run_step check_running_as_root_or_sudo check_running_as_root_or_sudo
  run_step check_target_exists check_target_exists
  run_step check_python_version check_python_version
  run_step check_target_freshness check_target_freshness
  run_step handle_existing_venv handle_existing_venv
  run_step create_venv create_venv
  run_step upgrade_pip upgrade_pip
  run_step install_package_editable install_package_editable
  run_step verify_imports verify_imports
  run_step check_no_cache_leak check_no_cache_leak
  run_step verify_health_smoke verify_health_smoke
  BOOTSTRAP_REACHED_SUCCESS=1
}

main "$@"
echo "bootstrap_venv: success"
