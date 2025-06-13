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
RUN . .venv/bin/activate && pip install fastapi

# Copy built frontend from Stage 1
WORKDIR /app
COPY --from=frontend-build /app/ui/dist ./ui/dist

# Set environment variables
ENV NODE_ENV=production
ENV PORT=8000
ENV DISPLAY=:99
ENV DBUS_SESSION_BUS_ADDRESS=/dev/null

# Expose ports
EXPOSE 8000
EXPOSE 5900

# Start the application with Xvfb and minimal GUI
CMD ["/bin/sh", "-c", "Xvfb :99 -screen 0 1024x768x24 -ac & sleep 2 && fluxbox & sleep 2 && x11vnc -display :99 -nopw -forever & sleep 2 && cd /app/workflows && . .venv/bin/activate && python cli.py launch-gui"]