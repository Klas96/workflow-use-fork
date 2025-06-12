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
    curl \
    # Add dependencies for playwright
    libstdc++ \
    libgcc \
    libc6-compat \
    nss \
    freetype \
    freetype-dev \
    harfbuzz \
    ca-certificates \
    ttf-liberation \
    fontconfig \
    dbus-libs \
    expat \
    libx11 \
    libxcomposite \
    libxdamage \
    libxext \
    libxfixes \
    libxrandr \
    libxrender \
    libxscrnsaver \
    libxtst \
    alsa-lib \
    at-spi2-core \
    cairo \
    cups-libs \
    gdk-pixbuf \
    glib \
    gtk+3.0 \
    libdrm \
    mesa \
    nspr \
    pango \
    pango-dev \
    pixman \
    pciutils-libs \
    udev \
    xdg-utils \
    zlib

# Copy extension files
COPY extension/ ./extension/
WORKDIR /app/extension
RUN npm install && npm run build

# Set up workflow environment
WORKDIR /app
COPY workflows/ ./workflows/
WORKDIR /app/workflows

# Create virtual environment with specific Python version
RUN python3 -m venv .venv && \
    /app/workflows/.venv/bin/pip install --upgrade pip setuptools wheel

# Install packages with specific versions
RUN /app/workflows/.venv/bin/pip install -v \
    typer \
    browser-use \
    playwright-python==1.40.0 \
    patchright==1.52.4 \
    -e . --no-deps
RUN cd /app && npx playwright install chromium

# Set up UI
WORKDIR /app
COPY ui/package.json ui/package-lock.json* ./ui/
WORKDIR /app/ui
RUN npm install && npm install @rollup/rollup-linux-x64-musl
COPY ui/ ./
RUN npm run build

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
CMD ["/bin/sh", "-c", "Xvfb :99 -screen 0 1024x768x24 -ac & sleep 2 && fluxbox & sleep 2 && x11vnc -display :99 -nopw -forever & sleep 2 && cd /app/workflows && . .venv/bin/activate && python cli.py launch-gui"]