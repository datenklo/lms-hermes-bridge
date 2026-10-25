"""Routines answered before any model is asked: built-in weather/help and user-defined table rows.

Pure parsing plus injectable I/O (`fetch`, `probe`, `opener`, `launcher`) so everything is unit-testable.
"""
import json
import re
import shlex
import subprocess
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from . import i18n
from .config import DEFAULT_ROUTINES
from .keywords import find

GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
MAX_DAYS = 16


@dataclass
class Result:
    name: str  # weather | help | custom
    lang: str
    text: str
    label: str = ""  # status-line name; empty means the localized built-in name


@dataclass
class Redirect:
    """A routine that rewrites the prompt and hands it to the normal pipeline."""
    prompt: str
    backend: str  # hermes | auto
    label: str


class RoutineError(Exception):
    pass


# ---------------------------------------------------------------- language
_DE = re.compile(r"\b(wetter|wie|was|wird|werden|soll|heute|morgen|übermorgen|ich|der|die|das|kann|kannst|hilfe|"
                 r"regnet|nächste|nächsten|für|bei|ist|es|schnee|sonnig|und|mir|mal|bitte|dieses|ändere)\b", re.I)
_EN = re.compile(r"\b(weather|will|what|how|the|tomorrow|today|rain|is|it|can|help|for|next|this|and|me|please|"
                 r"change|does|do|you)\b", re.I)


def detect_lang(prompt: str) -> str:
    de, en = len(_DE.findall(prompt)), len(_EN.findall(prompt))
    if de != en:
        return "de" if de > en else "en"
    cur = i18n.current()
    return cur if cur in ("de", "en") else "en"


# ----------------------------------------------------------------- weather
WEATHER_WORD = re.compile(r"\b(wetter\w*|vorhersage|weather|forecast)\b", re.I)
PRECIP_WORD = re.compile(r"\b(regnet|regnen|regen|schnee|schneit|schneien|gewitter|hagel|rain|raining|snow|snowing|"
                         r"thunderstorm|umbrella|schirm|temperatur|temperature)\b", re.I)
RAIN_WORD = re.compile(r"\b(regnet|regnen|regen|schirm|rain|raining|umbrella)\b", re.I)
SNOW_WORD = re.compile(r"\b(schnee|schneit|schneien|snow|snowing)\b", re.I)
SNOW_CODES = {71, 73, 75, 77, 85, 86}

WMO = {
    0: ("klar", "clear sky"), 1: ("überwiegend klar", "mostly clear"), 2: ("teils bewölkt", "partly cloudy"),
    3: ("bedeckt", "overcast"), 45: ("Nebel", "fog"), 48: ("Nebel mit Reif", "rime fog"),
    51: ("leichter Nieselregen", "light drizzle"), 53: ("Nieselregen", "drizzle"),
    55: ("starker Nieselregen", "heavy drizzle"), 56: ("gefrierender Nieselregen", "freezing drizzle"),
    57: ("gefrierender Nieselregen", "freezing drizzle"), 61: ("leichter Regen", "light rain"),
    63: ("Regen", "rain"), 65: ("starker Regen", "heavy rain"), 66: ("gefrierender Regen", "freezing rain"),
    67: ("gefrierender Regen", "freezing rain"), 71: ("leichter Schneefall", "light snow"),
    73: ("Schneefall", "snow"), 75: ("starker Schneefall", "heavy snow"), 77: ("Schneegriesel", "snow grains"),
    80: ("leichte Schauer", "light showers"), 81: ("Schauer", "showers"), 82: ("heftige Schauer", "violent showers"),
    85: ("Schneeschauer", "snow showers"), 86: ("starke Schneeschauer", "heavy snow showers"),
    95: ("Gewitter", "thunderstorm"), 96: ("Gewitter mit Hagel", "thunderstorm with hail"),
    99: ("Gewitter mit Hagel", "thunderstorm with hail"),
}

