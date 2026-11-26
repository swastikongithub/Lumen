"""POST /api/v1/feedback: thumbs up/down on an answer, with an optional reason.

Only answers (assistant messages) from the caller's own conversations can be rated.
Rating the same answer again replaces the earlier rating.
"""

import uuid
from typing import Annotated, Literal, Self

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, StringConstraints, model_validator

from app.api.deps import CurrentSession
from app.db.chats import find_answer, save_feedback
from app.db.session import DbSession
from app.enums import FeedbackReason

MAX_COMMENT_CHARS = 1000

router = APIRouter(tags=["feedback"])


class FeedbackRequest(BaseModel):
    message_id: uuid.UUID
    rating: Literal[1, -1]
    # Thumbs-down only. "offensive" is the in-app report Google Play requires.
    reason: FeedbackReason | None = None
    comment: (
        Annotated[str, StringConstraints(strip_whitespace=True, max_length=MAX_COMMENT_CHARS)]
        | None
    ) = None

    @model_validator(mode="after")
    def reason_only_with_thumbs_down(self) -> Self:
        if self.reason is not None and self.rating == 1:
            raise ValueError("reason is only allowed with rating -1")
        return self


@router.post(
    "/feedback",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"description": "Answer not found for this session"}},
)
async def submit_feedback(body: FeedbackRequest, session: CurrentSession, db: DbSession) -> None:
    answer = await find_answer(db, session.session_id, body.message_id)
    if answer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Answer not found")
    await save_feedback(db, answer.id, body.rating, body.reason, body.comment or None)
    await db.commit()
