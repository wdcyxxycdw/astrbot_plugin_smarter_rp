#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/setup_sillytavern.sh [--dir PATH] [--port PORT] [--skip-install] [--no-verify]

Sets up a local SillyTavern checkout with the AstrBot Smarter RP extension installed.

Options:
  --dir PATH       SillyTavern install directory.
                   Default: $HOME/.local/share/astrbot-smarter-rp/SillyTavern
  --port PORT      SillyTavern HTTP port. If omitted, the first free port from 8000-8099 is used.
  --skip-install   Skip npm install.
  --no-verify      Skip final file verification.
  -h, --help       Show this help.

Environment variables:
  SILLYTAVERN_DIR   Same as --dir.
  SILLYTAVERN_PORT  Same as --port.
  SILLYTAVERN_REF   Optional git branch/tag/commit to checkout after clone/update.
EOF
}

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
REPO_ROOT=$(cd -- "$SCRIPT_DIR/.." && pwd -P)
SILLYTAVERN_REPO="https://github.com/SillyTavern/SillyTavern.git"
SILLYTAVERN_DIR=${SILLYTAVERN_DIR:-"$HOME/.local/share/astrbot-smarter-rp/SillyTavern"}
PORT_WAS_SET=0
if [[ -n "${SILLYTAVERN_PORT+x}" ]]; then
  PORT_WAS_SET=1
fi
SILLYTAVERN_PORT=${SILLYTAVERN_PORT:-8000}
SKIP_INSTALL=0
VERIFY=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dir)
      SILLYTAVERN_DIR=${2:?--dir requires a path}
      shift 2
      ;;
    --port)
      SILLYTAVERN_PORT=${2:?--port requires a port}
      PORT_WAS_SET=1
      shift 2
      ;;
    --skip-install)
      SKIP_INSTALL=1
      shift
      ;;
    --no-verify)
      VERIFY=0
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

port_is_free() {
  python3 - "$1" <<'PY'
import socket
import sys
port = int(sys.argv[1])
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(('127.0.0.1', port))
    except OSError:
        sys.exit(1)
PY
}

choose_port() {
  if [[ "$PORT_WAS_SET" -eq 1 ]]; then
    if port_is_free "$SILLYTAVERN_PORT"; then
      printf '%s\n' "$SILLYTAVERN_PORT"
      return
    fi
    echo "Configured port $SILLYTAVERN_PORT is already in use on 127.0.0.1" >&2
    exit 1
  fi

  local port
  for port in $(seq "$SILLYTAVERN_PORT" 8099); do
    if port_is_free "$port"; then
      printf '%s\n' "$port"
      return
    fi
  done

  echo "No free SillyTavern port found in ${SILLYTAVERN_PORT}-8099" >&2
  exit 1
}

configure_sillytavern() {
  local config_path="$1"
  local port="$2"
  python3 - "$config_path" "$port" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
port = int(sys.argv[2])
lines = path.read_text(encoding='utf-8').splitlines()
out = []
in_browser_launch = False
browser_enabled_set = False
top_port_set = False

for line in lines:
    stripped = line.lstrip()
    indent = len(line) - len(stripped)

    if indent == 0 and stripped.startswith('browserLaunch:'):
        in_browser_launch = True
        browser_enabled_set = False
        out.append(line)
        continue

    if in_browser_launch and indent == 0 and stripped and not stripped.startswith('#'):
        if not browser_enabled_set:
            out.append('  enabled: false')
        in_browser_launch = False

    if in_browser_launch and indent == 2 and stripped.startswith('enabled:'):
        out.append('  enabled: false')
        browser_enabled_set = True
        continue

    if indent == 0 and stripped.startswith('port:'):
        out.append(f'port: {port}')
        top_port_set = True
        continue

    out.append(line)

if in_browser_launch and not browser_enabled_set:
    out.append('  enabled: false')
if not top_port_set:
    out.append(f'port: {port}')

path.write_text('\n'.join(out) + '\n', encoding='utf-8')
PY
}

require_command git
require_command node
require_command npm
require_command python3

SILLYTAVERN_PORT=$(choose_port)
EXTENSION_SOURCE="$REPO_ROOT/sillytavern_extension/astrbot-smarter-rp"
if [[ ! -f "$EXTENSION_SOURCE/manifest.json" ]]; then
  echo "Extension source not found: $EXTENSION_SOURCE" >&2
  exit 1
fi

mkdir -p "$(dirname -- "$SILLYTAVERN_DIR")"

if [[ -d "$SILLYTAVERN_DIR/.git" ]]; then
  echo "Updating SillyTavern in $SILLYTAVERN_DIR"
  git -C "$SILLYTAVERN_DIR" pull --ff-only
elif [[ -e "$SILLYTAVERN_DIR" ]]; then
  echo "Target exists but is not a git checkout: $SILLYTAVERN_DIR" >&2
  exit 1
else
  echo "Cloning SillyTavern into $SILLYTAVERN_DIR"
  git clone --depth 1 "$SILLYTAVERN_REPO" "$SILLYTAVERN_DIR"
fi

if [[ -n "${SILLYTAVERN_REF:-}" ]]; then
  echo "Checking out SillyTavern ref $SILLYTAVERN_REF"
  git -C "$SILLYTAVERN_DIR" fetch --tags
  git -C "$SILLYTAVERN_DIR" checkout "$SILLYTAVERN_REF"
fi

if [[ "$SKIP_INSTALL" -eq 0 ]]; then
  echo "Installing SillyTavern npm dependencies"
  npm --prefix "$SILLYTAVERN_DIR" install
fi

CONFIG_PATH="$SILLYTAVERN_DIR/config.yaml"
if [[ ! -f "$CONFIG_PATH" ]]; then
  cp "$SILLYTAVERN_DIR/default/config.yaml" "$CONFIG_PATH"
fi
configure_sillytavern "$CONFIG_PATH" "$SILLYTAVERN_PORT"

EXTENSIONS_DIR="$SILLYTAVERN_DIR/public/scripts/extensions/third-party"
EXTENSION_TARGET="$EXTENSIONS_DIR/astrbot-smarter-rp"
EXTENSION_TMP="$EXTENSION_TARGET.tmp.$$"
mkdir -p "$EXTENSIONS_DIR"
rm -rf "$EXTENSION_TMP"
cp -R "$EXTENSION_SOURCE" "$EXTENSION_TMP"
rm -rf "$EXTENSION_TARGET"
mv "$EXTENSION_TMP" "$EXTENSION_TARGET"

if [[ "$VERIFY" -eq 1 ]]; then
  test -f "$SILLYTAVERN_DIR/package.json"
  test -f "$CONFIG_PATH"
  test -f "$EXTENSION_TARGET/manifest.json"
  test -f "$EXTENSION_TARGET/index.js"
  test -d "$SILLYTAVERN_DIR/node_modules"
fi

cat <<EOF
SillyTavern setup complete.

Directory: $SILLYTAVERN_DIR
Port: $SILLYTAVERN_PORT
Extension: $EXTENSION_TARGET

Start SillyTavern with:
  cd "$SILLYTAVERN_DIR" && npm start

Open:
  http://127.0.0.1:$SILLYTAVERN_PORT/

AstrBot bridge URL for the extension:
  ws://127.0.0.1:8008/ws

The bridge is unauthenticated in this version; keep it on localhost only.
EOF