WEEKDAYS = [
    ("montag", "monday"), ("dienstag", "tuesday"), ("mittwoch", "wednesday"), ("donnerstag", "thursday"),
    ("freitag", "friday"), ("samstag", "saturday"), ("sonntag", "sunday"),
]
WD_SHORT = {"de": ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"], "en": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]}

_WD_RE = re.compile(
    r"\b(?:am\s+|on\s+|next\s+|nächsten\s+|kommenden\s+)?(" + "|".join(f"{d}|{e}" for d, e in WEEKDAYS) + r")\b", re.I)
_WD_INDEX = {w: i for i, pair in enumerate(WEEKDAYS) for w in pair}


def _parse_when(text: str, today: date):
    """Returns (offsets, kind, rest, notes); kind is 'now', 'days' or 'default'."""
    offs: set[int] = set()
    notes: list[str] = []
    kind = "days"

    def take(rx, fn):
        nonlocal text
        while (m := rx.search(text)):
            fn(m)
            text = text[:m.start()] + " " + text[m.end():]

    take(re.compile(r"\b(?:übermorgen|day after tomorrow)\b", re.I), lambda m: offs.add(2))
    take(re.compile(r"\b(?:morgen|tomorrow)\b", re.I), lambda m: offs.add(1))
    take(re.compile(r"\b(?:heute|today|tonight)(?:\s+(?:abend|nacht|früh))?\b", re.I), lambda m: offs.add(0))

    def now(_m):
        nonlocal kind
        kind = "now"
        offs.add(0)
    take(re.compile(r"\b(?:jetzt|aktuell\w*|gerade|derzeit|momentan|now|currently|right now)\b", re.I), now)

    def weekend(_m):
        offs.update([d for d in range(7) if (today + timedelta(d)).weekday() in (5, 6)][:2])
    take(re.compile(r"\b(?:am\s+)?(?:wochenende|(?:this\s+)?weekend)\b", re.I), weekend)

    def week(m):
        s = m.group(0).lower()
        if ("nächste woche" in s or "naechste woche" in s or "next week" in s):
            start = 7 - today.weekday()
            offs.update(range(start, start + 7))
        else:
            offs.update(range(0, 7))
    take(re.compile(r"\b(?:(?:diese|kommende|nächste|naechste|this|next|coming)\s+(?:woche|week)|"
                    r"(?:die\s+)?(?:nächsten|kommenden)\s+tage?n?|next\s+(?:few\s+)?days|7[- ]?tage|seven days)\b",
                    re.I), week)

    def weekday(m):
        off = (_WD_INDEX[m.group(1).lower()] - today.weekday()) % 7
        offs.add(off or 7)
    take(_WD_RE, weekday)
    take(re.compile(r"\bin\s+(\d{1,2})\s+(?:tagen|tage|days?)\b", re.I), lambda m: offs.add(int(m.group(1))))

    def dated(m):
        day, mon, yr = int(m.group(1)), int(m.group(2)), m.group(3)
        try:
            year = int(yr) + (2000 if yr and len(yr) == 2 else 0) if yr else today.year
            d = date(year, mon, day)
            if not yr and d < today:
                d = date(year + 1, mon, day)
            offs.add((d - today).days)
        except ValueError:
            notes.append("bad_date")
    take(re.compile(r"\b(?:am\s+)?(\d{1,2})\.(\d{1,2})\.(\d{2,4})?"), dated)

    if not offs:
        offs, kind = {0, 1}, "default"
    if any(o < 0 for o in offs):
        notes.append("past")
    if any(o >= MAX_DAYS for o in offs):
        notes.append("range")
    valid = sorted(o for o in offs if 0 <= o < MAX_DAYS)
    if not valid:
        valid, kind = [0, 1], "default"
    return valid, kind, text, notes


_STOP = set("""wie wird werden soll sollte das der die den dem ein eine es ist sein bitte wetter wettervorhersage
vorhersage und oder mir mal zeige zeig gib sag sage was what whats how is will be the a an like tell me show give
weather forecast for regnet regen schnee rain snow temperatur temperature gewitter hagel schirm umbrella wird's
gibt it im in at near of um bei für fuer nahe around""".split())
_STOP_END = set("wird werden sein ist soll sollte es wetter weather be like und and oder or regnet regen rain".split())
_BAD_START = set("""den dem der die das the next nächsten kommenden diesem diesen this these einer eine a an my meiner
meinem meinen""".split())
_PREP = re.compile(r"\b(?:in|im|für|fuer|bei|nahe|um|at|for|near|around)\s+(?=\S)", re.I)


def extract_location(rest: str) -> str | None:
    for m in _PREP.finditer(rest):
        cand = re.split(r"[?!;]", rest[m.end():])[0]
        tokens = []
        for tok in cand.split():
            if tok.strip(",.").lower() in _STOP_END:
                break
            tokens.append(tok)
        loc = " ".join(tokens).strip(" ,.")
        if loc and loc.split()[0].strip(",").lower() not in _BAD_START:
            return loc
    tokens = [w.strip(",.?!") for w in rest.split()]
    tokens = [w for w in tokens if w and w.lower() not in _STOP]
    return " ".join(tokens) if 1 <= len(tokens) <= 4 else None


def _http_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "lms-hermes-bridge"})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            return json.load(r)
    except (OSError, ValueError) as e:
        raise RoutineError(str(e)) from e


