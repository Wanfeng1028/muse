import pytest


def test_bm25_preprocessing_is_cached(monkeypatch):
    from hy_memory.pipelines._retrieval import lemmatize

    calls = 0

    def fake_english(text):
        nonlocal calls
        calls += 1
        return text.lower()

    monkeypatch.setattr(lemmatize, "_lemmatize_english", fake_english)
    lemmatize._lemmatize_cached.cache_clear()

    assert lemmatize.lemmatize_for_bm25("Repeated Candidate") == "repeated candidate"
    assert lemmatize.lemmatize_for_bm25("Repeated Candidate") == "repeated candidate"
    assert calls == 1


def test_ner_preprocessing_is_cached(monkeypatch):
    from hy_memory.pipelines._retrieval import ner

    calls = 0

    class Entity:
        text = "Tokyo"
        label_ = "GPE"

    class Doc:
        ents = [Entity()]

    class NLP:
        def __call__(self, text):
            nonlocal calls
            calls += 1
            return Doc()

    monkeypatch.setattr(ner, "_get_nlp", lambda: NLP())
    ner._extract_entities_cached.cache_clear()

    assert ner.extract_entities("Tokyo", for_boost=True) == [("Tokyo", "GPE")]
    assert ner.extract_entities("Tokyo", for_boost=True) == [("Tokyo", "GPE")]
    assert calls == 1


def test_ner_result_cache_isolated_across_model_reload(monkeypatch):
    from types import SimpleNamespace
    from hy_memory.pipelines._retrieval import ner

    def model(label):
        return lambda text: SimpleNamespace(
            ents=[SimpleNamespace(text=text, label_=label)]
        )

    monkeypatch.setattr(ner, "_ner_nlp", None)
    monkeypatch.setattr(ner, "_ner_load_attempted", False)
    monkeypatch.setattr(ner, "_load_nlp", lambda: model("GPE"))
    ner._extract_entities_cached.cache_clear()
    assert ner.extract_entities("London") == [("London", "GPE")]

    monkeypatch.setattr(ner, "_ner_nlp", None)
    monkeypatch.setattr(ner, "_ner_load_attempted", False)
    monkeypatch.setattr(ner, "_load_nlp", lambda: model("ORG"))
    ner._extract_entities_cached.cache_clear()
    assert ner.extract_entities("London") == [("London", "ORG")]


@pytest.mark.asyncio
async def test_existing_tags_cache_can_be_disabled(monkeypatch):
    from hy_memory.models.memory import MemoryNode
    from hy_memory.pipelines.writer import MemoryWriter

    class Store:
        def __init__(self):
            self.calls = 0

        async def list_by_user(self, **kwargs):
            self.calls += 1
            node = MemoryNode(node_id="n", user_id="u", content="c")
            node.tags = ["tag"]
            return [node]

    monkeypatch.setenv("MEMORY_EXISTING_TAGS_CACHE_TTL_SEC", "0")
    writer = MemoryWriter.__new__(MemoryWriter)
    store = Store()

    await writer._collect_existing_tags(store, "u", "a")
    await writer._collect_existing_tags(store, "u", "a")
    assert store.calls == 2
