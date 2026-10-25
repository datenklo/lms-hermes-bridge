from datetime import date, timedelta

from lms_hermes_bridge import routines
from lms_hermes_bridge.config import DEFAULTS
import copy

TODAY = date(2026, 10, 25)


def cfg(**over):
    c = copy.deepcopy(DEFAULTS)
    c.update(over)
    return c


def fake_fetch(rain_first=True, results=None):
    calls = []

    def fetch(url):
        calls.append(url)
        if "geocoding" in url:
            res = results if results is not None else [
                {"name": "Berlin", "latitude": 52.5, "longitude": 13.4, "admin1": "Berlin", "country": "Deutschland"}]
            return {"results": res}
        n = 16
        return {
            "current": {"temperature_2m": 12.3, "apparent_temperature": 10.1, "weather_code": 3, "wind_speed_10m": 9},
            "daily": {
                "time": [(TODAY + timedelta(i)).isoformat() for i in range(n)],
                "weather_code": [63 if rain_first else 0] + [0] * (n - 1),
                "temperature_2m_max": [14] * n, "temperature_2m_min": [7] * n,
                "precipitation_probability_max": [80 if rain_first else 0] + [10] * (n - 1),
                "precipitation_sum": [3.2 if rain_first else 0] + [0] * (n - 1),
                "wind_speed_10m_max": [20] * n,
            },
        }
    fetch.calls = calls
    return fetch


def run(prompt, fetch=None, **cfg_over):
    return routines.handle(prompt, cfg(**cfg_over), fetch=fetch or fake_fetch(), today=TODAY,
                           probe=lambda c: {"lmstudio": 5, "hermes": None})


# --- parsing -------------------------------------------------------------
def test_location_variants():
    cases = {
        "Wie soll das Wetter werden in Berlin?": "Berlin",
        "Wetter Berlin": "Berlin",
        "Wie wird das Wetter in Frankfurt am Main?": "Frankfurt am Main",
        "What will the weather be like in New York": "New York",
        "weather in Springfield, Illinois": "Springfield, Illinois",
        "Wetter in den nächsten Tagen": None,
        "Wie ist das Wetter": None,
    }
    for prompt, want in cases.items():
        _, _, rest, _ = routines._parse_when(prompt, TODAY)
        assert routines.extract_location(rest) == want, prompt


def test_time_variants():
    p = lambda s: routines._parse_when(s, TODAY)  # noqa: E731
    assert p("Wetter in Berlin")[0] == [0, 1] and p("Wetter in Berlin")[1] == "default"
    assert p("Wetter morgen in Berlin")[0] == [1]
    assert p("Wetter übermorgen")[0] == [2]
    assert p("weather tomorrow")[0] == [1]
    assert p("Wetter in 3 Tagen in Wien")[0] == [3]
    assert p("Wetter jetzt in Wien")[1] == "now"
    assert len(p("Wetter in den nächsten Tagen")[0]) == 7
    assert p("Wetter am Wochenende")[0] == [0, 6]  # 2026-10-25 is a Sunday: today plus next Saturday
    assert p("Wetter am 28.10. in Wien")[0] == [3]
    assert p("Wetter am Montag")[0] == [1]
    assert "range" in p("Wetter in 30 Tagen")[3] and p("Wetter in 30 Tagen")[0] == [0, 1]
    assert "past" in p("Wetter am 20.10.2026")[3]


# --- weather answers -------------------------------------------------------
def test_weather_answer_contains_place_and_days():
    r = run("Wie soll das Wetter werden in Berlin?")
    assert r.name == "weather" and r.lang == "de"
    assert "Wetter für Berlin" in r.text and "Heute:" in r.text and "Morgen:" in r.text and "Jetzt:" in r.text
    assert "Regen" in r.text and "80 %" in r.text


def test_rain_question_headline_and_english():
    assert run("Regnet es morgen in Berlin?").text.splitlines()[1].startswith("Nein") is True  # day 1: 10 %
    r = run("Will it rain today in Berlin?")
    assert r.lang == "en" and "Yes, rain is expected" in r.text


def test_no_place_uses_default_or_asks():
    f = fake_fetch()
    assert "Für welchen Ort" in run("Wie ist das Wetter morgen?", f).text and f.calls == []
    assert "Wetter für Berlin" in run("Wie ist das Wetter morgen?", fake_fetch(), weather_location="Berlin").text


def test_unknown_place_ambiguous_and_errors():
    assert "nicht gefunden" in run("Wetter in Xyzzyville", fake_fetch(results=[])).text
    res = [{"name": "Springfield", "latitude": 1, "longitude": 1, "admin1": "Missouri", "country": "USA"},
           {"name": "Springfield", "latitude": 2, "longitude": 2, "admin1": "Illinois", "country": "USA"}]
    assert "Illinois" in run("weather in Springfield, Illinois", fake_fetch(results=res)).text

    def boom(url):
        raise routines.RoutineError("offline")
    assert "nicht erreichbar" in run("Wetter in Berlin", boom).text


def test_local_only_blocks_network():
    f = fake_fetch()
    r = run("Wetter in Berlin", f, local_only=True)
    assert "Nur-lokal" in r.text and f.calls == []


# --- help ------------------------------------------------------------------
def test_help_triggers():
    for p in ["Was kann dieses Tool?", "Was kann dieses Tool alles", "Was kannst du?", "Hilfe", "help",
              "What can this tool do?", "what does this app do", "Wie funktioniert das?"]:
        r = run(p)
        assert r and r.name == "help", p
    assert "Status" in run("Was kann dieses Tool?").text and "5 Modelle" in run("Was kann dieses Tool?").text
    assert "What LMS Hermes Bridge can do" in run("What can this tool do?").text


def test_help_topics_and_hotkey_formatting():
    assert "Ctrl+Alt+Space" in run("Wie ändere ich den Hotkey?").text
    assert "Claude" in run("Hilfe externe Modelle").text
    assert "Stichwörter" in run("help keywords").text or "keywords" in run("help keywords").text
    assert routines.pretty_hotkey("<Control><Alt>space") == "Ctrl+Alt+Space"
    assert routines.pretty_hotkey("<Super>F1") == "Super+F1"


def test_no_false_positives_and_switch():
    for p in ["Schreibe eine E-Mail an meinen Chef", "help me write a poem about rain", "Hilf mir bei meinem Python-Skript",
              "Erkläre den Regenbogen", "Öffne den Browser"]:
        assert run(p) is None, p
    assert run("Was kann dieses Tool?", routines_enabled=False) is None
