"""Usage numbers for GET /admin/stats (SPEC §10), computed in Postgres over a window of days.

- questions: user messages, also counted per UTC day;
- answers: assistant messages. A failed answer (busy, unavailable) is never saved, so
  questions minus answers is roughly the number of failures;
- abstain and cache-hit rates: shares of answers;
- thumbs-down rate: share of rated answers that got a thumbs down;
- latency and time to first token: p50 and p95 over answers, in milliseconds.
Rates and percentiles are None when there is nothing to compute them from.
"""

from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import Float, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Feedback, Message
from app.enums import Role


@dataclass(frozen=True)
class DayCount:
    day: date
    questions: int


@dataclass(frozen=True)
class Percentiles:
    p50: float | None
    p95: float | None


@dataclass(frozen=True)
class UsageStats:
    questions: int
    answers: int
    questions_per_day: list[DayCount]
    abstain_rate: float | None
    cache_hit_rate: float | None
    thumbs_up: int
    thumbs_down: int
    thumbs_down_rate: float | None
    latency_ms: Percentiles
    ttft_ms: Percentiles


def share(part: int, whole: int) -> float | None:
    return round(part / whole, 4) if whole else None


def percentile(fraction: float, column):
    return func.percentile_cont(fraction).within_group(cast(column, Float))


async def usage_stats(db: AsyncSession, since: datetime) -> UsageStats:
    answer = (Message.role == Role.ASSISTANT) & (Message.created_at >= since)
    row = (
        await db.execute(
            select(
                func.count(),
                func.count().filter(Message.abstained.is_(True)),
                func.count().filter(Message.cache_hit.is_(True)),
                percentile(0.5, Message.latency_ms),
                percentile(0.95, Message.latency_ms),
                percentile(0.5, Message.ttft_ms),
                percentile(0.95, Message.ttft_ms),
            ).where(answer)
        )
    ).one()
    answers, abstained, cache_hits, lat50, lat95, ttft50, ttft95 = row

    day = func.date(func.timezone("UTC", Message.created_at)).label("day")
    per_day = await db.execute(
        select(day, func.count())
        .where(Message.role == Role.USER, Message.created_at >= since)
        .group_by(day)
        .order_by(day)
    )
    questions_per_day = [DayCount(day=d, questions=n) for d, n in per_day]

    ratings = dict(
        (
            await db.execute(
                select(Feedback.rating, func.count())
                .join(Message, Feedback.message_id == Message.id)
                .where(answer)
                .group_by(Feedback.rating)
            )
        ).all()
    )
    up, down = ratings.get(1, 0), ratings.get(-1, 0)

    return UsageStats(
        questions=sum(d.questions for d in questions_per_day),
        answers=answers,
        questions_per_day=questions_per_day,
        abstain_rate=share(abstained, answers),
        cache_hit_rate=share(cache_hits, answers),
        thumbs_up=up,
        thumbs_down=down,
        thumbs_down_rate=share(down, up + down),
        latency_ms=Percentiles(p50=lat50, p95=lat95),
        ttft_ms=Percentiles(p50=ttft50, p95=ttft95),
    )
