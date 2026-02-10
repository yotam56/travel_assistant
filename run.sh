#!/usr/bin/env bash
set -e

API_URL="http://localhost:8000"

cleanup() {
    echo "Shutting down…"
    [ -n "$BACKEND_PID" ] && kill "$BACKEND_PID" 2>/dev/null
    [ -n "$STREAMLIT_PID" ] && kill "$STREAMLIT_PID" 2>/dev/null
    wait 2>/dev/null
}
trap cleanup EXIT

# Start the FastAPI backend
echo "Starting backend…"
uvicorn app.main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

# Wait for the backend to become healthy
echo "Waiting for backend health check…"
for i in $(seq 1 30); do
    if curl -sf "$API_URL/health" > /dev/null 2>&1; then
        echo "Backend is healthy."
        break
    fi
    if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
        echo "Backend process died." >&2
        exit 1
    fi
    sleep 1
done

if ! curl -sf "$API_URL/health" > /dev/null 2>&1; then
    echo "Backend did not become healthy in time." >&2
    exit 1
fi

# Start Streamlit
echo "Starting Streamlit…"
API_BASE_URL="$API_URL" streamlit run streamlit_app.py --server.port 8501 &
STREAMLIT_PID=$!

echo "Backend running on $API_URL"
echo "Streamlit running on http://localhost:8501"

wait
