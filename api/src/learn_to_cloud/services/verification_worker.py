"""Run persisted verification attempts alongside the web API."""

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from learn_to_cloud_shared.core.config import VerificationWorkerConfig
from learn_to_cloud_shared.models import utcnow
from learn_to_cloud_shared.repositories.verification_attempt_repository import (
    AttemptAlreadyGoneError,
    VerificationAttemptRepository,
)
from learn_to_cloud_shared.verification_attempt_executor import (
    expire_verification_attempts,
    terminalize_verification_attempt,
)
from opentelemetry import trace
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from learn_to_cloud.services.verification_runner import execute_verification_attempt

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


@dataclass
class VerificationWorkerState:
    """Process-local liveness state for the sequential verification worker."""

    stale_after_seconds: float
    last_heartbeat: float
    status: str = "running"
    shutdown_requested: bool = False

    @classmethod
    def from_config(cls, config: VerificationWorkerConfig) -> "VerificationWorkerState":
        """Create state with a threshold covering the longest legitimate operation."""
        return cls(
            stale_after_seconds=(
                config.execution_timeout_seconds
                + config.shutdown_timeout_seconds
                + (config.poll_interval_seconds * 2)
            ),
            last_heartbeat=time.monotonic(),
        )

    def heartbeat(self) -> None:
        """Record progress at a worker-loop checkpoint."""
        self.last_heartbeat = time.monotonic()

    def request_shutdown(self) -> None:
        """Mark cancellation as an expected lifecycle event."""
        self.shutdown_requested = True

    def finish(self, task: asyncio.Task[None]) -> None:
        """Classify the worker's terminal task state without logging exception data."""
        if task.cancelled():
            self.status = "stopped" if self.shutdown_requested else "failed"
        elif task.exception() is not None:
            self.status = "failed"
        else:
            self.status = "stopped"

    @property
    def is_stale(self) -> bool:
        """Return whether the worker missed its liveness deadline."""
        return time.monotonic() - self.last_heartbeat > self.stale_after_seconds


async def _fail_attempt(
    attempt_id: UUID,
    error_code: str,
    session_maker: async_sessionmaker[AsyncSession],
    config: VerificationWorkerConfig,
) -> None:
    try:
        async with asyncio.timeout(config.shutdown_timeout_seconds):
            await terminalize_verification_attempt(
                attempt_id,
                outcome="server_error",
                error_code=error_code,
                validation_message=(
                    "Verification could not finish. This attempt was not counted. "
                    "Please try again."
                ),
                terminal_source="api_worker",
                session_maker=session_maker,
            )
    except AttemptAlreadyGoneError:
        logger.info(
            "verification.attempt.deleted",
            extra={"verification.attempt.id": str(attempt_id)},
        )
    except (SQLAlchemyError, TimeoutError) as exc:
        logger.error(
            "verification.attempt.finalize_failed",
            extra={
                "verification.attempt.id": str(attempt_id),
                "error.type": type(exc).__name__,
            },
        )


async def _execute(
    attempt_id: UUID,
    session_maker: async_sessionmaker[AsyncSession],
    config: VerificationWorkerConfig,
) -> None:
    with tracer.start_as_current_span(
        "verification.execute",
        attributes={"verification.attempt.id": str(attempt_id)},
        record_exception=False,
        set_status_on_exception=False,
    ) as span:
        logger.info(
            "verification.attempt.started",
            extra={"verification.attempt.id": str(attempt_id)},
        )
        try:
            async with asyncio.timeout(config.execution_timeout_seconds):
                await execute_verification_attempt(
                    attempt_id, session_maker=session_maker
                )
        except asyncio.CancelledError:
            span.set_status(trace.StatusCode.ERROR, "verification_interrupted")
            await _fail_attempt(
                attempt_id, "verification_interrupted", session_maker, config
            )
            raise
        except TimeoutError:
            span.set_status(trace.StatusCode.ERROR, "verification_timeout")
            await _fail_attempt(
                attempt_id, "verification_timeout", session_maker, config
            )
        except Exception as exc:
            # Provider errors can contain evidence or credentials; log only the type.
            span.set_status(trace.StatusCode.ERROR, "verification_error")
            logger.error(
                "verification.attempt.execution_failed",
                extra={
                    "verification.attempt.id": str(attempt_id),
                    "error.type": type(exc).__name__,
                },
            )
            await _fail_attempt(attempt_id, "verification_error", session_maker, config)


async def run_verification_worker(
    session_maker: async_sessionmaker[AsyncSession],
    config: VerificationWorkerConfig,
    heartbeat: Callable[[], None] | None = None,
) -> None:
    """Poll and claim one attempt at a time; started attempts are never retried."""
    try:
        while True:
            if heartbeat is not None:
                heartbeat()
            now = utcnow()
            queued_before = now - timedelta(seconds=config.queue_timeout_seconds)
            try:
                await expire_verification_attempts(
                    queued_before=queued_before,
                    started_before=now
                    - timedelta(
                        seconds=config.execution_timeout_seconds
                        + config.shutdown_timeout_seconds
                    ),
                    session_maker=session_maker,
                )
                if heartbeat is not None:
                    heartbeat()
                async with session_maker() as db:
                    attempt_id = await VerificationAttemptRepository(db).claim_pending(
                        queued_after=queued_before
                    )
                    await db.commit()
                if heartbeat is not None:
                    heartbeat()
            except SQLAlchemyError as exc:
                logger.error(
                    "verification.worker.database_unavailable",
                    extra={"error.type": type(exc).__name__},
                )
                await asyncio.sleep(config.poll_interval_seconds)
                continue
            if attempt_id is None:
                await asyncio.sleep(config.poll_interval_seconds)
            else:
                await _execute(attempt_id, session_maker, config)
                if heartbeat is not None:
                    heartbeat()
    except Exception as exc:
        logger.error(
            "verification.worker.failed", extra={"error.type": type(exc).__name__}
        )
        raise
