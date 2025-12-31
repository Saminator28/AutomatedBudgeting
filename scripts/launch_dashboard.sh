#!/bin/bash
# Launch the Automated Budgeting Dashboard (backend + frontend)

set -e

WORKSPACE_DIR="$(dirname "$(dirname "$(dirname "$0")")")"
cd "$WORKSPACE_DIR"

# Start backend (FastAPI)
echo "Starting backend (FastAPI)..."
cd src/ui/backend
if ! pgrep -f "uvicorn main:app" > /dev/null; then
  nohup uvicorn main:app --reload > backend.log 2>&1 &
  BACKEND_PID=$!
  echo "Backend started with PID $BACKEND_PID (log: src/ui/backend/backend.log)"
else
  echo "Backend already running."
fi

# Start frontend (React)
echo "Starting frontend (React)..."
cd ../
if [ ! -d "node_modules" ]; then
  echo "Installing frontend dependencies..."
  npm install
fi
npm start
