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
        models = []
        for item in data:
            if not item.get("id"):
                continue
            # llama.cpp-style servers announce what they can do; guessing costs context and vision:
            # {"status": {"value": "loaded"}, "meta": {"n_ctx": 131072},
            #  "architecture": {"input_modalities": ["text", "image"]}}
            meta = item.get("meta") or {}
            modalities = {str(m).lower() for m in ((item.get("architecture") or {}).get("input_modalities") or [])}
            vision = bool(cfg.get("vision")) or "image" in modalities
            models.append(ModelInfo(
                key=item["id"],
                type="vlm" if vision else "llm",
                loaded=(item.get("status") or {}).get("value", "loaded") == "loaded",
                params_b=parse_params_b(item["id"]),
                max_context=int(meta.get("n_ctx") or 4096),
                capabilities=tuple(sorted(modalities)),
            ))
        return models
    except (OSError, ValueError, KeyError, TypeError):
        return None
