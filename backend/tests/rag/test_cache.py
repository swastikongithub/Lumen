"""The semantic answer cache against Qdrant's in-memory mode, with hand-made vectors."""

import pytest
from qdrant_client import AsyncQdrantClient

from app.rag import cache as cache_module
from app.rag.cache import AnswerCache, cache_point_id, normalize

COLLECTION = "answer_cache"
CITATIONS = [{"n": 1, "chunk_id": "chunk-1", "title": "Academic Rules", "page": 4}]

# Normalised question -> vector. Cosine with the first one: 0.99, 0.90 and 0.
VECTORS = {
    "what is the attendance rule": [1.0, 0.0, 0.0],
    "whats the attendance rule": [0.99, 0.14, 0.0],
    "what is the attendance policy for labs": [0.9, 0.436, 0.0],
    "when do hostel gates close": [0.0, 1.0, 0.0],
}


def fake_embed(text: str) -> list[float]:
    return VECTORS[text]


@pytest.fixture
async def client():
    client = AsyncQdrantClient(location=":memory:")
    yield client
    await client.close()


@pytest.fixture
async def cache(client: AsyncQdrantClient) -> AnswerCache:
    answer_cache = AnswerCache(client, COLLECTION, fake_embed, dim=3, threshold=0.95)
    await answer_cache.ensure_collection()
    return answer_cache


async def store(cache: AnswerCache, question="What is the attendance rule?", **overrides):
    values = {"category": None, "corpus_version": 3, "content": "75% [1].", "citations": CITATIONS}
    values |= overrides
    await cache.store(question, **values)


def test_normalize_ignores_case_spaces_and_end_punctuation() -> None:
    assert normalize("  What is the   attendance rule?? ") == "what is the attendance rule"
    assert cache_point_id("Attendance rule?", None, 3) == cache_point_id("attendance rule", None, 3)
    assert cache_point_id("attendance rule", None, 3) != cache_point_id("attendance rule", None, 4)


async def test_an_equivalent_question_gets_the_stored_answer(cache: AnswerCache) -> None:
    await store(cache)

    hit = await cache.lookup("whats the attendance rule", None, corpus_version=3)

    assert hit is not None
    assert (hit.content, hit.citations) == ("75% [1].", CITATIONS)
    assert hit.score == pytest.approx(0.99, abs=0.01)


async def test_a_question_below_the_threshold_misses(cache: AnswerCache) -> None:
    await store(cache)

    assert await cache.lookup("What is the attendance policy for labs?", None, 3) is None


async def test_a_new_corpus_version_invalidates_the_entry(cache: AnswerCache) -> None:
    await store(cache, corpus_version=3)

    assert await cache.lookup("What is the attendance rule?", None, corpus_version=4) is None


async def test_entries_are_kept_apart_by_category_filter(cache: AnswerCache) -> None:
    await store(cache, category="exams")

    assert await cache.lookup("What is the attendance rule?", None, 3) is None
    assert await cache.lookup("What is the attendance rule?", "academics", 3) is None
    assert await cache.lookup("What is the attendance rule?", "exams", 3) is not None


async def test_asking_again_replaces_the_entry(cache: AnswerCache, client) -> None:
    await store(cache, content="old [1].")
    await store(cache, question="what is the attendance rule", content="new [1].")

    hit = await cache.lookup("What is the attendance rule?", None, 3)

    assert hit.content == "new [1]."
    assert (await client.count(COLLECTION)).count == 1


async def test_the_question_text_is_not_stored(cache: AnswerCache, client) -> None:
    await store(cache)

    points, _ = await client.scroll(COLLECTION, with_payload=True)

    assert set(points[0].payload) == {
        "answer",
        "citations",
        "corpus_version",
        "category_filter",
        "created_at",
    }


async def test_old_entries_are_deleted(cache: AnswerCache, client, monkeypatch) -> None:
    monkeypatch.setattr(cache_module.time, "time", lambda: 1_000.0)
    await store(cache)
    monkeypatch.setattr(cache_module.time, "time", lambda: 5_000.0)
    await store(cache, question="When do hostel gates close?")

    await cache.delete_older_than(2_000)

    assert await cache.lookup("What is the attendance rule?", None, 3) is None
    assert await cache.lookup("When do hostel gates close?", None, 3) is not None


async def test_a_qdrant_failure_is_a_miss_not_an_error(client: AsyncQdrantClient) -> None:
    missing = AnswerCache(client, "no_such_collection", fake_embed, dim=3)

    await missing.store("What is the attendance rule?", None, 3, "75% [1].", CITATIONS)

    assert await missing.lookup("What is the attendance rule?", None, 3) is None


async def test_ensure_collection_is_idempotent(cache: AnswerCache, client) -> None:
    await store(cache)

    await cache.ensure_collection()

    assert (await client.count(COLLECTION)).count == 1
