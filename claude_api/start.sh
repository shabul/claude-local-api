#!/usr/bin/env bash
# Start the claude_api Unix socket server.
# Env vars:
#   CLAUDE_API_MODEL     — default model  (default: haiku)
#   CLAUDE_API_POOL_SIZE — warm workers   (default: 3)
#
# Examples:
#   ./claude_api/start.sh
#   CLAUDE_API_MODEL=sonnet CLAUDE_API_POOL_SIZE=2 ./claude_api/start.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"

exec python -m claude_api.server
