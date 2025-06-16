#!/usr/bin/env bash
set -euo pipefail

IMAGE_NAME="chatty"
HOST_PORT=8000
CONTAINER_PORT=8000

echo "▶️  Running ${IMAGE_NAME}.."

docker run --rm \
  -p 8000:8000 \
  -it \
  -v "$(pwd)":/home/developer/chatty:rw \
  chatty \
    --model qwen2.5-coder:7b \
    --ollama http://host.docker.internal:11434
