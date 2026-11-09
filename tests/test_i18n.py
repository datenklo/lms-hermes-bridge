from lms_hermes_bridge import i18n


def test_language_priority_and_manual_selection(monkeypatch):
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    monkeypatch.delenv("LC_ALL", raising=False)
    monkeypatch.delenv("LC_MESSAGES", raising=False)
    monkeypatch.setenv("LANGUAGE", "fr:de_DE:en")
    assert i18n.detect() == "de"
    i18n.set_language("en")
    assert i18n.current() == "en"
    i18n.set_language("auto")
    assert i18n.current() == "de"
    i18n.set_language("en")


def test_c_locale_ignores_language_override(monkeypatch):
    monkeypatch.setenv("LC_ALL", "C.UTF-8")
    monkeypatch.setenv("LANGUAGE", "de")
    assert i18n.detect() == "en"