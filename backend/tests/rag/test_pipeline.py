"""The pipeline end to end with a mocked LLM, retriever and re-ranker (SPEC §9)."""

import pytest

from app.rag.citations import UNVERIFIED_NOTICE
from app.rag.generator import LlmBusyError, LlmUnavailableError
from app.rag.pipeline import Answer, PipelineConfig, RagPipeline
from app.rag.prompts import NOT_FOUND_ANSWER
from tests.rag.fakes import FakeGenerator, FakeRetriever, FakeScorer, busy_generator, make_chunk

ATTENDANCE = make_chunk(1, "Students need 75% attendance to sit the end-term exam.")
MEDICAL = make_chunk(2, "Medical leave counts towards attendance when approved.")
HOSTEL = make_chunk(3, "Hostel gates close at 10 pm.", category="hostel")
SCORES = {"75%": 6.0, "Medical": 3.0, "Hostel": -4.0}


def pipeline(
    generator: FakeGenerator,
    chunks=(ATTENDANCE, MEDICAL, HOSTEL),
    scores=SCORES,
    **config,
) -> RagPipeline:
    return RagPipeline(
        FakeRetriever(chunks), FakeScorer(scores), generator, PipelineConfig(**config)
    )


async def collect(rag: RagPipeline, question: str = "attendance rule?", category=None):
    pieces, answers = [], []
    async for item in rag.run(question, category):
        (answers if isinstance(item, Answer) else pieces).append(item)
    assert len(answers) == 1, "run() ends with exactly one Answer"
    return "".join(pieces), answers[0]


async def test_answer_streams_and_cites_the_blocks_it_used() -> None:
    llm = FakeGenerator("You need 75% attendance [1]. Approved medical leave counts [2].")

    streamed, answer = await collect(pipeline(llm))

    assert streamed == answer.content == llm.reply
    assert [(c["n"], c["chunk_id"]) for c in answer.citations] == [(1, "chunk-1"), (2, "chunk-2")]
    assert not answer.abstained
    assert (answer.model, answer.tokens_in, answer.best_score) == ("fake-model", 900, 6.0)


async def test_prompt_numbers_blocks_in_rerank_order() -> None:
    llm = FakeGenerator("Yes [1].")

    await collect(pipeline(llm, chunks=(HOSTEL, MEDICAL, ATTENDANCE), rerank_top_n=2))

    user_prompt = llm.calls[0][1]["content"]
    assert user_prompt.index("75% attendance") < user_prompt.index("Medical leave")
    assert "Hostel gates" not in user_prompt  # cut by rerank_top_n


async def test_low_rerank_score_abstains_without_calling_the_llm() -> None:
    llm = FakeGenerator("should never be used")

    streamed, answer = await collect(pipeline(llm, abstain_threshold=7.0, abstain_sources=2))

    assert llm.calls == []
    assert streamed == answer.content == NOT_FOUND_ANSWER
    assert answer.abstained
    assert [c["chunk_id"] for c in answer.citations] == ["chunk-1", "chunk-2"]  # closest sources


async def test_no_retrieved_chunks_abstains_with_no_sources() -> None:
    llm = FakeGenerator("unused")

    _, answer = await collect(pipeline(llm, chunks=()))

    assert answer.abstained
    assert answer.citations == []
    assert answer.best_score is None
    assert llm.calls == []


async def test_category_is_passed_to_the_retriever() -> None:
    rag = pipeline(FakeGenerator("Yes [1]."))

    await collect(rag, "hostel gates?", category="hostel")

    assert rag.retriever.calls == [("hostel gates?", "hostel")]


async def test_citations_to_blocks_outside_the_context_are_dropped() -> None:
    llm = FakeGenerator("You need 75% attendance [1][9].")

    _, answer = await collect(pipeline(llm))

    assert [c["n"] for c in answer.citations] == [1]
    assert answer.content == llm.reply  # the text itself is not rewritten


async def test_answer_without_valid_citations_gets_a_notice() -> None:
    llm = FakeGenerator("You need 75% attendance.")

    streamed, answer = await collect(pipeline(llm))

    assert streamed == answer.content == llm.reply + UNVERIFIED_NOTICE
    assert answer.citations == []
    assert not answer.abstained


async def test_model_saying_not_found_counts_as_an_abstention() -> None:
    llm = FakeGenerator(NOT_FOUND_ANSWER)

    streamed, answer = await collect(pipeline(llm, abstain_sources=1))

    assert streamed == NOT_FOUND_ANSWER  # no "couldn't verify" notice on top
    assert answer.abstained
    assert [c["chunk_id"] for c in answer.citations] == ["chunk-1"]
    assert answer.model == "fake-model"  # the LLM was called, so its usage is kept


async def test_empty_model_reply_is_an_error() -> None:
    with pytest.raises(LlmUnavailableError):
        await collect(pipeline(FakeGenerator("   ")))


async def test_rate_limits_reach_the_caller() -> None:
    with pytest.raises(LlmBusyError) as error:
        await collect(pipeline(busy_generator(retry_after=42)))

    assert error.value.retry_after == 42