def geocode(query: str, lang: str, fetch) -> dict | None:
    """'Springfield, Illinois' narrows the result list by the parts after the comma."""
    name, *qual = [p.strip() for p in query.split(",")]
    url = f"{GEO_URL}?{urllib.parse.urlencode({'name': name, 'count': 10, 'language': lang, 'format': 'json'})}"
    results = fetch(url).get("results") or []
    wanted = [q.lower() for q in qual if q]
    for r in results:
        hay = " ".join(str(r.get(k, "")) for k in ("admin1", "admin2", "country", "country_code")).lower()
        if all(q in hay for q in wanted):
            return r
    return None


W = {
    "de": {
        "need_place": "Für welchen Ort? Beispiel: „Wie wird das Wetter morgen in Berlin?“ "
                      "(In den Einstellungen kannst du einen Standardort festlegen.)",
        "not_found": "Ort „{q}“ nicht gefunden. Bitte Stadt (ggf. mit Land oder Region) angeben, "
                     "z. B. „Wetter in Springfield, Illinois“.",
        "unreachable": "Der Wetterdienst (Open-Meteo) ist nicht erreichbar: {err}",
        "local_only": "Der Nur-lokal-Modus ist aktiv. Für das Wetter wäre eine Internetabfrage (Open-Meteo) nötig.",
        "header": "Wetter für {place}", "now": "Jetzt", "feels": "gefühlt {t} °C", "wind": "Wind {w} km/h",
        "wind_max": "Wind bis {w} km/h", "precip": "Niederschlag {p} % ({mm} mm)",
        "days": ["Heute", "Morgen", "Übermorgen"],
        "past": "Vergangene Tage kann ich nicht abfragen.",
        "range": f"Die Vorhersage reicht nur {MAX_DAYS} Tage; spätere Tage wurden übersprungen.",
        "bad_date": "Ein Datum konnte ich nicht lesen.",
        "none": "Für diesen Zeitraum liegt keine Vorhersage vor.",
        "rain_yes": "Ja, mit Regen ist zu rechnen ({p} %, ca. {mm} mm).",
        "rain_maybe": "Eher nicht, aber möglich ({p} %).", "rain_no": "Nein, kaum Regen zu erwarten ({p} %).",
        "snow_yes": "Ja, Schnee ist möglich.", "snow_no": "Nein, kein Schnee in Sicht.",
        "date": "%d.%m.", "wmo": 0,
    },
    "en": {
        "need_place": "For which place? Example: “What will the weather be like in Berlin tomorrow?” "
                      "(You can set a default location in the settings.)",
        "not_found": "Place “{q}” not found. Please give a city (optionally with country or region), "
                     "e.g. “weather in Springfield, Illinois”.",
        "unreachable": "The weather service (Open-Meteo) is not reachable: {err}",
        "local_only": "Local-only mode is on. The weather needs an internet request (Open-Meteo).",
        "header": "Weather for {place}", "now": "Now", "feels": "feels like {t} °C", "wind": "wind {w} km/h",
        "wind_max": "wind up to {w} km/h", "precip": "precipitation {p} % ({mm} mm)",
        "days": ["Today", "Tomorrow", "Day after tomorrow"],
        "past": "I cannot look up past days.",
        "range": f"The forecast only covers {MAX_DAYS} days; later days were skipped.",
        "bad_date": "I could not read a date.",
        "none": "There is no forecast for that period.",
        "rain_yes": "Yes, rain is expected ({p} %, about {mm} mm).",
        "rain_maybe": "Probably not, but it is possible ({p} %).", "rain_no": "No, hardly any rain expected ({p} %).",
        "snow_yes": "Yes, snow is possible.", "snow_no": "No, no snow in sight.",
        "date": "%m/%d", "wmo": 1,
    },
}


