"""Pacing helpers to avoid LinkedIn Sales Navigator velocity throttling."""

from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass


@dataclass
class PacingConfig:
    """Anti-burst pacing for territory persona harvest."""

    # Pause between accounts (seconds).
    delay: float = 6.0
    delay_jitter: float = 4.0
    # Pause between API calls for the same account (resolve + search + refine).
    request_delay: float = 2.5
    request_jitter: float = 1.5
    # After this many accounts in a row, take batch_pause.
    batch_size: int = 20
    batch_pause: float = 600.0
    # Stop the run after this many newly processed accounts (None = no cap).
    max_per_run: int | None = 40
    # Stop the run after this many consecutive 429 responses.
    rate_limit_stop_after: int = 3
    # Retry rate-limited accounts at end of run (causes burst; default off).
    retry_at_end: bool = False


async def pace_between_accounts(config: PacingConfig) -> None:
    wait = config.delay + random.uniform(0, max(config.delay_jitter, 0))
    await asyncio.sleep(wait)


async def pace_between_requests(config: PacingConfig) -> None:
    wait = config.request_delay + random.uniform(0, max(config.request_jitter, 0))
    await asyncio.sleep(wait)


async def pace_batch_break(config: PacingConfig, accounts_since_break: int) -> int:
    if config.batch_size <= 0 or config.batch_pause <= 0:
        return accounts_since_break
    if accounts_since_break < config.batch_size:
        return accounts_since_break
    print(
        f"Batch pause: sleeping {config.batch_pause:.0f}s after "
        f"{accounts_since_break} accounts...",
        flush=True,
    )
    await asyncio.sleep(config.batch_pause)
    return 0
