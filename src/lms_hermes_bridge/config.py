"""Persistent settings stored as JSON in ~/.config/lms-hermes-bridge/config.json."""
import copy
import json
import os
from pathlib import Path

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "lms-hermes-bridge"
CONFIG_FILE = CONFIG_DIR / "config.json"

PROVIDER_PRESETS = {
    "openai": {
        "name": "ChatGPT (OpenAI)",
        "kind": "openai",
        "endpoint": "https://api.openai.com/v1/chat/completions",
        "model": "gpt-4o",
    },
    "anthropic": {
        "name": "Claude (Anthropic)",
        "kind": "anthropic",
        "endpoint": "https://api.anthropic.com/v1/messages",
        "model": "claude-sonnet-4-5",
    },
    "copilot": {
        "name": "Copilot (GitHub Models)",
        "kind": "openai",
        "endpoint": "https://models.github.ai/inference/chat/completions",
        "model": "openai/gpt-4.1",
    },
}

DEFAULTS = {
    "language": "auto",  # auto | en | de
    "hotkey": "<Control><Alt>space",
    "local_only": False,  # never contact external providers
    "check_components": True,  # offer to install missing LM Studio / Hermes at start
    "routing": "auto",  # auto | local | hermes | provider:<id>
    "lmstudio": {
        "url": "http://localhost:1234",
        "auto_load": True,  # load the selected model via the `lms` CLI
        "unload_others": True,  # free memory before loading a different model
        "preferred_fast": "",  # optional model key overrides
        "preferred_balanced": "",
        "preferred_deep": "",
        "preferred_code": "",
    },
    "hermes": {
        "enabled": False,
        "endpoint": "http://127.0.0.1:8642/v1/chat/completions",
        "api_key": "",
        "model": "hermes-agent",
    },
    "providers": [],  # list of {id, name, kind, endpoint, api_key, model, enabled}
}


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load() -> dict:
    try:
        return _merge(DEFAULTS, json.loads(CONFIG_FILE.read_text()))
    except (OSError, ValueError):
        return copy.deepcopy(DEFAULTS)


def save(cfg: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_FILE.with_suffix(".tmp")
    # The file may contain API keys: owner-only access.
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(cfg, f, indent=2)
    os.replace(tmp, CONFIG_FILE)
