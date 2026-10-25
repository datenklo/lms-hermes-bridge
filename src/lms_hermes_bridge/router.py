"""Decision logic: which backend, which model, which parameters.

Pure functions, no I/O, so everything here is unit-testable.
"""
import re
from dataclasses import dataclass, field
from functools import lru_cache

from .config import DEFAULT_AGENT_KEYWORDS
from .lmstudio import ModelInfo

CODE_RE = re.compile(
    r"\b(code|coding|function|class|bug|debug|refactor|compile|regex|script|python|rust|"
    r"javascript|typescript|bash|sql|stack ?trace|exception|programm\w*|funktion|fehler)\b",
    re.I,
)
# Spaces inside a keyword phrase tolerate a filler article: "create file" matches "create a file".
_GAP = r"\s+(?:(?:a|an|the|my|ein|eine|einen|einem|der|die|das|den|dem|mein|meine|meinen)\s+)?"


@lru_cache(maxsize=8)
def _agent_re(keywords: tuple[str, ...]) -> re.Pattern | None:
    """Whole-word match; a trailing * on a keyword also matches longer forms (install* -> installing)."""
    parts = []
    for kw in keywords:
        kw = kw.strip()
        if not kw.strip("*"):
            continue
        prefix = kw.endswith("*")
        words = kw.rstrip("*").split()
        parts.append(_GAP.join(re.escape(w) for w in words) + ("" if prefix else r"(?!\w)"))
    return re.compile(r"(?<!\w)(?:" + "|".join(parts) + ")", re.I) if parts else None


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


@dataclass
class Route:
    backend: str  # lmstudio | hermes | provider
    tier: str
    reason: str
    model: str = ""
    provider_id: str = ""
    params: dict = field(default_factory=dict)
    needs_load: bool = False


def classify(prompt: str, agent_keywords: list[str] | None = None) -> tuple[str, str]:
    """Returns (tier, reason). Fast heuristics so routing itself costs nothing."""
    words = len(prompt.split())
    kws = DEFAULT_AGENT_KEYWORDS if agent_keywords is None else agent_keywords
    agent_re = _agent_re(tuple(kws))
    if agent_re and agent_re.search(prompt):
        return "agent", "action request"
    if CODE_RE.search(prompt) or "```" in prompt:
        return "code", "programming topic"
    if DEEP_RE.search(prompt) or words > 120:
        return "deep", "complex request"
    if words <= 12:
        return "fast", "short question"
    return "balanced", "general request"


def pick_model(models: list[ModelInfo], tier: str, mem_bytes: int, preferred: str = "") -> ModelInfo | None:
    chat = [m for m in models if m.is_chat]
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


def decide(prompt: str, cfg: dict, models: list[ModelInfo] | None, mem_bytes: int) -> Route | None:
    """Builds a Route. Returns None when no backend is usable."""
    tier, reason = classify(prompt, cfg.get("agent_keywords"))
    routing = cfg["routing"]
    providers = [] if cfg["local_only"] else [p for p in cfg["providers"] if p.get("enabled", True)]
    hermes_ok = cfg["hermes"]["enabled"]

    if routing.startswith("provider:") and not cfg["local_only"]:
        pid = routing.split(":", 1)[1]
        for p in providers:
            if p["id"] == pid:
                return Route("provider", tier, "forced", p["model"], pid)
    if routing == "hermes" and hermes_ok:
        return Route("hermes", "agent", "forced", cfg["hermes"]["model"])

    if routing == "auto" and tier == "agent" and hermes_ok:
        return Route("hermes", "agent", reason, cfg["hermes"]["model"])

    if models is not None:
        lms = cfg["lmstudio"]
        m = pick_model(models, tier, mem_bytes, lms.get(f"preferred_{'balanced' if tier == 'agent' else tier}", ""))
        if m:
            params = dict(TIER_PARAMS[tier])
            params["context"] = min(params["context"], m.max_context)
            return Route("lmstudio", tier, reason, m.key, params=params, needs_load=not m.loaded)

    if routing == "local":
        return None

    # Fallbacks when LM Studio is down or has no model.
    if hermes_ok:
        return Route("hermes", tier, "LM Studio unavailable", cfg["hermes"]["model"])
    if providers:
        p = providers[0]
        return Route("provider", tier, "LM Studio unavailable", p["model"], p["id"])
    return None
