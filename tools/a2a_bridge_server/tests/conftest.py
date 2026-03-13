"""Configure Python path for a2a_bridge_server lib imports."""

import sys
from pathlib import Path

# Add the package root so tests can import from lib/
package_root = str(Path(__file__).parent.parent)
if package_root not in sys.path:
    sys.path.insert(0, package_root)
