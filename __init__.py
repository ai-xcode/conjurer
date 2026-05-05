"""Conjurer — a ComfyUI extension.

Registers an HTTP chat endpoint inside ComfyUI's own server (port 8188)
and ships a JS panel that injects into ComfyUI's web UI. No separate
Flask process — the assistant lives inside ComfyUI itself, like Copilot.

Symlinked into ~/ComfyUI/custom_nodes/conjurer by install.sh.
"""
from . import server  # noqa: F401  — registers routes as a side-effect of import

# ComfyUI auto-discovers extensions via these globals
NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}
WEB_DIRECTORY = "./web"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
