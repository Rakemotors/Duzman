#!/usr/bin/env bash
# Manual Duzman deployment helper for reviewed repository trees.

set -u
set -o pipefail

readonly EXIT_USAGE=1
readonly EXIT_PREFLIGHT=2
readonly EXIT_RSYNC=3
readonly EXIT_CHOWN=4
readonly DEPLOY_OWNER="duzman:duzman"

MODE="DRY-RUN"
SOURCE=""
TARGET="/opt/duzman"
APPLY_REQUESTED=0
DRY_RUN_REQUESTED=0

EXCLUDES=(
  ".git/"
  ".venv/"
  "__pycache__/"
  ".pytest_cache/"
  ".mypy_cache/"
  ".ruff_cache/"
  ".env"
  ".env.*"
  "logs/"
  "*.pyc"
)

usage() {
  cat <<'EOF'
Usage: deploy/deploy.sh [--apply | --dry-run] [--source SRC] [--target TGT]

Options:
  --apply       Run rsync and ownership changes against the target.
  --dry-run     Show the rsync plan without modifying the target.
  --source SRC  Source repository directory. Defaults to the repo root.
  --target TGT  Target directory. Defaults to /opt/duzman.
  -h, --help    Show this help.
EOF
}

usage_error() {
  printf 'Usage error: %s\n' "$1" >&2
  usage >&2
  exit "$EXIT_USAGE"
}

preflight_error() {
  printf 'Pre-flight failed: %s\n' "$1" >&2
  exit "$EXIT_PREFLIGHT"
}

print_summary() {
  local exclude

  printf 'Duzman deploy plan\n'
  printf '  mode: %s\n' "$MODE"
  printf '  source: %s\n' "$SOURCE"
  printf '  target: %s\n' "$TARGET"
  printf '  excludes:\n'
  for exclude in "${EXCLUDES[@]}"; do
    printf '    - %s\n' "$exclude"
  done
}

chown_deployed_tree() {
  find "$TARGET" \
    \( -name ".env" -o -name ".env.*" \) -prune -o \
    -exec chown "$DEPLOY_OWNER" -- {} + ||
    {
      printf 'Ownership update failed after rsync: %s\n' "$TARGET" >&2
      exit "$EXIT_CHOWN"
    }
}

check_env_file() {
  local env_file="${TARGET%/}/.env"
  local env_mode=""
  local env_owner=""

  printf 'Post-check .env: %s\n' "$env_file"
  if [[ ! -e "$env_file" ]]; then
    printf 'WARNING: .env is missing.\n' >&2
    return
  fi

  printf '.env exists.\n'
  if [[ -s "$env_file" ]]; then
    printf '.env is non-empty.\n'
  else
    printf 'WARNING: .env is empty.\n' >&2
  fi

  if env_mode="$(stat -c '%a' -- "$env_file" 2>/dev/null)"; then
    if [[ "$env_mode" == "600" ]]; then
      printf '.env permissions are 600.\n'
    else
      printf 'WARNING: .env permissions are %s; expected 600.\n' "$env_mode" >&2
    fi
  else
    printf 'WARNING: could not inspect .env permissions.\n' >&2
  fi

  if env_owner="$(stat -c '%U:%G' -- "$env_file" 2>/dev/null)"; then
    if [[ "$env_owner" == "$DEPLOY_OWNER" ]]; then
      printf '.env owner is %s.\n' "$DEPLOY_OWNER"
    else
      printf 'WARNING: .env owner is %s; expected %s.\n' "$env_owner" "$DEPLOY_OWNER" >&2
    fi
  else
    printf 'WARNING: could not inspect .env owner.\n' >&2
  fi
}

while (($# > 0)); do
  case "$1" in
    --apply)
      APPLY_REQUESTED=1
      shift
      ;;
    --dry-run)
      DRY_RUN_REQUESTED=1
      shift
      ;;
    --source)
      (($# >= 2)) || usage_error "--source requires a directory."
      SOURCE="$2"
      shift 2
      ;;
    --target)
      (($# >= 2)) || usage_error "--target requires a directory."
      TARGET="$2"
      shift 2
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      usage_error "unknown argument: $1"
      ;;
  esac
done

if ((APPLY_REQUESTED == 1 && DRY_RUN_REQUESTED == 1)); then
  usage_error "--apply and --dry-run cannot be used together."
fi

if ((APPLY_REQUESTED == 1)); then
  MODE="APPLY"
fi

if [[ -z "$SOURCE" ]]; then
  SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)" ||
    preflight_error "could not resolve deploy script directory."
  SOURCE="$(cd -- "$SCRIPT_DIR/.." && pwd -P)" ||
    preflight_error "could not resolve repository root."
fi

[[ -n "$SOURCE" ]] || preflight_error "source directory must not be empty."
[[ -n "$TARGET" ]] || preflight_error "target directory must not be empty."
[[ -d "$SOURCE" ]] || preflight_error "source directory does not exist: $SOURCE"
[[ -r "$SOURCE" ]] || preflight_error "source directory is not readable: $SOURCE"
[[ -f "${SOURCE%/}/pyproject.toml" ]] ||
  preflight_error "source does not look like a Duzman repo; pyproject.toml is missing: $SOURCE"
command -v rsync >/dev/null 2>&1 || preflight_error "rsync is not available."

if ((APPLY_REQUESTED == 1 && EUID != 0)); then
  preflight_error "--apply must run as root before rsync can change ownership."
fi

if [[ -e "$TARGET" && ! -d "$TARGET" ]]; then
  preflight_error "target exists but is not a directory: $TARGET"
fi

if [[ ! -d "$TARGET" ]]; then
  if ((APPLY_REQUESTED == 1)); then
    mkdir -p -- "$TARGET" ||
      preflight_error "target directory could not be created: $TARGET"
    chown "$DEPLOY_OWNER" -- "$TARGET" ||
      {
        printf 'Ownership update failed for new target: %s\n' "$TARGET" >&2
        exit "$EXIT_CHOWN"
      }
  else
    printf 'Info: target %s would be created.\n' "$TARGET"
  fi
fi

print_summary

RSYNC_ARGS=(-a --delete)
if ((APPLY_REQUESTED == 0)); then
  RSYNC_ARGS+=(--dry-run -v)
fi
for exclude in "${EXCLUDES[@]}"; do
  RSYNC_ARGS+=(--exclude "$exclude")
done

rsync "${RSYNC_ARGS[@]}" -- "${SOURCE%/}/" "${TARGET%/}/" ||
  {
    printf 'rsync failed.\n' >&2
    exit "$EXIT_RSYNC"
  }

if ((APPLY_REQUESTED == 1)); then
  chown_deployed_tree
fi

check_env_file
exit 0
