from lms_hermes_bridge import router
from lms_hermes_bridge.config import DEFAULTS
from lms_hermes_bridge.lmstudio import ModelInfo, parse_params_b
import copy

GB = 1024**3
MODELS = [
    ModelInfo("qwen2.5-3b-instruct", params_b=3, size_bytes=2 * GB),
    ModelInfo("llama-3.1-8b-instruct", params_b=8, size_bytes=5 * GB, loaded=True),
    ModelInfo("qwen2.5-coder-14b", params_b=14, size_bytes=9 * GB),
    ModelInfo("big-70b", params_b=70, size_bytes=40 * GB),
    ModelInfo("nomic-embed", type="embeddings"),
]


def cfg(**over):
    c = copy.deepcopy(DEFAULTS)
    c.update(over)
    return c


def test_parse_params():
    assert parse_params_b("qwen2.5-7b-instruct") == 7
    assert parse_params_b("gemma-4-12B-coder") == 12
    assert parse_params_b("mixtral-8x7b") == 56
    assert parse_params_b("no-size") == 0


def test_classify():
    assert router.classify("open firefox")[0] == "agent"
    assert router.classify("fix this python bug")[0] == "code"
    assert router.classify("analyze the market")[0] == "deep"
    assert router.classify("capital of France?")[0] == "fast"


def test_fast_prefers_small_and_loaded():
    assert router.pick_model(MODELS, "fast", 32 * GB).key == "llama-3.1-8b-instruct"


def test_code_picks_coder_and_deep_fits_memory():
    assert router.pick_model(MODELS, "code", 32 * GB).key == "qwen2.5-coder-14b"
    # 70B (40 GB) does not fit in 32 GB RAM
    assert router.pick_model(MODELS, "deep", 32 * GB).key == "qwen2.5-coder-14b"


def test_embeddings_never_chosen():
    assert router.pick_model([MODELS[-1]], "fast", 32 * GB) is None


def test_vision_route_selects_only_image_capable_models():
    vlm = ModelInfo("gemma4-12b", type="vlm", params_b=12, loaded=False, capabilities=("tool_use",))
    ordinary = ModelInfo("llama-3.1-8b", type="llm", params_b=8, loaded=True)
    c = cfg()
    route = router.decide("describe this", c, [ordinary, vlm], 32 * GB, needs_image=True)
    assert route.backend == "lmstudio" and route.model == vlm.key and route.needs_load
    assert route.params["supports_vision"] and route.params["supports_tools"]
    assert router.pick_model([ordinary], "fast", 32 * GB, require_vision=True) is None


def test_vision_prompt_never_falls_back_to_non_vision_backend():
    c = cfg()
    c["hermes"]["enabled"] = True
    assert router.decide("describe image", c, MODELS, 32 * GB, needs_image=True) is None

    c["routing"] = "hermes"
    vlm = ModelInfo("gemma4-vlm", type="vlm", params_b=12, loaded=True)
    route = router.decide("describe image", c, [vlm], 32 * GB, needs_image=True)
    assert route.backend == "lmstudio" and route.model == vlm.key

    c["routing"] = "provider:p1"
    assert router.decide("describe image", c, [], 32 * GB, needs_image=True) is None


def test_model_capabilities_use_api_type_and_metadata():
    vlm = ModelInfo("some-model", type="vlm", capabilities=("tool_use", "reasoning"))
    assert vlm.supports_vision and vlm.supports_tools and vlm.supports_thinking
    reasoning_model = ModelInfo("deepseek-r1-8b")
    assert reasoning_model.supports_thinking


def test_lmstudio_model_listing_keeps_capability_metadata(monkeypatch):
    from lms_hermes_bridge import lmstudio
    monkeypatch.setattr(lmstudio, "_get_json", lambda _url: {"data": [{
        "id": "vision-test", "type": "vlm", "state": "loaded", "max_context_length": 8192,
        "capabilities": ["tool_use", "reasoning"],
    }]})
    monkeypatch.setattr(lmstudio, "_cli_sizes", lambda: {})
    model = lmstudio.list_models("http://localhost:1234")[0]
    assert model.supports_vision and model.supports_tools and model.supports_thinking


def test_decide_local_and_fallbacks():
    r = router.decide("hi there", cfg(), MODELS, 32 * GB)
    assert r.backend == "lmstudio" and r.params["context"] <= 4096
    assert router.decide("hi", cfg(), None, 32 * GB) is None
    c = cfg(providers=[{"id": "a", "name": "A", "kind": "openai", "endpoint": "x", "model": "m"}])
    assert router.decide("hi", c, None, GB).backend == "provider"
    c["local_only"] = True
    assert router.decide("hi", c, None, GB) is None


def test_agent_goes_to_hermes():
    c = cfg()
    c["hermes"]["enabled"] = True
    assert router.decide("open the browser", c, MODELS, 32 * GB).backend == "hermes"


def test_default_keywords_cover_common_actions():
    for p in ["Öffne den Browser mit wetter.de", "open firefox", "Please create a file notes.txt",
              "Erstelle eine Datei test.txt", "Lade die Datei herunter", "remind me at 5", "Lösche alte Logs"]:
        assert router.classify(p)[0] == "agent", p


def test_keywords_are_whole_words_unless_starred():
    assert router.classify("What is the copyright of this book?")[0] != "agent"
    assert router.classify("Tell me about opening hours of museums")[0] != "agent"
    assert router.classify("install* is a good stem", ["install*"])[0] == "agent"
    assert router.classify("öffnen wir das Gespräch", ["öffne*"])[0] == "agent"
    assert router.classify("Öffne den Browser", ["öffne* browser"])[0] == "agent"


def test_custom_and_empty_keyword_lists():
    assert router.classify("fnord the thing", ["fnord"])[0] == "agent"
    assert router.classify("open firefox", [])[0] != "agent"
    assert router.decide("fnord now", cfg(agent_keywords=["fnord"], hermes={**DEFAULTS["hermes"], "enabled": True}),
                         MODELS, 32 * GB).backend == "hermes"


def test_keywords_per_language_are_all_matched():
    kws = {"en": ["fnord"], "de": ["quark*"]}
    assert router.classify("fnord please", kws)[0] == "agent"
    assert router.classify("quarkig", kws)[0] == "agent"
    assert router.classify("hello", {"en": [], "de": []})[0] != "agent"


def test_default_keywords_are_split_by_language():
    from lms_hermes_bridge.config import DEFAULT_AGENT_KEYWORDS as D
    assert set(D) == {"en", "de"} and "open" in D["en"] and "öffne*" in D["de"]
    assert "open" not in D["de"] and "öffne*" not in D["en"]


def test_legacy_flat_keyword_list_is_migrated():
    from lms_hermes_bridge import config
    out = config._migrate({"agent_keywords": ["open", "öffne*", "mycustom"]})["agent_keywords"]
    assert out == {"en": ["open", "mycustom"], "de": ["öffne*"]}
