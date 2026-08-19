FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PIP_BREAK_SYSTEM_PACKAGES=1
ENV HERMES_CONTAINER=1

WORKDIR /app

# ============================================================
# SYSTEM DEPENDENCIES
# ============================================================
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        sudo \
        screen \
        git \
        curl \
        wget \
        ca-certificates \
        xz-utils \
        ripgrep \
        procps \
        bash \
        openssh-client \
        unzip \
        tar \
        gzip \
        bzip2 \
        file \
        less \
        libatomic1 \
    && rm -rf /var/lib/apt/lists/*

# ============================================================
# SUDO
# ============================================================
RUN echo "root ALL=(ALL) NOPASSWD:ALL" \
    > /etc/sudoers.d/root && \
    chmod 440 /etc/sudoers.d/root

# ============================================================
# APPLICATION
# ============================================================
COPY app.py /app/app.py
COPY templates /app/templates
COPY install.sh /app/install.sh
COPY entrypoint.sh /app/entrypoint.sh
COPY config.txt /app/config.txt

RUN chmod 755 \
    /app/app.py \
    /app/install.sh \
    /app/entrypoint.sh

# ============================================================
# PYTHON
# ============================================================
RUN pip install \
    --no-cache-dir \
    fastapi \
    uvicorn[standard]

# ============================================================
# PRE-INSTALL HERMES (in build phase — avoids runtime permission issues)
# ============================================================
RUN mkdir -p /data/hermes && \
    git clone --depth=1 https://github.com/NousResearch/hermes-agent.git /data/hermes/hermes-agent && \
    \
    # Install uv (managed)
    curl -LsSf https://astral.sh/uv/install.sh | sh 2>&1 | tail -3 && \
    \
    # Create venv + install Hermes (skip Node.js/browser tools)
    python3 -m venv /data/hermes/hermes-agent/venv && \
    /data/hermes/hermes-agent/venv/bin/pip install --no-cache-dir \
        -e "/data/hermes/hermes-agent[all]" 2>&1 | tail -5 && \
    \
    # Fix permissions on all binaries
    chmod -R 755 /data/hermes/hermes-agent/venv/bin/ && \
    chmod -R 755 /data/hermes/hermes-agent/hermes_cli/ && \
    \
    # Pre-install Node.js 26 LTS (avoids runtime download + install.sh conflict)
    curl -fsSL https://nodejs.org/dist/v26.7.0/node-v26.7.0-linux-x64.tar.xz -o /tmp/node.tar.xz && \
    mkdir -p /data/hermes/node && \
    tar -xJf /tmp/node.tar.xz -C /data/hermes/node --strip-components=1 && \
    rm /tmp/node.tar.xz && \
    chmod -R 755 /data/hermes/node/bin/ && \
    \
    # Copy installed Hermes to fallback location (HF Spaces volume may wipe /data)
    cp -r /data/hermes /app/.hermes-fallback && \
    chmod -R 755 /app/.hermes-fallback/hermes-agent/venv/bin/ && \
    \
    # Clean apt cache
    rm -rf /var/lib/apt/lists/*

# ============================================================
# HUGGING FACE
# ============================================================
ENV PORT=7860
ENV HERMES_HOME=/data/hermes
ENV HERMES_NONINTERACTIVE=1

# Make the venv + Hermes-managed tooling available on PATH
ENV PATH="/data/hermes/bin:/data/hermes/node/bin:/data/hermes/hermes-agent/venv/bin:/root/.local/bin:/usr/local/bin:/usr/bin:/bin"

EXPOSE 7860

# Startup pipeline:
#   entrypoint.sh  → configure Hermes (key already in image) → exec app.py
#   app.py         → manages the Hermes screen session, then serves web UI
ENTRYPOINT ["/app/entrypoint.sh"]
