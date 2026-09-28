from pathlib import Path
import sys


AGENT_SOURCE = Path(__file__).resolve().parents[2] / "code" / "agent"
if str(AGENT_SOURCE) not in sys.path:
    sys.path.insert(0, str(AGENT_SOURCE))
