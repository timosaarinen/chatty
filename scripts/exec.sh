#!/usr/bin/env bash
set -euo pipefail

CONTAINER_NAME="chatty-dev"

# Check if it's running
if ! docker ps --filter "name=^/${CONTAINER_NAME}$" --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
  echo "⚠️  No running container named ${CONTAINER_NAME}"
  exit 1
fi

echo "🔍  Exec’ing into container ${CONTAINER_NAME}"
docker exec -it "${CONTAINER_NAME}" /bin/bash
