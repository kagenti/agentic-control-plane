#!/bin/bash
# Test runner for agentic-control-plane
# Discovers and runs all tests in the src directory

set -e

echo "🧪 Running tests..."
echo ""

# Run pytest with test discovery in src directory
uv run --extra dev pytest src/ -v --tb=short

echo ""
echo "✅ All tests passed!"
