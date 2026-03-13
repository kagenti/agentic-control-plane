"""Configure Python path for k8s_debug_agent imports."""

import sys
from pathlib import Path

# Add the agent root so tests can import from k8s_debug_agent/
sys.path.insert(0, str(Path(__file__).parent.parent))
