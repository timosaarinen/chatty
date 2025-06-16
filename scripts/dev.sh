#!/usr/bin/env bash
set -euo pipefail

IMAGE_NAME="chatty"
HOST_PORT=8000
CONTAINER_PORT=8000
WORKDIR="$(pwd)"
CONTAINER_WORKDIR="/home/developer/chatty"

if [[ $# -lt 1 ]]; then
  echo "❌  Usage: $0 <model-name>"
  exit 1
fi
MODEL="$1"
shift

OLLAMA_URL="http://host.docker.internal:11434"

echo "🚀  Starting dev container with model=${MODEL}…"
docker run -d --rm \
  -p ${HOST_PORT}:${CONTAINER_PORT} \
  -v "${WORKDIR}:${CONTAINER_WORKDIR}:rw" \
  --name chatty-dev \
  "${IMAGE_NAME}" \
    --model "${MODEL}" \
    --ollama "${OLLAMA_URL}" \
    --host "0.0.0.0" --port "8000" --reload

echo "✅  Dev container started. Access it at http://localhost:${HOST_PORT}"
echo "🔍  To attach a shell: scripts/exec.sh"
