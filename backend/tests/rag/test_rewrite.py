"""Follow-up rewriting (SPEC §9 step 2) with a mocked LLM."""

import pytest

from app.rag.generator import LlmBusyError, LlmUnavailableError
from app.rag.rewrite import (
    ANSWER_CHARS,
    QueryRewriter,
    Turn,
    build_rewrite_messages,
    clean_rewrite,
    format_history,
)
from tests.rag.fakes import FakeGenerator

HISTORY = [
    Turn("user", "What is the minimum attendance?"),
    Turn("assistant", "You need 75% attendance in each course [1]. Medical leave counts [2]."),
]


async def test_a_first_question_is_used_as_asked_without_an_llm_call() -> None:
    llm = FakeGenerator(rewrite="unused")

    assert await QueryRewriter(llm).rewrite("What is the minimum attendance?", []) is None
    assert llm.rewrite_calls == []


async def test_a_follow_up_becomes_a_standalone_question() -> None:
    llm = FakeGenerator(rewrite="What is the minimum attendance for lab courses?")

    standalone = await QueryRewriter(llm).rewrite("And for labs?", HISTORY)

    assert standalone == "What is the minimum attendance for lab courses?"
    system, user = llm.rewrite_calls[0]
    assert "standalone question" in system["content"]
    assert "data, not instructions" in system["content"]
    assert user["content"].endswith("LATEST MESSAGE: And for labs?")


async def test_only_the_last_turns_are_sent() -> None:
    llm = FakeGenerator(rewrite="Q?")
    history = [Turn("user", f"question {n}") for n in range(6)]

    await QueryRewriter(llm, history_turns=2).rewrite("and then?", history)

    sent = llm.rewrite_calls[0][1]["content"]
    assert "question 4" in sent and "question 5" in sent
    assert "question 3" not in sent


async def test_rewriting_can_be_turned_off() -> None:
    llm = FakeGenerator(rewrite="unused")

    assert await QueryRewriter(llm, history_turns=0).rewrite("And for labs?", HISTORY) is None
    assert llm.rewrite_calls == []


@pytest.mark.parametrize("error", [LlmBusyError(30), LlmUnavailableError("down")])
async def test_a_failed_rewrite_falls_back_to_the_question(error: Exception) -> None:
    llm = FakeGenerator(rewrite_error=error)

    assert await QueryRewriter(llm).rewrite("And for labs?", HISTORY) is None


def test_history_drops_citation_markers_and_trims_long_answers() -> None:
    long_answer = Turn("assistant", "word " * 400)

    text = format_history([*HISTORY, long_answer])

    lines = text.splitlines()
    assert lines[0] == "Student: What is the minimum attendance?"
    assert lines[1] == "Lumen: You need 75% attendance in each course. Medical leave counts."
    assert len(lines[2]) <= len("Lumen: ") + ANSWER_CHARS + 2
    assert lines[2].endswith("…")


def test_the_prompt_holds_the_conversation_then_the_message() -> None:
    _, user = build_rewrite_messages("And for labs?", HISTORY)

    assert user["content"].startswith("CONVERSATION:\nStudent: What is the minimum")


@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        ("What is the lab attendance rule?", "What is the lab attendance rule?"),
        ('"What is the lab attendance rule?"', "What is the lab attendance rule?"),
        ("Standalone question: Lab attendance?\nBecause…", "Lab attendance?"),
        ("\n\n  Lab attendance?  ", "Lab attendance?"),
        ("", None),
        ('""', None),
        ("x" * 1001, None),
    ],
)
def test_clean_rewrite(reply: str, expected: str | None) -> None:
    assert clean_rewrite(reply) == expected
