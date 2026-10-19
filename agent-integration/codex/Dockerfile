# This container has NOT been built in the delivery environment (Docker absent).
# Pin the resulting image digest after building and auditing on the target machine.
FROM node:22-bookworm-slim
LABEL dev.codexglasses.protocol="stdio-broker-v1"
RUN apt-get update && apt-get install -y --no-install-recommends python3 git ripgrep ca-certificates \
    && python3 -c "import unittest" \
    && npm install --global @openai/codex@0.162.1 \
    && useradd --uid 10001 --create-home agent \
    && mkdir -p /workspace /home/agent/.codex /opt/codexglasses \
    && chown -R 10001:10001 /home/agent /workspace
COPY worker_entry.py /opt/codexglasses/worker_entry.py
USER 10001:10001
ENV XDG_CACHE_HOME=/tmp/codexglasses-cache
WORKDIR /workspace
ENTRYPOINT ["python3", "/opt/codexglasses/worker_entry.py"]
