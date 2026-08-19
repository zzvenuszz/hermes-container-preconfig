FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PIP_BREAK_SYSTEM_PACKAGES=1
ENV HERMES_CONTAINER=1

WORKDIR /app

# ============================================================
# SYSTEM DEPENDENCIES — minimal, no browser/X11/audio packages
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
# config.txt holds the Gemini API key (user-provided). entrypoint.sh reads
# it and writes the key into /data/hermes/.env (the persisted volume) — it is
# NOT read from source code at runtime.
COPY config.txt /app/config.txt

RUN chmod +x \
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
# DATA
# ============================================================
RUN mkdir -p \
    /data/hermes/hermes-agent && \
    git clone --depth=1 https://github.com/NousResearch/hermes-agent.git /data/hermes/hermes-agent

# ============================================================
# HUGGING FACE
# ============================================================
ENV PORT=7860
ENV HERMES_HOME=/data/hermes
ENV HERMES_NONINTERACTIVE=1

# Make the venv + Hermes-managed tooling available on PATH for every process.
ENV PATH="/data/hermes/bin:/data/hermes/node/bin:/data/hermes/hermes-agent/venv/bin:/root/.local/bin:/usr/local/bin:/usr/bin:/bin"

EXPOSE 7860

# Startup pipeline:
#   entrypoint.sh  → install (once) + configure Hermes → exec app.py
#   app.py         → manages the Hermes screen session, then serves the web
#                    UI on 0.0.0.0:$PORT (keeps the container alive).
ENTRYPOINT ["/app/entrypoint.sh"]
