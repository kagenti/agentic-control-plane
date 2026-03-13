"""Configure Python path for k8s_debug_agent imports."""

import sys
from pathlib import Path

# Add the agent root so tests can import from k8s_debug_agent/
agent_root = str(Path(__file__).parent.parent)
if agent_root not in sys.path:
    sys.path.insert(0, agent_root)