def _num(v, digits=0):
    return "–" if v is None else (f"{v:.{digits}f}" if digits else f"{round(v)}")


def weather(prompt: str, cfg: dict, lang: str, fetch, today: date) -> Result:
    w = W[lang]
    if cfg.get("local_only"):
        return Result("weather", lang, w["local_only"])
    offsets, kind, rest, notes = _parse_when(prompt, today)
    place = extract_location(rest) or (cfg.get("weather_location") or "").strip()
    if not place:
        return Result("weather", lang, w["need_place"])
    try:
        geo = geocode(place, lang, fetch)
        if not geo:
            return Result("weather", lang, w["not_found"].format(q=place))
        q = urllib.parse.urlencode({
            "latitude": geo["latitude"], "longitude": geo["longitude"], "timezone": "auto",
            "forecast_days": MAX_DAYS,
            "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,"
                     "precipitation_sum,wind_speed_10m_max",
        }, safe=",")
        data = fetch(f"{FORECAST_URL}?{q}")
    except RoutineError as e:
        return Result("weather", lang, w["unreachable"].format(err=e))

    desc = lambda code: WMO.get(code, ("–", "–"))[w["wmo"]]  # noqa: E731
    region = ", ".join(dict.fromkeys(str(geo[k]) for k in ("name", "admin1", "country") if geo.get(k)))
    lines = [w["header"].format(place=region)]

    cur = data.get("current") or {}
    if kind in ("now", "default") and cur:
        lines.append(f"{w['now']}: {_num(cur.get('temperature_2m'))} °C, {desc(cur.get('weather_code'))} · "
                     f"{w['feels'].format(t=_num(cur.get('apparent_temperature')))} · "
                     f"{w['wind'].format(w=_num(cur.get('wind_speed_10m')))}")

    daily = data.get("daily") or {}
    times = daily.get("time") or []
    rows = []
    if kind != "now" and times:
        base = date.fromisoformat(times[0])
        for off in offsets:
            idx = (today + timedelta(off) - base).days
            if not 0 <= idx < len(times):
                continue
            d = date.fromisoformat(times[idx])
            label = w["days"][off] if off < 3 else f"{WD_SHORT[lang][d.weekday()]}, {d.strftime(w['date'])}"
            if off < 3 and kind != "default":
                label += f" ({WD_SHORT[lang][d.weekday()]}, {d.strftime(w['date'])})"
            prob, mm = daily["precipitation_probability_max"][idx], daily["precipitation_sum"][idx]
            rows.append((off, idx, f"{label}: {desc(daily['weather_code'][idx])} · "
                         f"{_num(daily['temperature_2m_min'][idx])}–{_num(daily['temperature_2m_max'][idx])} °C · "
                         f"{w['precip'].format(p=_num(prob), mm=_num(mm, 1))} · "
                         f"{w['wind_max'].format(w=_num(daily['wind_speed_10m_max'][idx]))}"))
        if not rows:
            lines.append(w["none"])
        else:
            first_idx = rows[0][1]
            headline = None
            if SNOW_WORD.search(prompt):
                snow = daily["weather_code"][first_idx] in SNOW_CODES
                headline = w["snow_yes" if snow else "snow_no"]
            elif RAIN_WORD.search(prompt):
                prob, mm = daily["precipitation_probability_max"][first_idx], daily["precipitation_sum"][first_idx]
                key = "rain_yes" if (prob or 0) >= 50 or (mm or 0) >= 1 else "rain_maybe" if (prob or 0) >= 20 else "rain_no"
                headline = w[key].format(p=_num(prob), mm=_num(mm, 1))
            if headline:
                lines.insert(1, headline)
            lines.append("")
            lines.extend(r[2] for r in rows)
    lines.extend(w[n] for n in dict.fromkeys(notes) if n in w)
    return Result("weather", lang, "\n".join(lines).strip())


