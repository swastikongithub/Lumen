"""Liveness and readiness probes. These stay outside /api/v1 (SPEC §10)."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from functools import partial
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel
from qdrant_client import AsyncQdrantClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.api.deps import AppSettings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])

ReadinessCheck = Callable[[], Awaitable[None]]
CheckResult = Literal["ok", "error", "timeout"]


class HealthOut(BaseModel):
    status: Literal["ok"]


class ReadyOut(BaseModel):
    status: Literal["ready", "not_ready"]
    checks: dict[str, CheckResult]


async def ping_postgres(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))


async def ping_qdrant(client: AsyncQdrantClient) -> None:
    await client.get_collections()


def readiness_checks(request: Request) -> dict[str, ReadinessCheck]:
    """The dependencies /ready verifies. Phase 2 adds a check that the models are loaded."""
    state = request.app.state
    return {
        "postgres": partial(ping_postgres, state.engine),
        "qdrant": partial(ping_qdrant, state.qdrant),
    }


@router.get("/health")
async def health() -> HealthOut:
    """Liveness: the process is up. Checks nothing else, so it never flaps."""
    return HealthOut(status="ok")


@router.get("/ready", responses={503: {"model": ReadyOut, "description": "A dependency failed"}})
async def ready(
    response: Response,
    settings: AppSettings,
    checks: Annotated[dict[str, ReadinessCheck], Depends(readiness_checks)],
) -> ReadyOut:
    """Readiness: every dependency answers within the timeout. Runs the checks concurrently."""
    results = await asyncio.gather(
        *(_run_check(name, check, settings.ready_timeout_seconds) for name, check in checks.items())
    )
    report = dict(zip(checks, results, strict=True))
    is_ready = all(result == "ok" for result in report.values())
    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadyOut(status="ready" if is_ready else "not_ready", checks=report)


async def _run_check(name: str, check: ReadinessCheck, limit_seconds: float) -> CheckResult:
    # Failure details go to the log, not the response, so internals don't leak publicly.
    try:
        async with asyncio.timeout(limit_seconds):
            await check()
    except TimeoutError:
        logger.warning("Readiness check %s timed out after %.1fs", name, limit_seconds)
        return "timeout"
    except Exception:
        logger.warning("Readiness check %s failed", name, exc_info=True)
        return "error"
    return "ok"
