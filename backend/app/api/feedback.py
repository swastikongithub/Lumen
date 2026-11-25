"""POST /api/v1/feedback: thumbs up/down on an answer, with an optional reason."""

import uuid
from typing import Annotated, Literal, Self

from fastapi import APIRouter, status
from pydantic import BaseModel, StringConstraints, model_validator

from app.api.deps import CurrentSession, not_implemented
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


@router.post("/feedback", status_code=status.HTTP_204_NO_CONTENT)
async def submit_feedback(body: FeedbackRequest, session: CurrentSession) -> None:
    not_implemented(phase=2)
