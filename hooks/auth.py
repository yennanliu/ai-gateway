# LiteLLM's custom_auth loader requires a .py file next to --config and execs it
# without registering it in sys.modules, which crashes on our frozen dataclass +
# `from __future__ import annotations`. Re-import normally here to dodge that.
from hooks.auth import user_api_key_auth  # noqa: F401
