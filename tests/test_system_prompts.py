from lms_hermes_bridge.config import DEFAULTS
from lms_hermes_bridge.system_prompts import DEFAULT_SYSTEM_PROMPTS, for_language


def test_default_prompts_exist_in_both_languages():
    assert "# ROLLE UND ZIEL" in DEFAULT_SYSTEM_PROMPTS["de"]
    assert "# ROLE AND GOAL" in DEFAULT_SYSTEM_PROMPTS["en"]
    assert "Quellen:" in DEFAULT_SYSTEM_PROMPTS["de"]
    assert "Sources:" in DEFAULT_SYSTEM_PROMPTS["en"]


def test_language_selects_its_own_default_prompt():
    assert for_language(DEFAULTS, "de") == DEFAULT_SYSTEM_PROMPTS["de"]
    assert for_language(DEFAULTS, "en") == DEFAULT_SYSTEM_PROMPTS["en"]
    assert for_language(DEFAULTS, "fr") == DEFAULT_SYSTEM_PROMPTS["en"]


def test_custom_prompts_override_defaults_and_can_be_empty():
    config = {"system_prompts": {"de": "Eigene Vorgabe", "en": ""}}
    assert for_language(config, "de") == "Eigene Vorgabe"
    assert for_language(config, "en") == ""
