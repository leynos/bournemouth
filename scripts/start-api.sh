#!/usr/bin/env sh
# Start the bournemouth API server using uv and granian.
# Usage: scripts/start-api.sh [granian options]
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/.."
uv run granian --factory bournemouth.app:create_app "$@"