def is_weather(prompt: str) -> bool:
    words = len(prompt.split())
    if words > 25:
        return False
    if WEATHER_WORD.search(prompt):
        return True
    # Rain/snow words alone are too generic; require a time word or a place hint.
    return bool(PRECIP_WORD.search(prompt) and re.search(
        r"\b(heute|morgen|übermorgen|today|tomorrow|tonight|wochenende|weekend|in|im|bei|at|near)\b", prompt, re.I)
        and words <= 12)


# -------------------------------------------------------------------- help
_HELP_STRONG = re.compile(
    r"\bwas\s+(?:kann|kannst|macht|ist|bietet|bedeutet)\s+(?:man\s+)?(?:(?:dieses|dieser|diese|das|die|der|dein)\s+)?"
    r"(?:\w+\s+)?(?:tool|app|programm|anwendung|bridge|software|ding)\b|\bwas\s+kannst\s+du\b|"
    r"\bwas\s+kann\s+(?:man|ich)\s+(?:hier|damit)\b|\bwhat\s+can\s+(?:this|you|i)\b|"
    r"\bwhat\s+(?:does|is)\s+this\s+(?:tool|app|program|thing)\b|\bwhat\s+do\s+you\s+do\b|"
    r"\bhow\s+(?:does|do)\s+(?:this|it|i\s+use)\b|\bwie\s+funktioniert\s+(?:das|dieses|die|der)\b", re.I)
_HELP_WEAK = re.compile(r"\b(hilfe|anleitung|funktionen|funktionsumfang|befehle|help(?!\s+(?:me|us|with))|features)\b",
                        re.I)
_HOWTO = re.compile(r"\b(wie|how|wo|where)\b.*\b(änder\w*|stell\w*|einstell\w*|konfigur\w*|hinzufüg\w*|einricht\w*|"
                    r"aktivier\w*|change|set|configure|add|enable|setup|use)\b", re.I)
TOPICS = {
    "hotkey": re.compile(r"\b(hotkey|tastenkombination|tastenkombi|tastenkürzel|shortcut)s?\b", re.I),
    "providers": re.compile(r"\b(claude|chatgpt|openai|anthropic|copilot|api[- ]?(?:schlüssel|key)|"
                            r"externe?[nr]?\s+modelle?|external\s+models?|provider|anbieter)\b", re.I),
    "hermes": re.compile(r"\bhermes\b", re.I),
    "local": re.compile(r"\b(nur[- ]lokal|local[- ]only|datenschutz|privacy|offline)\b", re.I),
    "keywords": re.compile(r"\b(stichwörter|stichwort|keywords?)\b", re.I),
    "models": re.compile(r"\b(lm[- ]?studio|modell\w*|models?)\b", re.I),
    "weather": re.compile(r"\b(wetter|weather)\b", re.I),
}

