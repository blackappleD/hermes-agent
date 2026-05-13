#!/usr/bin/env bash
# Mirror a Windows checkout into WSL's native filesystem, then run the local
# installer from that mirrored source tree.

set -euo pipefail

SRC_DIR="${HERMES_WSL_SOURCE_DIR:-/mnt/d/workspace/hermes-agent}"
DEST_DIR="${HERMES_WSL_TEST_DIR:-/src/hermes-agent}"
INSTALL_ARGS=()

log_info() {
    printf '→ %s\n' "$1"
}

log_success() {
    printf '✓ %s\n' "$1"
}

log_error() {
    printf '✗ %s\n' "$1" >&2
}

usage() {
    cat <<'EOF'
Usage: install-wsl-test.sh [OPTIONS] [-- INSTALL_ARGS...]

Copies a Windows checkout into WSL native storage and runs:
  bash <dest>/scripts/install.sh --local --dir <dest>

Options:
  --src PATH       Source checkout (default: /mnt/d/workspace/hermes-agent)
  --dest PATH      WSL test checkout (default: /src/hermes-agent)
  -h, --help       Show this help

Environment:
  HERMES_WSL_SOURCE_DIR  Override source checkout
  HERMES_WSL_TEST_DIR    Override destination checkout

Examples:
  bash scripts/install-wsl-test.sh
  bash scripts/install-wsl-test.sh -- --skip-setup
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --src)
            SRC_DIR="$2"
            shift 2
            ;;
        --dest)
            DEST_DIR="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        --)
            shift
            INSTALL_ARGS+=("$@")
            break
            ;;
        *)
            INSTALL_ARGS+=("$1")
            shift
            ;;
    esac
done

case "$DEST_DIR" in
    ""|"/"|"/src")
        log_error "Refusing unsafe destination: ${DEST_DIR:-<empty>}"
        exit 1
        ;;
esac

case "$DEST_DIR" in
    */hermes-agent|*/hermes-agent/)
        ;;
    *)
        log_error "Destination must end with /hermes-agent for this test installer: $DEST_DIR"
        exit 1
        ;;
esac

if [ ! -d "$SRC_DIR" ]; then
    log_error "Source checkout does not exist: $SRC_DIR"
    exit 1
fi

if [ ! -f "$SRC_DIR/pyproject.toml" ]; then
    log_error "Source does not look like hermes-agent: $SRC_DIR"
    log_error "Expected pyproject.toml"
    exit 1
fi

prepare_destination() {
    local parent
    parent="$(dirname "$DEST_DIR")"

    if mkdir -p "$parent" 2>/dev/null; then
        :
    elif command -v sudo >/dev/null 2>&1; then
        sudo mkdir -p "$parent"
        sudo chown "$(id -u):$(id -g)" "$parent"
    else
        log_error "Cannot create destination parent: $parent"
        exit 1
    fi

    if [ -e "$DEST_DIR" ] && [ ! -w "$DEST_DIR" ] && command -v sudo >/dev/null 2>&1; then
        sudo chown -R "$(id -u):$(id -g)" "$DEST_DIR"
    fi

    mkdir -p "$DEST_DIR"
}

sync_source() {
    local excludes=(
        "--exclude=.git/"
        "--exclude=.omc/"
        "--exclude=.omx/"
        "--exclude=.obsidian/"
        "--exclude=venv/"
        "--exclude=.venv/"
        "--exclude=node_modules/"
        "--exclude=__pycache__/"
        "--exclude=.pytest_cache/"
        "--exclude=.mypy_cache/"
        "--exclude=.ruff_cache/"
        "--exclude=build/"
        "--exclude=dist/"
        "--exclude=*.egg-info/"
    )

    if command -v rsync >/dev/null 2>&1; then
        rsync -a --delete "${excludes[@]}" "$SRC_DIR"/ "$DEST_DIR"/
        return 0
    fi

    log_info "rsync not found; using tar copy fallback"
    log_info "Tar fallback preserves existing venv/node_modules but does not delete stale files."
    log_info "Install rsync for exact mirroring: apt-get update && apt-get install -y rsync"
    mkdir -p "$DEST_DIR"
    (
        cd "$SRC_DIR"
        tar \
            --exclude='.git' \
            --exclude='.omc' \
            --exclude='.omx' \
            --exclude='.obsidian' \
            --exclude='venv' \
            --exclude='.venv' \
            --exclude='node_modules' \
            --exclude='__pycache__' \
            --exclude='.pytest_cache' \
            --exclude='.mypy_cache' \
            --exclude='.ruff_cache' \
            --exclude='build' \
            --exclude='dist' \
            --exclude='*.egg-info' \
            -cf - .
    ) | (
        cd "$DEST_DIR"
        tar -xf -
    )
}

log_info "Source: $SRC_DIR"
log_info "Destination: $DEST_DIR"

prepare_destination
sync_source

# Normalize shell script line endings after copying from a Windows-mounted tree.
find "$DEST_DIR" \
    \( -path "$DEST_DIR/venv" -o -path "$DEST_DIR/.venv" -o -path "$DEST_DIR/node_modules" -o -path "$DEST_DIR/ui-tui/node_modules" \) -prune \
    -o -name '*.sh' -type f -print0 | xargs -0 sed -i 's/\r$//'
chmod +x "$DEST_DIR/scripts/install.sh"

log_success "Source copied into WSL native filesystem"
exec bash "$DEST_DIR/scripts/install.sh" --local --dir "$DEST_DIR" "${INSTALL_ARGS[@]}"
