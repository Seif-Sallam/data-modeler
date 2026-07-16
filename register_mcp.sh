#!/usr/bin/env bash
# Register the Data Modeler MCP server with Claude Code.
#
# Usage:
#   ./register_mcp.sh            # register at user scope (available in all projects)
#   ./register_mcp.sh project    # register at project scope (this repo only)
#
# The app must be running (./run.sh) for the tools to work.

set -euo pipefail
cd "$(dirname "$0")"
DIR="$(pwd)"
SCRIPT="$DIR/mcp_server.py"
URL="${DATA_MODELER_URL:-http://127.0.0.1:8001}"
SCOPE="${1:-user}"

if ! command -v claude >/dev/null 2>&1; then
  echo "The 'claude' CLI was not found on PATH."
  echo "A project-scoped .mcp.json already exists in this repo — open the project in"
  echo "Claude Code and approve the 'data-modeler' server when prompted."
  exit 1
fi

# Remove any prior registration at this scope so re-running is idempotent.
claude mcp remove data-modeler --scope "$SCOPE" >/dev/null 2>&1 || true

claude mcp add-json data-modeler --scope "$SCOPE" "$(cat <<JSON
{
  "command": "uv",
  "args": ["run", "--with", "mcp", "--with", "httpx", "python", "$SCRIPT"],
  "env": { "DATA_MODELER_URL": "$URL" }
}
JSON
)"

echo "Registered 'data-modeler' at $SCOPE scope -> $URL"
echo "Restart Claude Code to pick it up. Start the app first with ./run.sh."
