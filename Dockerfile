# Stage 1: Build the frontend
FROM node:20-slim AS frontend-build
WORKDIR /app/ui
COPY ui/ ./
RUN rm -rf node_modules package-lock.json && npm install && npm install @rollup/rollup-linux-x64-gnu && npm run build

# Stage 2: Main app with minimal GUI and Python
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies for GUI, browsers, and Playwright
RUN apt-get update && apt-get install -y \
    xvfb \
    fluxbox \
    x11vnc \
    xterm \
    fonts-freefont-ttf \
    curl \
    chromium \
    chromium-driver \
    firefox-esr \
    build-essential \
    python3-dev \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Copy extension and workflows
COPY extension/ ./extension/
COPY workflows/ ./workflows/

# Set up Python virtual environment
WORKDIR /app/workflows
RUN python3 -m venv .venv && \
    . .venv/bin/activate && \
    pip install --upgrade pip setuptools wheel

# Install Python dependencies
RUN . .venv/bin/activate && pip install -v typer
RUN . .venv/bin/activate && pip install -v browser-use
RUN . .venv/bin/activate && pip install requests
RUN . .venv/bin/activate && pip install -v playwright
RUN . .venv/bin/activate && pip install -v patchright==1.52.4
RUN . .venv/bin/activate && pip install -v -e . --no-deps
RUN . .venv/bin/activate && python -m playwright install chromium
RUN . .venv/bin/activate && pip install fastmcp
RUN . .venv/bin/activate && pip install fastapi uvicorn
RUN . .venv/bin/activate && pip install python-multipart

# Copy built frontend from Stage 1
WORKDIR /app
COPY --from=frontend-build /app/ui/dist ./ui/dist

# Set environment variables
ENV NODE_ENV=production
ENV PORT=8000
ENV DISPLAY=:99
ENV DBUS_SESSION_BUS_ADDRESS=/dev/null

# Create a startup script
RUN echo '#!/bin/bash\n\
if [ ! -d "/app/workflows/.venv" ]; then\n\
    echo "Creating virtual environment..."\n\
    python3 -m venv /app/workflows/.venv\n\
    . /app/workflows/.venv/bin/activate\n\
    pip install -v typer\n\
    pip install -v browser-use\n\
    pip install requests\n\
    pip install -v playwright\n\
    pip install -v patchright\n\
    pip install -v -e . --no-deps\n\
    python -m playwright install\n\
    pip install fastmcp\n\
    pip install fastapi uvicorn\n\
    pip install python-multipart\n\
fi\n\
\n\
# Start Xvfb with a larger screen and wait for it to be ready\n\
Xvfb :99 -screen 0 1024x768x24 -ac &\n\
sleep 2\n\
\n\
# Set display environment variable\n\
export DISPLAY=:99\n\
\n\
# Start fluxbox window manager\n\
fluxbox &\n\
sleep 1\n\
\n\
# Start x11vnc\n\
x11vnc -display :99 -nopw -forever &\n\
\n\
# Start the frontend server\n\
cd /app\n\
python3 -m http.server 8000 --directory ui/dist &\n\
\n\
# Start the API server\n\
cd /app/workflows\n\
export PYTHONPATH=/app/workflows\n\
. .venv/bin/activate\n\
uvicorn backend.api:app --host 0.0.0.0 --port 8002 --no-access-log\n\
' > /app/start.sh && chmod +x /app/start.sh

# Expose ports
EXPOSE 8000
EXPOSE 8002
EXPOSE 5900

# Start the application with Xvfb and minimal GUI
CMD ["/app/start.sh"]