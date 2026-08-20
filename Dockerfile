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
# PRE-INSTALL Node.js 20 LTS (avoids runtime download in HF Spaces)
# ============================================================
ENV NODE_VERSION=v20.11.1
RUN curl -fsSL "https://nodejs.org/dist/${NODE_VERSION}/node-${NODE_VERSION}-linux-x64.tar.xz" -o /tmp/node.tar.xz && \
    mkdir -p /opt/node && \
    tar -xJf /tmp/node.tar.xz -C /opt/node --strip-components=1 && \
    rm /tmp/node.tar.xz && \
    chmod -R 755 /opt/node/bin/

ENV PATH="/opt/node/bin:${PATH}"

# ============================================================
# PRE-INSTALL Hermes Agent (avoids runtime install.sh failures)
# ============================================================
RUN mkdir -p /data/hermes/hermes-agent && \
    git clone --depth=1 https://github.com/NousResearch/hermes-agent.git /data/hermes/hermes-agent && \
    python3 -m venv /data/hermes/hermes-agent/venv && \
    /data/hermes/hermes-agent/venv/bin/pip install --upgrade --break-system-packages pip wheel setuptools && \
    /data/hermes/hermes-agent/venv/bin/pip install --no-cache-dir --break-system-packages -e "/data/hermes/hermes-agent[all]" && \
    chmod -R 755 /data/hermes/hermes-agent/venv/bin/ && \
    cp -r /data/hermes /app/.hermes-fallback

# ============================================================
# DATA
# ============================================================
RUN mkdir -p /data/hermes

# ============================================================
# HUGGING FACE
# ============================================================
ENV PORT=7860
ENV HERMES_HOME=/data/hermes
ENV HERMES_NONINTERACTIVE=1

EXPOSE 7860

ENTRYPOINT ["/app/entrypoint.sh"]
