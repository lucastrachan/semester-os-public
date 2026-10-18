"""Shared backend code. Importing this package puts backend/vendor (pure-Python pypdf and tzdata,
installed by scripts/deploy.py) on sys.path, so every Lambda sees them even if the runtime has no tz data."""
import os
import sys

_VENDOR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "vendor")
if os.path.isdir(_VENDOR) and _VENDOR not in sys.path:
    sys.path.insert(0, _VENDOR)
