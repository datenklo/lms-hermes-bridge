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
              "Erkläre den Regenbogen"]:
        assert run(p) is None, p
    assert run("Was kann dieses Tool?", routines_enabled=False) is None


def rows(*extra, disable=()):
    base = [dict(r, enabled=r["id"] not in disable) for r in copy.deepcopy(DEFAULTS["routines"])]
    return list(extra) + base


def row(action, keywords, value="", id_="custom:t", enabled=True, name="Test"):
    return {"id": id_, "name": name, "enabled": enabled, "keywords": keywords, "action": action, "value": value}


def test_builtin_rows_can_be_switched_off():
    assert run("Was kann dieses Tool?", routines=rows(disable=("builtin:help",))) is None
    assert run("Wetter in Berlin", routines=rows(disable=("builtin:weather",))) is None
    assert run("Wetter in Berlin") is not None


def test_builtin_rows_accept_extra_keywords():
    r = rows()
    r[0]["keywords"] = ["himmel"]
    assert run("Wie ist der Himmel in Berlin", routines=r).name == "weather"
    assert run("Wie ist der Himmel in Berlin") is None


def test_custom_answer_with_placeholders():
    res = run("zeig mir den code für Lisa", routines=rows(row("answer", ["zeig mir den code für"], "Code für {input}!")))
    assert res.name == "custom" and res.text == "Code für Lisa!" and res.label == "Test"


def test_custom_rows_win_over_builtins_and_disabled_rows_are_ignored():
    mine = row("answer", ["wetter"], "mein Wetter")
    assert run("Wetter in Berlin", routines=rows(mine)).text == "mein Wetter"
    assert run("Wetter in Berlin", routines=rows(dict(mine, enabled=False))).name == "weather"


def test_url_action_encodes_input_and_blocks_bad_schemes():
    calls = []
    launcher = calls.append
    c = cfg(routines=rows(row("url", ["suche"], "https://example.org/?q={input}")))
    res = routines.handle("suche Katzen & Hunde", c, launcher=launcher)
    assert calls == [["xdg-open", "https://example.org/?q=Katzen+%26+Hunde"]] and ("Geöffnet" in res.text or "Opened" in res.text)
    bad = cfg(routines=rows(row("url", ["evil"], "javascript:alert({input})")))
    assert "http" in routines.handle("evil 1", bad, launcher=launcher).text and len(calls) == 1  # refused, nothing spawned


def test_command_action_has_no_shell_injection():
    calls = []
    c = cfg(routines=rows(row("command", ["öffne notiz"], "gedit --new-window {input}")))
    res = routines.handle("öffne notiz a.txt; rm -rf ~", c, launcher=calls.append)
    assert calls == [["gedit", "--new-window", "a.txt; rm -rf ~"]] and ("Gestartet" in res.text or "Started" in res.text)


def test_command_errors_are_reported():
    def missing(argv):
        raise FileNotFoundError(argv[0])
    c = cfg(routines=rows(row("command", ["start x"], "nonexistent-prog")))
    assert any(w in routines.handle("start x", c, launcher=missing).text for w in ("nicht gefunden", "not found"))
    bad = cfg(routines=rows(row("command", ["start y"], 'echo "unclosed')))
    assert any(w in routines.handle("start y", bad, launcher=lambda a: None).text for w in ("ungültig", "invalid"))
    empty = cfg(routines=rows(row("command", ["start z"], "")))
    assert any(w in routines.handle("start z", empty, launcher=lambda a: None).text for w in ("keine Aktion", "no action"))


def test_hermes_and_llm_actions_redirect_the_prompt():
    c = cfg(routines=rows(row("hermes", ["erledige"], "Do this on my PC: {input}"),
                          row("llm", ["übersetze*"], "Translate: {input}", id_="custom:u")))
    h = routines.handle("erledige Backup machen", c)
    assert isinstance(h, routines.Redirect) and h.backend == "hermes" and h.prompt == "Do this on my PC: Backup machen"
    u = routines.handle("Übersetze Hallo Welt", c)
    assert u.backend == "auto" and u.prompt == "Translate: Hallo Welt"


