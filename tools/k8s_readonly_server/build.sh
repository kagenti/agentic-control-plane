#!/bin/bash
set -e

# Build script for k8s-readonly-server MCP tool

IMAGE_NAME="${IMAGE_NAME:-ghcr.io/kagenti/k8s-readonly-mcp-server}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
FULL_IMAGE="${IMAGE_NAME}:${IMAGE_TAG}"

echo "Building ${FULL_IMAGE}..."

# Build the image
docker build -t "${FULL_IMAGE}" .

echo "✅ Built ${FULL_IMAGE}"
echo ""
echo "To push to registry:"
echo "  docker push ${FULL_IMAGE}"
echo ""
echo "To load into kind cluster:"
echo "  kind load docker-image ${FULL_IMAGE}"
echo ""
echo "To use with deployment:"
echo "  Update image in deploy/k8s-readonly-server/04-deployment.yaml"
