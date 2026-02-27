#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

if [ ! -d ".venv" ]; then
  echo "Creating virtual environment..."
  python3 -m venv .venv
  .venv/bin/pip install -r requirements.txt
fi

echo "Starting Finance Signal Pro → http://localhost:8501"
PYTHONPATH="$DIR" .venv/bin/streamlit run src/app.py \
  --browser.gatherUsageStats false \
  --server.headless false