H = {
    "de": {
        "overview": (
            "Das kann LMS Hermes Bridge:\n\n"
            "• Fragen und Aufgaben per Tastenkombination ({hotkey}), wie ein Suchfenster.\n"
            "• Wählt automatisch das passende LM-Studio-Modell (schnell, ausgewogen, tief, Code) und lädt es bei Bedarf.\n"
            "• Aktionen am Rechner (öffnen, installieren, Dateien, …) gehen an Hermes.\n"
            "• Externe Modelle (Claude, ChatGPT, Copilot) per Rechtsklick → Einstellungen.\n"
            "• Nur-lokal-Modus: keine Anfrage verlässt den Rechner.\n"
            "• Routinen ohne Modell: Wetter („Wie wird das Wetter morgen in Berlin?“) und diese Hilfe.\n\n"
            "Status:\n{status}\n\n"
            "Mehr dazu: „Hilfe Hotkey“, „Hilfe externe Modelle“, „Hilfe Hermes“, „Hilfe Nur lokal“, "
            "„Hilfe Stichwörter“, „Hilfe Wetter“."),
        "status_lms": "• LM Studio: {s}", "lms_up": "läuft ({n} Modelle)", "lms_down": "nicht erreichbar",
        "status_hermes": "• Hermes: {s}", "h_up": "läuft", "h_down": "aktiviert, aber nicht erreichbar",
        "h_off": "nicht aktiviert", "status_prov": "• Externe Anbieter: {n}",
        "status_local": "• Nur lokal: {s}", "on": "an", "off": "aus",
        "hotkey": "Die Tastenkombination ({hotkey}) öffnet das Fenster. Ändern: Rechtsklick auf das Fenster oder "
                  "das Tray-Symbol → Einstellungen → Allgemein → „Globale Tastenkombination“ → "
                  "„Tastenkombination registrieren“ (GNOME-Schreibweise, z. B. <Control><Alt>space).",
        "providers": "Externe Modelle: Einstellungen → „Externe Modelle“ → Vorlage wählen (Claude, ChatGPT, Copilot) "
                     "oder eigenen Endpunkt anlegen, API-Schlüssel und Modell eintragen. Verwendbar als feste Route "
                     "(Einstellungen → Routing) oder als Ersatz, wenn LM Studio nicht läuft.",
        "hermes": "Hermes bekommt Aktionsaufgaben (öffnen, installieren, Dateien …). Einrichten: API-Server in Hermes "
                  "aktivieren, dann Einstellungen → Hermes → aktivieren, URL und Schlüssel eintragen. Welche Anfragen "
                  "an Hermes gehen, steuert die Liste unter „Hermes-Stichwörter“.",
        "local": "Nur lokal: Einstellungen → Allgemein → „Nur lokal“. Dann werden keine externen APIs genutzt und "
                 "auch die Wetter-Routine (Internet) ist aus.",
        "keywords": "Hermes-Stichwörter: Einstellungen → Hermes-Stichwörter, ein Eintrag pro Zeile. Ein * am Ende "
                    "erfasst Wortformen (installier*). Es wird die Liste der aktuellen Sprache angezeigt.",
        "models": "LM Studio: Die Bridge wählt je Anfrage das Modell (schnell/ausgewogen/tief/Code) und lädt es mit "
                  "passendem Kontext. Feste Modelle pro Stufe: Einstellungen → LM Studio. Der Server wird bei Bedarf "
                  "automatisch gestartet.",
        "weather": "Wetter: z. B. „Wie wird das Wetter morgen in Berlin?“, „Regnet es am Wochenende in Hamburg?“, "
                   "„Wetter in Springfield, Illinois“, „Wetter in 3 Tagen in Wien“. Ohne Ortsangabe wird der "
                   "Standardort aus den Einstellungen genutzt. Datenquelle: Open-Meteo (Internet nötig).",
    },
    "en": {
        "overview": (
            "What LMS Hermes Bridge can do:\n\n"
            "• Questions and tasks via a hotkey ({hotkey}), like a search window.\n"
            "• Automatically picks the right LM Studio model (fast, balanced, deep, code) and loads it on demand.\n"
            "• Actions on your computer (open, install, files, …) go to Hermes.\n"
            "• External models (Claude, ChatGPT, Copilot) via right-click → Settings.\n"
            "• Local-only mode: no request leaves your machine.\n"
            "• Routines without a model: weather (“What will the weather be like in Berlin tomorrow?”) and this help.\n\n"
            "Status:\n{status}\n\n"
            "More: “help hotkey”, “help external models”, “help Hermes”, “help local only”, “help keywords”, "
            "“help weather”."),
        "status_lms": "• LM Studio: {s}", "lms_up": "running ({n} models)", "lms_down": "not reachable",
        "status_hermes": "• Hermes: {s}", "h_up": "running", "h_down": "enabled but not reachable",
        "h_off": "not enabled", "status_prov": "• External providers: {n}",
        "status_local": "• Local only: {s}", "on": "on", "off": "off",
        "hotkey": "The hotkey ({hotkey}) opens the window. Change it: right-click the window or tray icon → Settings "
                  "→ General → “Global hotkey” → “Register hotkey” (GNOME notation, e.g. <Control><Alt>space).",
        "providers": "External models: Settings → “External models” → pick a preset (Claude, ChatGPT, Copilot) or a "
                     "custom endpoint, enter API key and model. Use them as a fixed route (Settings → Routing) or as "
                     "fallback when LM Studio is down.",
        "hermes": "Hermes gets action tasks (open, install, files …). Set up: enable the API server in Hermes, then "
                  "Settings → Hermes → enable, enter URL and key. The “Hermes keywords” list controls which requests "
                  "go to Hermes.",
        "local": "Local only: Settings → General → “Local only”. External APIs are never used and the weather routine "
                 "(internet) is off too.",
        "keywords": "Hermes keywords: Settings → Hermes keywords, one entry per line. A trailing * matches word "
                    "forms (install*). The list of the current language is shown.",
        "models": "LM Studio: the bridge picks the model per request (fast/balanced/deep/code) and loads it with a "
                  "suitable context. Fixed models per tier: Settings → LM Studio. The server is started "
                  "automatically when needed.",
        "weather": "Weather: e.g. “What will the weather be like in Berlin tomorrow?”, “Will it rain in Hamburg this "
                   "weekend?”, “weather in Springfield, Illinois”, “weather in 3 days in Vienna”. Without a place the "
                   "default location from the settings is used. Source: Open-Meteo (needs internet).",
    },
}


