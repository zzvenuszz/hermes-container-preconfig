#!/usr/bin/env bash
set -euo pipefail

export HERMES_HOME="${HERMES_HOME:-/data/hermes}"
export DEBIAN_FRONTEND=noninteractive
export HERMES_NONINTERACTIVE=1
export HERMES_CONTAINER=1
export PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1

HERMES_DIR="$HERMES_HOME/hermes-agent"
VENV_BIN="$HERMES_DIR/venv/bin"
HERMES_BIN="$VENV_BIN/hermes"

export PATH="/opt/node/bin:$HERMES_HOME/bin:$HERMES_HOME/node/bin:$VENV_BIN:/root/.local/bin:/usr/local/bin:/usr/bin:/bin"
export TERM="${TERM:-xterm-256color}"

log() { echo "[entrypoint] $*"; }
log_warn() { echo "[entrypoint] WARN: $*"; }

mkdir -p "$HERMES_HOME"

# Copy config.txt
CONFIG_TXT="/app/config.txt"
if [ -f "$CONFIG_TXT" ]; then
    cp -f "$CONFIG_TXT" "$HERMES_HOME/config.txt" 2>/dev/null || true
fi

# --- Restore from fallback if volume mount wiped /data — runs IMMEDIATELY (no delay) ---
if [ ! -x "$HERMES_BIN" ] && [ -d "/app/.hermes-fallback/venv/bin" ]; then
    log "Restoring Hermes from /app/.hermes-fallback..."
    cp -r /app/.hermes-fallback/* "$HERMES_HOME/" 2>/dev/null || true
    mkdir -p "$HERMES_DIR"
    cp -r /app/.hermes-fallback/hermes-agent/* "$HERMES_DIR/" 2>/dev/null || true
    chmod -R 755 "$HERMES_DIR/venv/bin" 2>/dev/null || true
    log "Fallback restore done"
fi
APP_PID=$!
log "Web server started (PID $APP_PID)"

# --- Background: install Hermes async ---
(
    sleep 5  # Let web server bind first
    
    if [ ! -x "$HERMES_BIN" ]; then
        log "Installing Hermes via pip (background)..."
        mkdir -p "$HERMES_DIR"
        git clone --depth=1 https://github.com/NousResearch/hermes-agent.git "$HERMES_DIR" 2>/dev/null || true
        
        # Fix broken venv if exists
        if [ -d "$HERMES_DIR/venv" ]; then
            rm -rf "$HERMES_DIR/venv"
        fi
        python3 -m venv "$HERMES_DIR/venv"
        
        # Reinstall pip + wheel + setuptools first (fixes ImportError)
        curl -sS https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py
        "$VENV_BIN/python" /tmp/get-pip.py 2>/dev/null || true
        rm -f /tmp/get-pip.py
        "$VENV_BIN/pip" install --upgrade --break-system-packages pip wheel setuptools 2>&1 | tail -3
        
        # Install Hermes
        "$VENV_BIN/pip" install --break-system-packages --no-cache-dir -e "$HERMES_DIR[all]" 2>&1 | tail -3
        chmod -R 755 "$VENV_BIN" 2>/dev/null || true
        
        if [ -x "$HERMES_BIN" ]; then
            log "Hermes installed: $HERMES_BIN"
        else
            log_warn "Hermes install failed — terminal will run without agent"
        fi
    fi
    
    # Configure API key
    KEY=""
    KEY_NAME=""
    if [ -n "${API_KEY_DEFAULT:-}" ]; then
        KEY="$API_KEY_DEFAULT"; KEY_NAME="GOOGLE_API_KEY"
    elif [ -n "${GOOGLE_API_KEY:-}" ]; then
        KEY="$GOOGLE_API_KEY"; KEY_NAME="GOOGLE_API_KEY"
    elif [ -n "${OPENROUTER_API_KEY:-}" ]; then
        KEY="$OPENROUTER_API_KEY"; KEY_NAME="OPENROUTER_API_KEY"
    elif [ -n "${ANTHROPIC_API_KEY:-}" ]; then
        KEY="$ANTHROPIC_API_KEY"; KEY_NAME="ANTHROPIC_API_KEY"
    elif [ -n "${OPENAI_API_KEY:-}" ]; then
        KEY="$OPENAI_API_KEY"; KEY_NAME="OPENAI_API_KEY"
    elif [ -f "$CONFIG_TXT" ]; then
        KEY="$(sed -n 's/^GOOGLE_API_KEY=//p' "$CONFIG_TXT" | tail -1)"
        if [ -n "$KEY" ]; then
            KEY_NAME="GOOGLE_API_KEY"
        else
            KEY="$(sed -n 's/^OPENROUTER_API_KEY=//p' "$CONFIG_TXT" | tail -1)"
            KEY_NAME="OPENROUTER_API_KEY"
        fi
    fi
    
    ENV_FILE="$HERMES_HOME/.env"
    if [ -n "$KEY" ]; then
        touch "$ENV_FILE"; chmod 600 "$ENV_FILE"
        if [ -n "$KEY_NAME" ] && grep -q "^${KEY_NAME}=" "$ENV_FILE"; then
            sed -i "s|^${KEY_NAME}=.*|${KEY_NAME}=${KEY}|" "$ENV_FILE"
        else
            printf '\n%s=%s\n' "$KEY_NAME" "$KEY" >> "$ENV_FILE"
        fi
        log "${KEY_NAME} applied to $ENV_FILE"
    else
        log_warn "No API key found"
    fi
    
    # Configure Hermes
    if [ -x "$HERMES_BIN" ]; then
        "$HERMES_BIN" config set terminal.backend local >/dev/null 2>&1 || true
        PROV="$(sed -n 's/^AI_PROVIDER=//p' "$HERMES_HOME/config.txt" 2>/dev/null | tail -1)"
        if [ -n "$PROV" ] && [ "$PROV" != "auto" ]; then
            "$HERMES_BIN" config set provider "$PROV" >/dev/null 2>&1 || true
        fi
        log "Hermes configured"
    fi
) &
INSTALL_PID=$!
log "Background installer started (PID $INSTALL_PID)"

# Wait for web server
wait $APP_PID
