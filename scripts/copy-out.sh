#!/usr/bin/env bash
set -euo pipefail

USAGE="Usage: $0 <container-path> [<host-dest>]"
if [[ $# -lt 1 ]]; then
  echo "$USAGE"
  exit 1
fi

CONTAINER_PATH="$1"
HOST_DEST="${2:-.}"

IMAGE_NAME="chatty"
CONTAINER_ID=$(docker ps -q --filter "ancestor=${IMAGE_NAME}")

if [[ -z "$CONTAINER_ID" ]]; then
  echo "⚠️  No running container for image ${IMAGE_NAME}"
  exit 1
fi

echo "📦  Copying ${CONTAINER_ID}:${CONTAINER_PATH} → ${HOST_DEST}"
docker cp "${CONTAINER_ID}:${CONTAINER_PATH}" "${HOST_DEST}"
echo "✅  Done."
