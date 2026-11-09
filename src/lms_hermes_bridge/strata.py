"""Discover models served by the Strata OpenAI-compatible API."""
import json
import urllib.request

from .lmstudio import ModelInfo, parse_params_b


def list_models(cfg: dict) -> list[ModelInfo] | None:
    headers = {}
    if cfg.get("api_key"):
        headers["Authorization"] = f"Bearer {cfg['api_key']}"
    try:
        request = urllib.request.Request(cfg["url"].rstrip("/") + "/v1/models", headers=headers)
        with urllib.request.urlopen(request, timeout=3) as response:
            data = json.load(response)["data"]
        return [ModelInfo(item["id"], type="vlm" if cfg.get("vision") else "llm", loaded=True,
                          params_b=parse_params_b(item["id"])) for item in data if item.get("id")]
    except (OSError, ValueError, KeyError, TypeError):
        return None