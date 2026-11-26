"""GET /admin/stats (SPEC §10): usage numbers for the operator, behind X-Admin-Key.

Outside /api/v1 like the health probes: it is not part of the public API, so it is also
left out of the OpenAPI document (no reason to advertise it). Browsers cannot call it
cross-origin because CORS does not allow the X-Admin-Key header.

The key is compared in constant time (hmac.compare_digest), so response timing reveals
nothing about how much of a guess was right. Without ADMIN_API_KEY the endpoint answers
404, as if it did not exist.

    curl -H "X-Admin-Key: $ADMIN_API_KEY" "http://localhost:8000/admin/stats?days=7"
"""

import hmac
from datetime import UTC, date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel

from app.api.deps import AppSettings
from app.db.session import DbSession
from app.db.stats import usage_stats

# Messages are kept for at most 30 days (app/db/retention.py), so a longer window adds nothing.
MAX_DAYS = 30

router = APIRouter(prefix="/admin", tags=["admin"], include_in_schema=False)


def require_admin_key(
    settings: AppSettings, x_admin_key: Annotated[str | None, Header()] = None
) -> None:
    if settings.admin_api_key is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not Found")
    expected = settings.admin_api_key.get_secret_value().encode()
    given = (x_admin_key or "").encode()
    if not hmac.compare_digest(given, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing or wrong X-Admin-Key")


class DayOut(BaseModel):
    date: date
    questions: int


class PercentilesOut(BaseModel):
    p50: float | None
    p95: float | None


class StatsOut(BaseModel):
    days: int
    since: datetime
    questions: int
    answers: int
    questions_per_day: list[DayOut]
    abstain_rate: float | None
    cache_hit_rate: float | None
    thumbs_up: int
    thumbs_down: int
    thumbs_down_rate: float | None
    latency_ms: PercentilesOut
    ttft_ms: PercentilesOut


@router.get(
    "/stats",
    dependencies=[Depends(require_admin_key)],
    responses={401: {"description": "Missing or wrong X-Admin-Key"}},
)
async def get_stats(db: DbSession, days: Annotated[int, Query(ge=1, le=MAX_DAYS)] = 7) -> StatsOut:
    since = datetime.now(UTC) - timedelta(days=days)
    stats = await usage_stats(db, since)
    return StatsOut(
        days=days,
        since=since,
        questions=stats.questions,
        answers=stats.answers,
        questions_per_day=[
            DayOut(date=d.day, questions=d.questions) for d in stats.questions_per_day
        ],
        abstain_rate=stats.abstain_rate,
        cache_hit_rate=stats.cache_hit_rate,
        thumbs_up=stats.thumbs_up,
        thumbs_down=stats.thumbs_down,
        thumbs_down_rate=stats.thumbs_down_rate,
        latency_ms=PercentilesOut(p50=stats.latency_ms.p50, p95=stats.latency_ms.p95),
        ttft_ms=PercentilesOut(p50=stats.ttft_ms.p50, p95=stats.ttft_ms.p95),
    )
