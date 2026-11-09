"""Decision logic: which backend, which model, which parameters.

Pure functions, no I/O, so everything here is unit-testable.
"""
import ipaddress
import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

from .config import DEFAULT_AGENT_KEYWORDS
from .keywords import compile_keywords
from .lmstudio import ModelInfo
from .installer import _is_local

CODE_RE = re.compile(
    r"\b(code|coding|function|class|bug|debug|refactor|compile|regex|script|python|rust|"
    r"javascript|typescript|bash|sql|stack ?trace|exception|programm\w*|funktion|fehler)\b",
    re.I,
)
DEEP_RE = re.compile(
    r"\b(analy[sz]e|analysiere|explain in detail|erkläre ausführlich|prove|beweise|plan|plane|"
    r"compare|vergleiche|essay|research|recherchiere|summari[sz]e|fasse .* zusammen|step by step|"
    r"schritt für schritt|design|architektur|architecture)\b",
    re.I,
)

# Per-tier generation parameters. Context is capped by the model's maximum.
TIER_PARAMS = {
    "fast": {"context": 4096, "temperature": 0.5, "max_tokens": 512},
    "balanced": {"context": 8192, "temperature": 0.7, "max_tokens": 2048},
    "deep": {"context": 16384, "temperature": 0.7, "max_tokens": 4096},
    "code": {"context": 16384, "temperature": 0.2, "max_tokens": 4096},
    "agent": {"context": 8192, "temperature": 0.4, "max_tokens": 4096},
}


def endpoint_scope(endpoint: str) -> str:
    try:
        hostname = (urlparse(endpoint).hostname or "").lower().rstrip(".")
    except ValueError:
        return "wan"
    if hostname == "localhost":
        return "local"
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return "wan"
    if address.is_loopback:
        return "local"
    if address.is_private or address.is_link_local:
        return "lan"
    return "wan"


@dataclass
class Route:
    backend: str  # lmstudio | hermes | provider
    tier: str
    reason: str
    model: str = ""
    provider_id: str = ""
    params: dict = field(default_factory=dict)
    needs_load: bool = False


def _flatten(keywords) -> tuple[str, ...]:
    """Accepts the per-language dict (all languages are matched), a flat list, or None for defaults."""
    if keywords is None:
        keywords = DEFAULT_AGENT_KEYWORDS
    if isinstance(keywords, dict):
        return tuple(k for words in keywords.values() for k in words)
    return tuple(keywords)


def classify(prompt: str, agent_keywords: dict | list[str] | None = None) -> tuple[str, str]:
    """Returns (tier, reason). Fast heuristics so routing itself costs nothing."""
    words = len(prompt.split())
    agent_re = compile_keywords(_flatten(agent_keywords))
    if agent_re and agent_re.search(prompt):
        return "agent", "action request"
    if CODE_RE.search(prompt) or "```" in prompt:
        return "code", "programming topic"
    if DEEP_RE.search(prompt) or words > 120:
        return "deep", "complex request"
    if words <= 12:
        return "fast", "short question"
    return "balanced", "general request"


def pick_model(models: list[ModelInfo], tier: str, mem_bytes: int, preferred: str = "",
               require_vision: bool = False) -> ModelInfo | None:
    chat = [m for m in models if m.is_chat]
    if require_vision:
        chat = [m for m in chat if m.supports_vision]
    if not chat:
        return None
    if preferred:
        for m in chat:
            if m.key == preferred:
                return m
    # Skip models that clearly will not fit in RAM (keep ~25% headroom).
    fits = [m for m in chat if not m.size_bytes or m.size_bytes <= mem_bytes * 0.75] or chat

    def size(m: ModelInfo) -> float:
        return m.params_b or (m.size_bytes / 0.6e9) or 7.0

    if tier == "fast":
        small = [m for m in fits if size(m) <= 9]
        # An already-loaded small model beats loading a new one.
        loaded_small = [m for m in small if m.loaded]
        pool = loaded_small or small or fits
        return min(pool, key=size)

    if tier == "code":
        coders = [m for m in fits if re.search(r"code|coder|devstral", m.key, re.I)]
        if coders:
            return _prefer_loaded(coders, size, target=14)

    if tier == "deep":
        return _prefer_loaded(fits, size, target=30, prefer_big=True)

    # balanced / agent / code without coder: mid-size model
    return _prefer_loaded(fits, size, target=8)


def _prefer_loaded(pool, size, target: float, prefer_big: bool = False):
    # Closest to the target size; for 'deep' the biggest one up to the target wins.
    def score(m):
        s = size(m)
        base = -min(s, target) if prefer_big else abs(s - target)
        # Loaded models save a multi-second load, so they get a bonus.
        return base - (4 if m.loaded else 0)

    return min(pool, key=score)


