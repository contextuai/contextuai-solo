#!/usr/bin/env bash
# Start ContextuAI Solo backend
set -e

cd "$(dirname "$0")/backend"

# Create venv if not exists
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
else
    source .venv/bin/activate
fi

export CONTEXTUAI_MODE=desktop
export AGENT_LIBRARY_PATH="$(dirname "$0")/agent-library"

echo "Starting ContextuAI Solo backend on http://127.0.0.1:18741"
uvicorn app:app --host 127.0.0.1 --port 18741 --reload
