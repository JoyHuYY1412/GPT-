#!/bin/zsh
set -eu

APP_DIR="/Users/xintinghu/Library/CloudStorage/OneDrive-个人/USTC work/Xinting苦B带学生发bestpaper/Xinting_projects/论文推送/research_pulse"
PYTHON="/opt/homebrew/bin/python3"
VENV_ACTIVATE="$APP_DIR/.arxivreader/bin/activate"

cd "$APP_DIR"
mkdir -p logs

if [ -f "$VENV_ACTIVATE" ]; then
  source "$VENV_ACTIVATE"
  PYTHON="python"
fi

export RESEARCH_PULSE_HOST="127.0.0.1"
export RESEARCH_PULSE_PORT="8766"

exec "$PYTHON" "$APP_DIR/main.py"
