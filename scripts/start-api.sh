#!/usr/bin/env sh
# Start the bournemouth API server.
#
# Prerequisites:
#   - uv CLI must be installed and available on PATH
#   - granian Python package must be installed
#
# Usage:
#   scripts/start-api.sh [granian options]
#   scripts/start-api.sh --reload
#   scripts/start-api.sh --host 0.0.0.0 --port 8000
#
# The uv command executes the granian server with the application's factory
# function. Extra arguments are passed directly to granian.

set -eu
SCRIPT_DIR="$(cd "$(dirname -- "$0")" && pwd)"
cd "$SCRIPT_DIR/.."
command -v uv >/dev/null 2>&1 || {
    echo "Error: uv CLI not found" >&2
    exit 1
}
exec uv run granian --factory bournemouth.app:create_app "$@"
