FROM nvidia/cuda:12.1.1-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y \
    bash \
    ca-certificates \
    curl \
    python3 \
    python3-pip \
    zstd \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://ollama.com/install.sh | sh

WORKDIR /opt/program

COPY requirements.txt /opt/program/requirements.txt
RUN python3 -m pip install --upgrade pip && \
    python3 -m pip install -r /opt/program/requirements.txt

COPY entrypoint.sh /opt/program/entrypoint.sh
COPY server.py /opt/program/server.py

RUN chmod +x /opt/program/entrypoint.sh

EXPOSE 8080 11434

ENTRYPOINT ["/opt/program/entrypoint.sh"]
CMD ["serve"]
