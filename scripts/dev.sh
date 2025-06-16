#!/usr/bin/env bash
set -euo pipefail

IMAGE_NAME="chatty"
CONTAINER_NAME="chatty-dev"
WORKDIR="$(pwd)"
CONTAINER_WORKDIR="/home/developer/chatty"

if docker ps --filter "name=^/${CONTAINER_NAME}$" --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
  echo "✅  Dev container '${CONTAINER_NAME}' is already running."
  echo "    To get a shell, run: scripts/exec.sh"
  exit 0
fi

echo "🚀  Starting dev container '${CONTAINER_NAME}'..."
docker run -d --rm \
  --add-host=host.docker.internal:host-gateway \
  -v "${WORKDIR}:${CONTAINER_WORKDIR}:rw" \
  --name "${CONTAINER_NAME}" \
  --entrypoint=tail \
  "${IMAGE_NAME}" -f /dev/null

echo "✅  Dev container started."
echo "    - Your local directory is mounted at ${CONTAINER_WORKDIR}"
echo
echo "👉 To get a shell inside the container, run: scripts/exec.sh"
echo "   Inside the shell, you can run the agent, for example:"
echo "   uv run chatty.py --model <your-model> --ollama http://host.docker.internal:11434"
