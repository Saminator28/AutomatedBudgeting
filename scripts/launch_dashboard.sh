#!/bin/bash
# Launch the Automated Budgeting Dashboard (backend + frontend)

set -e

# Get the workspace directory (parent of scripts/)
WORKSPACE_DIR="$(cd "$(dirname "$(dirname "$0")")" && pwd)"
cd "$WORKSPACE_DIR"

echo "Workspace: $WORKSPACE_DIR"

# Activate Python virtual environment
if [ -d "myenv" ]; then
  source myenv/bin/activate
  echo "✓ Python virtual environment activated"
else
  echo "Warning: Virtual environment 'myenv' not found"
fi

# Start backend (FastAPI)
echo "Starting backend (FastAPI)..."
cd src/ui/backend
if ! pgrep -f "uvicorn main:app" > /dev/null; then
  nohup python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000 > backend.log 2>&1 &
  BACKEND_PID=$!
  sleep 2
  if ps -p $BACKEND_PID > /dev/null; then
    echo "✓ Backend started with PID $BACKEND_PID (log: src/ui/backend/backend.log)"
  else
    echo "✗ Backend failed to start. Check src/ui/backend/backend.log"
    exit 1
  fi
else
  echo "✓ Backend already running."
fi

# Return to workspace root for frontend
cd "$WORKSPACE_DIR/src/ui"

# Start frontend (React)
echo "Starting frontend (React)..."
if [ ! -d "node_modules" ]; then
  echo "Installing frontend dependencies..."
  npm install
fi
npm start
