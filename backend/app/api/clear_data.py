"""DELETE /api/v1/session: "Clear my data" (SPEC §10, §13).

Deletes every conversation, message and feedback row for the caller's X-Session-Id.
Clients also wipe what they keep on the device (saved answers, the session ID itself).
"""

import logging

from fastapi import APIRouter, status

from app.api.deps import CurrentSession
from app.db.chats import delete_session_data
from app.db.session import DbSession

logger = logging.getLogger(__name__)

router = APIRouter(tags=["privacy"])


@router.delete("/session", status_code=status.HTTP_204_NO_CONTENT)
async def clear_session_data(session: CurrentSession, db: DbSession) -> None:
    deleted = await delete_session_data(db, session.session_id)
    await db.commit()
    logger.info("Cleared session data: %d conversations deleted", deleted)
