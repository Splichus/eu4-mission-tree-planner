#!/usr/bin/env bash
# Serve the EU4 Mission-Tree Race Planner locally.
cd "$(dirname "$0")"
PORT="${1:-8731}"
echo "Serving EU4 planner at http://localhost:$PORT/  (Ctrl+C to stop)"
python3 -m http.server "$PORT"
