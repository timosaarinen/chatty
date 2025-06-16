#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "❌  Usage: $0 <model-name> [additional-chatty-args...]"
  echo "   Example: $0 codellama:latest"
  echo "   Example: $0 qwen2.5-coder:7b --debug"
  exit 1
fi

IMAGE_NAME="chatty"
MODEL="$1"
shift

echo "▶️  Running ${IMAGE_NAME} with model ${MODEL}..."

docker run --rm \
  --add-host=host.docker.internal:host-gateway \
  -it \
  -v "$(pwd)":/home/developer/chatty:rw \
  "${IMAGE_NAME}" \
    --model "${MODEL}" \
    --ollama http://host.docker.internal:11434 \
    "$@"
