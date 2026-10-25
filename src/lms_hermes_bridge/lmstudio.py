"""LM Studio access: model discovery (REST + `lms` CLI) and model loading."""
import json
import re
import shutil
import subprocess
import urllib.request
from dataclasses import dataclass
from pathlib import Path

LMS_FALLBACK = Path.home() / ".lmstudio" / "bin" / "lms"


@dataclass
class ModelInfo:
    key: str
    type: str = "llm"  # llm | vlm | embeddings
    loaded: bool = False
    params_b: float = 0.0  # billions of parameters (0 = unknown)
    size_bytes: int = 0
    max_context: int = 4096

    @property
    def is_chat(self) -> bool:
        return self.type in ("llm", "vlm")


def parse_params_b(text: str) -> float:
    """Extract '7b', '12B', '0.6b', '8x7b' style sizes from a model name."""
    m = re.search(r"(?<![a-z0-9])(?:(\d+)x)?(\d+(?:\.\d+)?)\s*b(?![a-z])", text.lower())
    if not m:
        return 0.0
    return float(m.group(2)) * (int(m.group(1)) if m.group(1) else 1)


def _lms_bin() -> str | None:
    return shutil.which("lms") or (str(LMS_FALLBACK) if LMS_FALLBACK.exists() else None)


def _get_json(url: str, timeout: float = 3.0):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.load(r)


def list_models(base_url: str) -> list[ModelInfo] | None:
    """Returns None when the server is unreachable."""
    try:
        data = _get_json(base_url.rstrip("/") + "/api/v0/models")["data"]
    except Exception:
        return None
    sizes = _cli_sizes()
    models = []
    for d in data:
        key = d.get("id", "")
        models.append(
            ModelInfo(
                key=key,
                type=d.get("type", "llm"),
                loaded=d.get("state") == "loaded",
                params_b=parse_params_b(key),
                size_bytes=sizes.get(key, 0),
                max_context=int(d.get("max_context_length") or 4096),
            )
        )
    return models


def _cli_sizes() -> dict[str, int]:
    lms = _lms_bin()
    if not lms:
        return {}
    try:
        out = subprocess.run([lms, "ls", "--json"], capture_output=True, text=True, timeout=10).stdout
        return {m["modelKey"]: int(m.get("sizeBytes", 0)) for m in json.loads(out)}
    except Exception:
        return {}


def load_model(key: str, context: int, unload_others: bool) -> bool:
    lms = _lms_bin()
    if not lms:
        return False
    try:
        if unload_others:
            subprocess.run([lms, "unload", "--all"], capture_output=True, timeout=60)
        r = subprocess.run(
            [lms, "load", key, "--context-length", str(context), "--gpu", "max", "-y"],
            capture_output=True,
            timeout=600,
        )
        return r.returncode == 0
    except Exception:
        return False


def mem_total_bytes() -> int:
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                return int(line.split()[1]) * 1024
    except OSError:
        pass
    return 16 * 1024**3
