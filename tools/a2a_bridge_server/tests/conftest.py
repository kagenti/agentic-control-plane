"""Configure Python path for a2a_bridge_server lib imports."""

import sys
from pathlib import Path

# Add the package root so tests can import from lib/
sys.path.insert(0, str(Path(__file__).parent.parent))