def pretty_hotkey(accel: str) -> str:
    mods = [{"Control": "Ctrl", "Primary": "Ctrl"}.get(m, m) for m in re.findall(r"<(\w+)>", accel)]
    key = re.sub(r"<\w+>", "", accel).strip()
    return "+".join(mods + [key.capitalize() if len(key) > 1 else key.upper()]) if key else accel


def default_probe(cfg: dict) -> dict:
    from . import lmstudio, services
    models = lmstudio.list_models(cfg["lmstudio"]["url"])
    return {
        "lmstudio": None if models is None else len([m for m in models if m.is_chat]),
        "hermes": services.hermes_up(cfg) if cfg["hermes"]["enabled"] else None,
    }


def _status(cfg: dict, h: dict, probe) -> str:
    p = probe(cfg)
    lms = h["lms_up"].format(n=p["lmstudio"]) if p["lmstudio"] is not None else h["lms_down"]
    hermes = h["h_off"] if p["hermes"] is None else h["h_up"] if p["hermes"] else h["h_down"]
    providers = len([x for x in cfg["providers"] if x.get("enabled", True)])
    return "\n".join([
        h["status_lms"].format(s=lms), h["status_hermes"].format(s=hermes), h["status_prov"].format(n=providers),
        h["status_local"].format(s=h["on" if cfg["local_only"] else "off"]),
    ])


def help_result(prompt: str, cfg: dict, lang: str, probe) -> Result:
    h = H[lang]
    hotkey = pretty_hotkey(cfg.get("hotkey", ""))
    for topic, rx in TOPICS.items():
        if rx.search(prompt):
            return Result("help", lang, h[topic].format(hotkey=hotkey) if topic == "hotkey" else h[topic])
    return Result("help", lang, h["overview"].format(hotkey=hotkey, status=_status(cfg, h, probe)))


def is_help(prompt: str) -> bool:
    words = len(prompt.split())
    return bool((words <= 12 and _HELP_STRONG.search(prompt))
                or (words <= 5 and _HELP_WEAK.search(prompt))
                or (words <= 14 and _HOWTO.search(prompt) and any(r.search(prompt) for r in TOPICS.values())))


# ------------------------------------------------------------ user routines
R = {
    "de": {
        "empty": "Für diese Routine ist keine Aktion hinterlegt.",
        "started": "Gestartet: {cmd}", "opened": "Geöffnet: {url}",
        "not_found": "Programm nicht gefunden oder nicht ausführbar: {cmd}",
        "bad_command": "Der Befehl ist ungültig (Anführungszeichen prüfen).",
        "bad_url": "Nur http-, https- und mailto-Adressen sind erlaubt.",
    },
    "en": {
        "empty": "This routine has no action configured.",
        "started": "Started: {cmd}", "opened": "Opened: {url}",
        "not_found": "Program not found or not executable: {cmd}",
        "bad_command": "The command is invalid (check the quotes).",
        "bad_url": "Only http, https and mailto addresses are allowed.",
    },
}
_TOKEN = re.compile(r"\{(input|prompt|home|date|time)\}")