def test_default_example_rows_work():
    calls = []
    assert routines.handle("suche im web nach Katzenfotos", cfg(), launcher=calls.append).name == "custom"
    assert calls[0][0] == "xdg-open" and calls[0][1].endswith("q=Katzenfotos")
    assert isinstance(routines.handle("Translate good morning", cfg()), routines.Redirect)


def test_input_text_and_fill():
    from lms_hermes_bridge.keywords import find
    m = find("Bitte suche im web nach Katzen!", ["suche im web nach"])
    assert routines.input_text("Bitte suche im web nach Katzen!", m) == "Bitte Katzen"
    assert routines.fill("{input}-{input}", "p", "{home}") == "{home}-{home}"  # inserted text is not re-expanded
    assert routines.fill("{prompt}", "a b&c", "x", quote=True) == "a+b%26c"


def test_config_normalizes_and_migrates_routines():
    from lms_hermes_bridge import config
    c = config.normalize_routines({"routines": [{"id": "x", "action": "bogus"}, {"id": "ok", "action": "answer",
                                   "keywords": ["a", " "], "value": 5}, "junk"]})
    ids = [r["id"] for r in c["routines"]]
    assert ids == ["ok", "builtin:weather", "builtin:help", "builtin:google", "builtin:browser",
                   "builtin:home", "builtin:downloads", "builtin:terminal", "builtin:calculator",
                   "builtin:settings"]
    assert c["routines"][0]["keywords"] == ["a"]
    raw = {"routine_help": False}
    config._migrate_routine_flags(raw)
    assert [r["enabled"] for r in raw["routines"][:2]] == [True, False]


def test_google_search_opens_encoded_query_in_default_browser():
    from urllib.parse import quote_plus
    from lms_hermes_bridge import i18n
    i18n.set_language("de")
    cfg = copy.deepcopy(DEFAULTS)
    launched = []
    prompt = "Ich wollte, das der Browser geöffnet wird und bei google nach Capybara-Türstoppern gesucht werden soll"
    result = routines.handle(prompt, cfg, launcher=launched.append)
    expected = "https://www.google.com/search?q=" + quote_plus("Capybara-Türstoppern")
    assert launched == [["xdg-open", expected]]
    assert result.label == "Google-Suche" and expected in result.text


def test_google_search_accepts_direct_and_english_phrasings():
    from urllib.parse import quote_plus
    cfg = copy.deepcopy(DEFAULTS)
    for prompt, query in (("Öffne Browser und suche bei Google nach Gartenstühlen", "Gartenstühlen"),
                          ("google nach capybara doorstoppers", "capybara doorstoppers"),
                          ("search google for capybara doorstoppers", "capybara doorstoppers")):
        launched = []
        result = routines.handle(prompt, cfg, launcher=launched.append)
        assert launched == [["xdg-open", "https://www.google.com/search?q=" + quote_plus(query)]], prompt
        assert result is not None


def test_google_builtin_can_be_disabled():
    cfg = copy.deepcopy(DEFAULTS)
    cfg["routines"] = [dict(r, enabled=False) if r["id"] == "builtin:google" else r
                        for r in cfg["routines"]]
    launched = []
    assert routines.handle("google nach capybara", cfg, launcher=launched.append) is None
    assert not launched


def test_simple_desktop_actions_do_not_need_hermes():
    from pathlib import Path
    cases = [
        ("Öffne den Browser", ["xdg-open", "https://www.google.com/"]),
        ("Öffne den Home-Ordner", ["xdg-open", str(Path.home())]),
        ("Öffne Downloads", ["xdg-open", str(Path.home() / "Downloads")]),
        ("Öffne Terminal", ["x-terminal-emulator"]),
        ("Öffne Rechner", ["gnome-calculator"]),
        ("Öffne Systemeinstellungen", ["gnome-control-center"]),
    ]
    for prompt, expected in cases:
        launched = []
        result = routines.handle(prompt, cfg(), launcher=launched.append)
        assert launched == [expected], prompt
        assert result.name == "custom" and result.label
