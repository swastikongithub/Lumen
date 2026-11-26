"""Pipeline steps 2, 3 and 9 (SPEC §9): follow-up rewriting, the answer cache, tracing."""

from app.rag.citations import UNVERIFIED_NOTICE
from app.rag.generator import LlmBusyError
from app.rag.pipeline import Answer, PipelineConfig, RagPipeline
from app.rag.prompts import NOT_FOUND_ANSWER
from app.rag.rewrite import QueryRewriter, Turn
from tests.rag.fakes import (
    FakeCache,
    FakeGenerator,
    FakeRetriever,
    FakeScorer,
    FakeTracer,
    make_chunk,
)

LAB = make_chunk(1, "Lab courses need 80% attendance.")
ATTENDANCE = make_chunk(2, "Students need 75% attendance to sit the end-term exam.")
SCORES = {"80%": 6.0, "75%": 4.0}
HISTORY = [
    Turn("user", "What is the minimum attendance?"),
    Turn("assistant", "You need 75% attendance [1]."),
]
STANDALONE = "What is the minimum attendance for lab courses?"


def pipeline(llm: FakeGenerator, *, cache=None, tracer=None, threshold=0.0) -> RagPipeline:
    return RagPipeline(
        FakeRetriever([LAB, ATTENDANCE]),
        FakeScorer(SCORES),
        llm,
        PipelineConfig(abstain_threshold=threshold),
        rewriter=QueryRewriter(llm),
        cache=cache,
        tracer=tracer,
    )


async def collect(rag: RagPipeline, question="And for labs?", category=None, **kwargs):
    pieces, answers = [], []
    async for item in rag.run(question, category, **kwargs):
        (answers if isinstance(item, Answer) else pieces).append(item)
    assert len(answers) == 1
    return "".join(pieces), answers[0]


# --- step 2: rewrite --------------------------------------------------------------------


async def test_a_follow_up_is_searched_and_answered_as_a_standalone_question() -> None:
    llm = FakeGenerator("Lab courses need 80% [1].", rewrite=STANDALONE)
    rag = pipeline(llm)

    _, answer = await collect(rag, history=HISTORY)

    assert rag.retriever.calls == [(STANDALONE, None)]
    assert llm.calls[0][1]["content"].endswith(f"QUESTION: {STANDALONE}")
    assert answer.rewritten_query == STANDALONE


async def test_a_first_question_is_not_rewritten() -> None:
    llm = FakeGenerator("You need 75% [1].", rewrite="unused")
    rag = pipeline(llm)

    _, answer = await collect(rag, "What is the minimum attendance?")

    assert llm.rewrite_calls == []
    assert rag.retriever.calls == [("What is the minimum attendance?", None)]
    assert answer.rewritten_query is None


async def test_a_failed_rewrite_searches_the_question_as_asked() -> None:
    llm = FakeGenerator("Lab courses need 80% [1].", rewrite_error=LlmBusyError(30))
    rag = pipeline(llm)

    _, answer = await collect(rag, history=HISTORY)

    assert rag.retriever.calls == [("And for labs?", None)]
    assert answer.rewritten_query is None and not answer.abstained


async def test_an_abstained_follow_up_keeps_its_rewrite() -> None:
    llm = FakeGenerator("unused", rewrite=STANDALONE)

    _, answer = await collect(pipeline(llm, threshold=10.0), history=HISTORY)

    assert answer.abstained and answer.rewritten_query == STANDALONE


# --- step 3: the answer cache -----------------------------------------------------------


async def test_a_grounded_answer_is_cached_and_served_again() -> None:
    cache = FakeCache()
    first_llm = FakeGenerator("Lab courses need 80% [1].")
    _, first = await collect(pipeline(first_llm, cache=cache), STANDALONE, corpus_version=3)

    llm = FakeGenerator("should not be called")
    rag = pipeline(llm, cache=cache)
    streamed, again = await collect(rag, STANDALONE.upper(), corpus_version=3)

    assert not first.cache_hit
    assert again.cache_hit and not again.abstained
    assert streamed == again.content == first.content
    assert again.citations == first.citations
    assert rag.retriever.calls == [] and llm.calls == []
    assert again.model is None and again.tokens_in is None  # no LLM answered


async def test_the_cache_is_looked_up_with_the_standalone_question() -> None:
    cache = FakeCache()
    llm = FakeGenerator("Lab courses need 80% [1].", rewrite=STANDALONE)

    await collect(
        pipeline(llm, cache=cache), history=HISTORY, category="academics", corpus_version=3
    )

    assert cache.lookups == [(STANDALONE, "academics", 3)]
    assert list(cache.entries) == [(STANDALONE.lower().rstrip("?"), "academics", 3)]


async def test_abstentions_and_unverified_answers_are_not_cached() -> None:
    cache = FakeCache()

    await collect(pipeline(FakeGenerator("unused"), cache=cache, threshold=10.0), corpus_version=3)
    await collect(pipeline(FakeGenerator(NOT_FOUND_ANSWER), cache=cache), corpus_version=3)
    _, unverified = await collect(
        pipeline(FakeGenerator("Labs need 80%."), cache=cache), corpus_version=3
    )

    assert unverified.content.endswith(UNVERIFIED_NOTICE)
    assert cache.entries == {}


async def test_without_a_corpus_version_the_cache_is_not_used() -> None:
    cache = FakeCache()

    await collect(pipeline(FakeGenerator("Labs need 80% [1]."), cache=cache))

    assert cache.lookups == [] and cache.entries == {}


# --- step 9: tracing --------------------------------------------------------------------


async def test_each_step_is_a_span() -> None:
    tracer = FakeTracer()
    llm = FakeGenerator("Lab courses need 80% [1].", rewrite=STANDALONE)

    await collect(
        pipeline(llm, cache=FakeCache(), tracer=tracer), history=HISTORY, corpus_version=3
    )

    assert tracer.names == [
        "rewrite",
        "cache-lookup",
        "retrieve",
        "rerank",
        "generate",
        "cache-store",
    ]
    spans = {span.name: span for span in tracer.spans}
    assert spans["rewrite"].fields["output"] == STANDALONE
    assert spans["cache-lookup"].fields["output"] == {"hit": False, "score": None}
    assert spans["rerank"].fields["metadata"]["best_score"] == 6.0
    assert [c["chunk_id"] for c in spans["retrieve"].fields["output"]] == ["chunk-1", "chunk-2"]
    assert "text" not in spans["retrieve"].fields["output"][0]  # IDs and scores only
    assert spans["generate"].fields["output"] == "Lab courses need 80% [1]."


async def test_a_cache_hit_stops_after_the_lookup_span() -> None:
    cache, tracer = FakeCache(), FakeTracer()
    await collect(pipeline(FakeGenerator("Labs need 80% [1]."), cache=cache), corpus_version=3)

    await collect(pipeline(FakeGenerator("unused"), cache=cache, tracer=tracer), corpus_version=3)

    assert tracer.names == ["cache-lookup"]
    assert tracer.spans[0].fields["output"] == {"hit": True, "score": 1.0}