def agent_route(cfg: dict, reason: str) -> Route | None:
    backend = cfg.get("agent_backend", "hermes")
    if backend == "pi":
        if cfg["pi"]["enabled"] and not cfg["local_only"]:
            return Route("pi", "agent", reason, cfg["pi"].get("model") or "Pi")
        return None
    if cfg["hermes"]["enabled"] and (not cfg["local_only"] or _is_local(cfg["hermes"]["endpoint"])):
        return Route("hermes", "agent", reason, cfg["hermes"]["model"])
    return None


def priority_routes(prompt: str, cfg: dict, model_lists: dict, mem_bytes: int,
                    needs_image: bool = False) -> list[Route]:
    tier, reason = classify(prompt, cfg.get("agent_keywords"))
    candidates = []
    for backend in ("lmstudio", "strata"):
        settings = cfg[backend]
        if not settings.get("enabled", backend == cfg.get("local_backend", "lmstudio")):
            continue
        scope = endpoint_scope(settings["url"])
        if cfg["local_only"] and scope != "local":
            continue
        preferred = cfg["lmstudio"].get("preferred_vision", "") if needs_image else cfg["lmstudio"].get(
            f"preferred_{'balanced' if tier == 'agent' else tier}", "")
        available = model_lists.get(backend) or []
        if backend == "lmstudio" and scope != "local":
            available = [model for model in available if model.loaded]
        model = pick_model(available, tier, mem_bytes, preferred, require_vision=needs_image)
        if model:
            params = dict(TIER_PARAMS[tier])
            params.update(context=min(params["context"], model.max_context), supports_vision=model.supports_vision,
                          supports_thinking=model.supports_thinking, supports_tools=model.supports_tools)
            candidates.append((scope, Route(backend, tier, reason, model.key, params=params,
                                            needs_load=backend == "lmstudio" and not model.loaded)))
    if not needs_image:
        for provider in cfg["providers"]:
            if not provider.get("enabled", True):
                continue
            scope = provider.get("scope") if provider.get("scope") in ("lan", "wan") else endpoint_scope(
                provider.get("endpoint", ""))
            if cfg["local_only"] and scope != "local":
                continue
            candidates.append((scope, Route("provider", tier, reason, provider["model"], provider["id"])))
    order = {"local": 0, "lan": 1, "wan": 2}
    return [route for _scope, route in sorted(candidates, key=lambda item: order[item[0]])]


def decide(prompt: str, cfg: dict, models: list[ModelInfo] | None, mem_bytes: int,
           needs_image: bool = False) -> Route | None:
    """Builds a Route. Returns None when no backend is usable."""
    tier, reason = classify(prompt, cfg.get("agent_keywords"))
    routing = cfg["routing"]
    providers = [] if cfg["local_only"] else [p for p in cfg["providers"] if p.get("enabled", True)]
    agent = agent_route(cfg, reason)
    backend = cfg.get("local_backend", "lmstudio")
    if cfg["local_only"] and not _is_local(cfg[backend]["url"]):
        models = None

    if not needs_image and routing.startswith("provider:") and not cfg["local_only"]:
        pid = routing.split(":", 1)[1]
        for p in providers:
            if p["id"] == pid:
                return Route("provider", tier, "forced", p["model"], pid)
    if not needs_image and routing == "hermes" and agent:
        return agent_route(cfg, "forced")

    if not needs_image and routing == "auto" and tier == "agent" and agent:
        return agent

    if models is not None:
        lms = cfg["lmstudio"]
        preferred = lms.get("preferred_vision", "") if needs_image else lms.get(
            f"preferred_{'balanced' if tier == 'agent' else tier}", "")
        m = pick_model(models, tier, mem_bytes, preferred, require_vision=needs_image)
        if m:
            params = dict(TIER_PARAMS[tier])
            params["context"] = min(params["context"], m.max_context)
            params["supports_vision"] = m.supports_vision
            params["supports_thinking"] = m.supports_thinking
            params["supports_tools"] = m.supports_tools
            return Route(backend, tier, reason, m.key, params=params, needs_load=not m.loaded)

    if needs_image:
        return None

    if routing == "local":
        return None

    # Fallbacks when LM Studio is down or has no model.
    if agent:
        return agent_route(cfg, "Local backend unavailable")
    if providers:
        p = providers[0]
        return Route("provider", tier, "LM Studio unavailable", p["model"], p["id"])
    return None
