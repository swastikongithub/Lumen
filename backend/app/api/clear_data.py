"""DELETE /api/v1/session: "Clear my data" (SPEC §10, §13).

Deletes every conversation, message and feedback row for the caller's X-Session-Id.
"""

from fastapi import APIRouter, status

from app.api.deps import CurrentSession, not_implemented

router = APIRouter(tags=["privacy"])


@router.delete("/session", status_code=status.HTTP_204_NO_CONTENT)
async def clear_session_data(session: CurrentSession) -> None:
    not_implemented(phase=2)
