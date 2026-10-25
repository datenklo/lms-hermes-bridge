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

DEFAULT_AGENT_KEYWORDS = {
    "en": [
        "open", "launch", "start", "run", "execute", "close", "quit", "kill", "install",
        "uninstall", "update", "upgrade", "restart", "reboot", "shut down", "lock the screen",
        "turn on", "turn off", "connect to", "disconnect", "mount", "unmount", "set volume",
        "set brightness", "mute", "create file", "create folder", "make folder", "delete", "remove",
        "rename", "move", "copy", "save file", "download", "upload", "zip", "unzip", "extract",
        "compress", "backup", "list files", "show files", "find file", "browse", "go to",
        "navigate to", "search the web", "search online", "google", "send email", "send mail",
        "send message", "schedule", "remind me", "set timer", "set alarm", "add to calendar",
        "take screenshot", "screenshot", "click", "automate",
    ],
    "de": [
        "öffne*", "starte*", "führe aus*", "ausführen*", "schließe*", "beende*", "installiere*",
        "deinstalliere*", "aktualisiere*", "neustart*", "fahre herunter*", "herunterfahren*",
        "sperre den bildschirm*", "schalte ein*", "schalte aus*", "verbinde*", "trenne*",
        "stelle lautstärke*", "stelle helligkeit*", "erstelle datei*", "erstelle ordner*",
        "lege ordner an*", "lösche*", "entferne*", "benenne um*", "verschiebe*", "kopiere*",
        "speichere datei*", "lade herunter*", "lade datei herunter*", "lade hoch*",
        "herunterladen*", "entpacke*", "komprimiere*", "sichere*", "liste dateien*",
        "zeige dateien*", "finde datei*", "durchsuche*", "gehe zu*", "navigiere zu*",
        "suche im web*", "suche im internet*", "google", "sende email*", "sende mail*",
        "sende nachricht*", "schicke*", "plane termin*", "erinnere mich*", "stelle timer*",
        "stelle wecker*", "trage in kalender ein*", "mache screenshot*", "klicke*",
        "automatisiere*",
    ],
}

BUILTIN_ROUTINES = (
    "builtin:weather", "builtin:help", "builtin:google", "builtin:browser", "builtin:home",
    "builtin:downloads", "builtin:terminal", "builtin:calculator", "builtin:settings",
)
ACTIONS = ("weather", "help", "answer", "command", "url", "hermes", "llm")

# Built-in rows only add extra keywords (their own detection stays on); the others are fully user-defined.
DEFAULT_ROUTINES = [
    {"id": "builtin:weather", "name": "Weather", "enabled": True, "keywords": [], "action": "weather", "value": ""},
    {"id": "builtin:help", "name": "Help", "enabled": True, "keywords": [], "action": "help", "value": ""},
    {"id": "builtin:google", "name": "Google search", "enabled": True,
     "keywords": ["suche bei google nach", "bei google nach", "google nach", "suche google nach",
                  "google for", "search google for", "google*"],
     "action": "url", "value": "https://www.google.com/search?q={input}"},
    {"id": "builtin:browser", "name": "Open browser", "enabled": True,
     "keywords": ["öffne* browser", "browser öffnen", "open browser", "launch browser", "start browser"],
     "action": "url", "value": "https://www.google.com/"},
    {"id": "builtin:home", "name": "Open home folder", "enabled": True,
     "keywords": ["öffne* home-ordner", "öffne* heimordner", "open home folder", "open home directory"],
     "action": "command", "value": "xdg-open {home}"},
    {"id": "builtin:downloads", "name": "Open Downloads", "enabled": True,
     "keywords": ["öffne* downloads", "öffne* download-ordner", "open downloads folder"],
     "action": "command", "value": "xdg-open {home}/Downloads"},
    {"id": "builtin:terminal", "name": "Open terminal", "enabled": True,
     "keywords": ["öffne* terminal", "starte* terminal", "open terminal", "launch terminal"],
     "action": "command", "value": "x-terminal-emulator"},
    {"id": "builtin:calculator", "name": "Open calculator", "enabled": True,
     "keywords": ["öffne* rechner", "starte* rechner", "open calculator", "launch calculator"],
     "action": "command", "value": "gnome-calculator"},
    {"id": "builtin:settings", "name": "Open system settings", "enabled": True,
     "keywords": ["öffne* systemeinstellungen", "öffne* einstellungen", "open system settings"],
     "action": "command", "value": "gnome-control-center"},
    {"id": "example:search", "name": "Web search", "enabled": True,
     "keywords": ["suche im web nach", "suche im internet nach", "search the web for", "web search"],
     "action": "url", "value": "https://duckduckgo.com/?q={input}"},
    {"id": "example:files", "name": "File manager", "enabled": True,
     "keywords": ["dateimanager", "file manager", "files app"],
     "action": "command", "value": "xdg-open {home}"},
    {"id": "example:translate", "name": "Translate", "enabled": True,
     "keywords": ["\u00fcbersetze*", "translate*"],
     "action": "llm",
     "value": "Translate the following text. If it is German, translate it to English, otherwise to German. "
              "Reply with the translation only:\n{input}"},
]

