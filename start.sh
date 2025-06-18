#!/bin/bash
if [ ! -d "/app/workflows" ]; then
    echo "Workflows directory not found. Please mount the workflows directory."
    exit 1
fi

# Load environment variables from .env file
set -a
source /app/workflows/.env
set +a

# Create logs directory
mkdir -p /app/workflows/tmp/logs

# Clean up any existing X server lock files
rm -f /tmp/.X99-lock
rm -f /tmp/.X11-unix/X99

# Start Xvfb with proper configuration
Xvfb :99 -screen 0 1920x1080x24 -ac +extension GLX +render -noreset &

# Wait for X server to be ready
for i in $(seq 1 10); do
    if xdpyinfo -display :99 >/dev/null 2>&1; then
        break
    fi
    echo "Waiting for X server to be ready... ($i/10)"
    sleep 1
done

# Start window manager
fluxbox &
sleep 2

# Start VNC server with proper configuration
x11vnc -display :99 -forever -shared -nopw -noxrecord -noxfixes -noxdamage &

# Wait for VNC server to be ready
for i in $(seq 1 10); do
    if netstat -tuln | grep -q ":5900 "; then
        break
    fi
    echo "Waiting for VNC server to be ready... ($i/10)"
    sleep 1
done

# Start the backend API
cd /app/workflows && python -m uvicorn backend.api:app --host 0.0.0.0 --port 8002 --no-access-log &

# Start the frontend
cd /app && python -m http.server 8000 &

# Start xterm with process monitoring
xterm -geometry 100x30+0+400 -e "while true; do clear; ps aux | grep -E \"python|uvicorn|playwright|x11vnc|Xvfb\" | grep -v grep; sleep 2; done" &

# Keep container running
tail -f /dev/null 