def input_text(prompt: str, match: re.Match) -> str:
    """The prompt without the matched keyword, e.g. 'suche im web nach Katzen' -> 'Katzen'."""
    rest = re.sub(r"\s+", " ", prompt[:match.start()] + " " + prompt[match.end():])
    return rest.strip(" \t,.:;!?\"'„“")


def fill(template: str, prompt: str, text: str, quote: bool = False) -> str:
    """Replaces {input} {prompt} {home} {date} {time}; one pass, so inserted text is never re-expanded."""
    now = datetime.now()
    values = {
        "input": text, "prompt": prompt, "home": str(Path.home()),
        "date": now.strftime("%Y-%m-%d"), "time": now.strftime("%H:%M"),
    }
    def repl(m):
        v = values[m.group(1)]
        return urllib.parse.quote_plus(v) if quote and m.group(1) in ("input", "prompt") else v
    return _TOKEN.sub(repl, template)


def _spawn(argv: list[str]) -> None:
    subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)


def _google_query(prompt: str, match: re.Match) -> str:
    query = prompt[match.end():].strip(" \t,.:;!?\"'„“")
    query = re.sub(r"\s+(?:gesucht|suchen|search(?:ed)?|finden|soll(?:en)?|werden|wird)\b.*$", "", query,
                   flags=re.I).strip(" \t,.:;!?\"'„“")
    return query


def run_custom(row: dict, prompt: str, match: re.Match, lang: str, launcher=None,
               input_override: str | None = None) -> Result | Redirect:
    m, spawn = R[lang], launcher or _spawn
    action, value, label = row["action"], row.get("value", "").strip(), row.get("name") or row["action"]
    if row.get("id") == "builtin:google":
        label = i18n.t("routine_google")
    text = input_text(prompt, match) if input_override is None else input_override
    if not value:
        return Result("custom", lang, m["empty"], label)
    if action == "answer":
        return Result("custom", lang, fill(value, prompt, text), label)
    if action in ("hermes", "llm"):
        return Redirect(fill(value, prompt, text), "hermes" if action == "hermes" else "auto", label)
    try:
        if action == "url":
            url = fill(value, prompt, text, quote=True)
            if urllib.parse.urlparse(url).scheme not in ("http", "https", "mailto"):
                return Result("custom", lang, m["bad_url"], label)
            spawn(["xdg-open", url])
            return Result("custom", lang, m["opened"].format(url=url), label)
        # No shell: every argument is substituted separately, so typed text cannot inject commands.
        argv = [Path(a).expanduser().as_posix() if a.startswith("~") else a
                for a in (fill(a, prompt, text) for a in shlex.split(value))]
        if not argv:
            return Result("custom", lang, m["empty"], label)
        spawn(argv)
        return Result("custom", lang, m["started"].format(cmd=shlex.join(argv)), label)
    except ValueError:
        return Result("custom", lang, m["bad_command"], label)
    except OSError:
        return Result("custom", lang, m["not_found"].format(cmd=value.split()[0] if value.split() else value), label)


# ------------------------------------------------------------------ entry
def handle(prompt: str, cfg: dict, fetch=None, probe=None, today: date | None = None,
           launcher=None) -> Result | Redirect | None:
    """Returns a Result/Redirect when a routine answers the prompt, else None.

    User-defined rows are checked first (explicit intent), then the built-ins, which also accept extra keywords.
    """
    if not cfg.get("routines_enabled", True):
        return None
    rows = [r for r in cfg.get("routines", DEFAULT_ROUTINES) if r.get("enabled", True)]
    lang = detect_lang(prompt)
    for r in rows:
        if r["action"] in ("weather", "help"):
            continue
        match = find(prompt, r.get("keywords", []))
        if match:
            extra = _google_query(prompt, match) if r["id"] == "builtin:google" else None
            return run_custom(r, prompt, match, lang, launcher, extra)
    for r in rows:
        extra = find(prompt, r.get("keywords", []))
        if r["action"] == "help" and (extra or is_help(prompt)):
            return help_result(prompt, cfg, lang, probe or default_probe)
        if r["action"] == "weather" and (extra or is_weather(prompt)):
            return weather(prompt, cfg, lang, fetch or _http_json, today or date.today())
    return None