DEFAULTS = {
    "language": "auto",  # auto | en | de
    "hotkey": "<Control><Alt>space",
    "local_only": False,  # never contact external providers
    "check_components": True,  # offer to install missing LM Studio / Hermes at start
    "autostart_backends": True,  # start local LM Studio server / Hermes gateway in the background when down
    "routines_enabled": True,  # built-in answers without an LLM: weather, help
    "weather_location": "",  # used when a weather question names no place
    "routines": copy.deepcopy(DEFAULT_ROUTINES),  # table in the settings: keywords -> action
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
    "agent_keywords": copy.deepcopy(DEFAULT_AGENT_KEYWORDS),  # per language; matches go to Hermes
}


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def _migrate(cfg: dict) -> dict:
    """Older configs stored one flat keyword list; split it by language."""
    kw = cfg.get("agent_keywords")
    if isinstance(kw, list):
        de = set(DEFAULT_AGENT_KEYWORDS["de"])
        cfg["agent_keywords"] = {
            "en": [k for k in kw if k not in de],
            "de": [k for k in kw if k in de],
        }
    return cfg


def normalize_routines(cfg: dict) -> dict:
    """Drops malformed rows and makes sure the built-in rows exist."""
    rows = []
    for r in cfg.get("routines") or []:
        if not isinstance(r, dict) or r.get("action") not in ACTIONS:
            continue
        rows.append({
            "id": str(r.get("id") or f"custom:{len(rows)}"),
            "name": str(r.get("name") or ""),
            "enabled": bool(r.get("enabled", True)),
            "keywords": [str(k).strip() for k in r.get("keywords", []) if str(k).strip()],
            "action": r["action"],
            "value": str(r.get("value") or ""),
        })
    have = {r["id"] for r in rows}
    rows += [copy.deepcopy(d) for d in DEFAULT_ROUTINES if d["id"] in BUILTIN_ROUTINES and d["id"] not in have]
    cfg["routines"] = rows
    return cfg


def _migrate_routine_flags(raw: dict) -> None:
    """Older configs had two switches instead of the table."""
    if "routines" in raw:
        return
    flags = {"builtin:weather": raw.pop("routine_weather", True), "builtin:help": raw.pop("routine_help", True)}
    if not all(flags.values()):
        raw["routines"] = [dict(d, enabled=flags.get(d["id"], d["enabled"])) for d in DEFAULT_ROUTINES]


def load() -> dict:
    try:
        raw = _migrate(json.loads(CONFIG_FILE.read_text()))
        _migrate_routine_flags(raw)
        return normalize_routines(_merge(DEFAULTS, raw))
    except (OSError, ValueError):
        return normalize_routines(copy.deepcopy(DEFAULTS))


def save(cfg: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_FILE.with_suffix(".tmp")
    # The file may contain API keys: owner-only access.
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(cfg, f, indent=2)
    os.replace(tmp, CONFIG_FILE)
