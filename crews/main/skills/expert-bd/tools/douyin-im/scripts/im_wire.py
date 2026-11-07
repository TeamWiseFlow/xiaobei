"""Compatibility imports for the shared IM codec."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "_shared"))
from douyin_utils.im_wire import *  # noqa: F401,F403
