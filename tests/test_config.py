import copy

from lms_hermes_bridge import config


def test_builtin_rows_keep_their_action_and_value_after_a_save():
    """The settings table renders a builtin row's value disabled and used to submit it empty.

    Saving must not blank out the shortcuts it has just shown, so the action and the value of
    a built-in row always come from DEFAULT_ROUTINES.
    """
    saved = copy.deepcopy(config.DEFAULT_ROUTINES)
    for row in saved:
        if row["id"] in config.BUILTIN_ROUTINES:
            row["value"] = ""
    rows = config.normalize_routines({"routines": saved})["routines"]
    by_id = {row["id"]: row for row in rows}
    for template in config.DEFAULT_ROUTINES:
        if template["id"] in config.BUILTIN_ROUTINES and template["value"]:
            assert by_id[template["id"]]["action"] == template["action"]
            assert by_id[template["id"]]["value"] == template["value"]


def test_builtin_keywords_survive_a_save():
    """Extra keywords added to a built-in row are user data and must be kept."""
    saved = copy.deepcopy(config.DEFAULT_ROUTINES)
    for row in saved:
        if row["id"] == "builtin:terminal":
            row["keywords"] = ["shell oeffnen"]
    rows = config.normalize_routines({"routines": saved})["routines"]
    row = next(r for r in rows if r["id"] == "builtin:terminal")
    assert row["keywords"] == ["shell oeffnen"]


def test_one_row_per_id():
    row = {"id": "custom:x", "name": "X", "keywords": ["x"], "action": "answer", "value": "y"}
    rows = config.normalize_routines({"routines": [row, dict(row)]})["routines"]
    assert [r["id"] for r in rows].count("custom:x") == 1


def test_copilot_preset_points_at_the_endpoint_that_answers():
    """models.github.ai/inference answers the literal string "OK" for every path, so a provider
    built from that preset never receives a completion. Verified against the live API with an
    authenticated `gh auth token`; the Copilot endpoint does answer.
    """
    preset = config.PROVIDER_PRESETS["copilot"]
    assert preset["endpoint"] == "https://api.githubcopilot.com/chat/completions"
    assert preset["kind"] == "openai"
