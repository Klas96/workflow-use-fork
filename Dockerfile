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
    curl \
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
    sudo \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user
RUN useradd -m -d /home/chrome -s /bin/bash chrome \
    && usermod -aG sudo chrome \
    && echo "chrome ALL=(ALL) NOPASSWD: ALL" >> /etc/sudoers

# Install Google Chrome
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# Copy extension and workflows
COPY extension/ ./extension/
COPY workflows/ ./workflows/
COPY workflows/.env ./workflows/.env
COPY start.sh /app/start.sh

WORKDIR /app/workflows

# Install Python packages globally
RUN pip install -e . && \
    pip install typer && \
    pip install "playwright==1.39" && \
    pip install "browser-use>=0.1.0" && \
    pip install requests && \
    pip install patchright==1.52.4 && \
    pip install fastmcp && \
    pip install fastapi uvicorn && \
    pip install python-multipart && \
    pip install python-dotenv && \
    python -m playwright install-deps chromium && \
    python -m playwright install chromium

# Set up Chrome for Playwright (using system Chrome)
RUN mkdir -p /home/chrome/.cache/ms-playwright && \
    chown -R chrome:chrome /home/chrome/.cache && \
    sudo -u chrome mkdir -p /home/chrome/.cache/ms-playwright/chromium-1060/chrome-linux && \
    sudo -u chrome ln -s /usr/bin/google-chrome-stable /home/chrome/.cache/ms-playwright/chromium-1060/chrome-linux/chrome

# Set environment variables
ENV DISPLAY=:99
ENV PYTHONUNBUFFERED=1
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
ENV PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/google-chrome-stable
ENV PLAYWRIGHT_CHROMIUM_SANDBOX=0
ENV PLAYWRIGHT_BROWSERS_PATH=/home/chrome/.cache/ms-playwright
ENV PLAYWRIGHT_BROWSER_ARGS="--no-sandbox"
ENV PYTHONPATH=/app/workflows:$PYTHONPATH

WORKDIR /app

# Copy frontend build
COPY --from=frontend-build /app/ui/dist ./ui/dist

RUN chmod +x /app/start.sh && \
    # Fix permissions for the chrome user
    chown -R chrome:chrome /app && \
    chown -R chrome:chrome /home/chrome && \
    chmod -R 755 /app

# Switch to chrome user
USER chrome

# Expose ports
EXPOSE 5900 8002 8000

# Start the application
CMD ["/app/start.sh"]