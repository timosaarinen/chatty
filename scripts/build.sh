#!/usr/bin/env bash
set -euo pipefail

IMAGE_NAME="chatty"

echo "🛠  Building Docker image ${IMAGE_NAME}..."
docker build -t "${IMAGE_NAME}" .
echo "✅  Built ${IMAGE_NAME}"
