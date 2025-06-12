FROM node:20-alpine

WORKDIR /app

# Install system dependencies including X11 and a minimal desktop environment
RUN apk add --no-cache \
    python3 \
    py3-pip \
    build-base \
    python3-dev \
    xvfb \
    x11vnc \
    fluxbox \
    xterm \
    xorg-server \
    xf86-video-dummy \
    dbus \
    ttf-freefont \
    chromium \
    chromium-chromedriver \
    firefox \
    firefox-esr \
    shadow \
    xf86-input-evdev \
    curl

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh && \
    echo 'export PATH="/root/.cargo/bin:$PATH"' >> /root/.bashrc && \
    echo 'export PATH="/root/.cargo/bin:$PATH"' >> /root/.profile

# Copy extension files
COPY extension/ ./extension/
WORKDIR /app/extension
RUN npm install && npm run build

# Set up workflow environment
WORKDIR /app
COPY workflows/ ./workflows/
WORKDIR /app/workflows
RUN python3 -m venv .venv && \
    . .venv/bin/activate && \
    pip install --upgrade pip && \
    pip install -e . --no-deps && \
    cd /app && npx playwright install chromium

# Set up UI
WORKDIR /app
COPY ui/ ./ui/
WORKDIR /app/ui
RUN rm -rf node_modules package-lock.json && \
    npm install && \
    npm install @rollup/rollup-linux-x64-musl && \
    npm run build

# Create browser profile directories with correct permissions
RUN mkdir -p /root/.config/chromium \
    /root/.mozilla \
    /root/.cache/chromium \
    /root/.cache/mozilla \
    && chown -R root:root /root/.config \
    /root/.mozilla \
    /root/.cache

# Set environment variables
ENV NODE_ENV=production
ENV PORT=8000
ENV DISPLAY=:99
ENV DBUS_SESSION_BUS_ADDRESS=/dev/null

# Expose ports
EXPOSE 8000
EXPOSE 5900

# Start the application with Xvfb
CMD Xvfb :99 -screen 0 1024x768x24 -ac & \
    fluxbox & \
    x11vnc -display :99 -nopw -forever & \
    cd /app/workflows && . .venv/bin/activate && python cli.py launch-gui