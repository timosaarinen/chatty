#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "❌  Usage: $0 [--model <model-name> | --litellm-model <model-name>] [additional-chatty-args...]"
  echo "   Example: $0 --model codellama:latest"
  echo "   Example: $0 --litellm-model openai/gpt-4o --debug"
  exit 1
fi

IMAGE_NAME="chatty"

echo "▶️  Running ${IMAGE_NAME} with args: $@"

docker run --rm \
  --add-host=host.docker.internal:host-gateway \
  -it \
  -v "$(pwd)":/home/developer/chatty:rw \
  "${IMAGE_NAME}" \
    --ollama http://host.docker.internal:11434 \
    "$@"
