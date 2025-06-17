# Stage 1: Build the frontend
FROM node:20-slim AS frontend-build
WORKDIR /app/ui
COPY ui/ ./
RUN rm -rf node_modules package-lock.json && npm install && npm install @rollup/rollup-linux-x64-gnu && npm run build

# Stage 2: Main app with minimal GUI and Python
FROM python:3.12-slim as stage-1

WORKDIR /app

# Install system dependencies including X11 and browser dependencies
RUN apt-get update && apt-get install -y \
    xvfb \
    fluxbox \
    x11vnc \
    xterm \
    wget \
    gnupg \
    net-tools \
    libglib2.0-0 \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxcb1 \
    libxkbcommon0 \
    libx11-6 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    libatspi2.0-0 \
    libxshmfence1 \
    libxss1 \
    libxinerama1 \
    libxrender1 \
    libxcursor1 \
    libxi6 \
    libxtst6 \
    libgtk-3-0 \
    libgdk-pixbuf2.0-0 \
    libwayland-client0 \
    libwayland-cursor0 \
    libwayland-egl1 \
    libexpat1 \
    libfontconfig1 \
    libfreetype6 \
    libpangoft2-1.0-0 \
    libpangocairo-1.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Copy extension and workflows
COPY extension/ ./extension/
COPY workflows/ ./workflows/

WORKDIR /app/workflows

# Create and activate virtual environment
RUN python3 -m venv .venv && \
    . .venv/bin/activate && \
    pip install -v -e . && \
    pip install -v typer && \
    pip install -v browser-use && \
    pip install requests && \
    pip install -v playwright && \
    pip install -v patchright==1.52.4 && \
    pip install fastmcp && \
    pip install fastapi uvicorn && \
    pip install python-multipart

# Clean up any old browser installs before installing Chromium
RUN . .venv/bin/activate && rm -rf /app/workflows/.venv/lib/python3.12/site-packages/playwright/driver/package/.local-browsers || true
# Ensure browser download is not skipped and install Chromium
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=0
RUN . .venv/bin/activate && python -m playwright install chromium

WORKDIR /app

# Copy frontend build
COPY --from=frontend-build /app/ui/dist ./ui/dist

# Create startup script
RUN echo '#!/bin/bash\n\
if [ ! -d "/app/workflows/.venv" ]; then\n\
    echo "Virtual environment not found. Please mount the workflows directory."\n\
    exit 1\n\
fi\n\
\n\
# Create logs directory\n\
mkdir -p /app/workflows/tmp/logs\n\
\n\
# Clean up any existing X server lock files\n\
rm -f /tmp/.X99-lock\n\
rm -f /tmp/.X11-unix/X99\n\
\n\
# Start Xvfb with proper configuration\n\
Xvfb :99 -screen 0 1920x1080x24 -ac +extension GLX +render -noreset &\n\
\n\
# Wait for X server to be ready\n\
for i in $(seq 1 10); do\n\
    if xdpyinfo -display :99 >/dev/null 2>&1; then\n\
        break\n\
    fi\n\
    echo "Waiting for X server to be ready... ($i/10)"\n\
    sleep 1\n\
done\n\
\n\
# Start window manager\n\
fluxbox &\n\
sleep 2\n\
\n\
# Start VNC server with proper configuration\n\
x11vnc -display :99 -forever -shared -nopw -noxrecord -noxfixes -noxdamage &\n\
\n\
# Wait for VNC server to be ready\n\
for i in $(seq 1 10); do\n\
    if netstat -tuln | grep -q ":5900 "; then\n\
        break\n\
    fi\n\
    echo "Waiting for VNC server to be ready... ($i/10)"\n\
    sleep 1\n\
done\n\
\n\
# Start the backend API\n\
cd /app/workflows && . .venv/bin/activate && python -m uvicorn backend.api:app --host 0.0.0.0 --port 8002 --no-access-log &\n\
\n\
# Start the frontend\n\
cd /app && python -m http.server 8000 &\n\
\n\
# Start xterm with process monitoring\n\
xterm -geometry 100x30+0+400 -e "while true; do clear; ps aux | grep -E \"python|uvicorn|playwright|x11vnc|Xvfb\" | grep -v grep; sleep 2; done" &\n\
\n\
# Keep container running\n\
tail -f /dev/null' > /app/start.sh && chmod +x /app/start.sh

# Set environment variables
ENV DISPLAY=:99
ENV PYTHONUNBUFFERED=1
ENV PLAYWRIGHT_BROWSER_ARGS="--no-sandbox --disable-setuid-sandbox --disable-dev-shm-usage --disable-accelerated-2d-canvas --disable-gpu --window-size=1920,1080 --start-maximized --disable-extensions --disable-default-apps --disable-popup-blocking --disable-notifications --disable-infobars --disable-web-security --allow-running-insecure-content --disable-features=IsolateOrigins,site-per-process"
ENV PYTHONPATH=/app/workflows:$PYTHONPATH

# Expose ports
EXPOSE 5900 8002 8000

# Start the application
CMD ["/app/start.sh"]