from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TypeVar

from .utils import sleep

T = TypeVar("T")


class RetryOptions:
    def __init__(
        self,
        attempts: int,
        base_delay_ms: int,
        max_delay_ms: int,
        factor: float,
        retryable: Callable[[BaseException], bool] | None = None,
        on_retry: Callable[[BaseException, int, int], Awaitable[None] | None] | None = None,
    ) -> None:
        self.attempts = attempts
        self.base_delay_ms = base_delay_ms
        self.max_delay_ms = max_delay_ms
        self.factor = factor
        self.retryable = retryable
        self.on_retry = on_retry


async def with_retry(operation: Callable[[], Awaitable[T]], options: RetryOptions) -> T:
    last_error: BaseException | None = None
    for attempt in range(1, options.attempts + 1):
      try:
        return await operation()
      except BaseException as error:
        last_error = error
        is_retryable = options.retryable(error) if options.retryable else True
        if not is_retryable or attempt >= options.attempts:
            raise
        delay_ms = min(options.max_delay_ms, round(options.base_delay_ms * (options.factor ** (attempt - 1))))
        if options.on_retry is not None:
            maybe = options.on_retry(error, attempt, delay_ms)
            if maybe is not None:
                await maybe
        await sleep(delay_ms)
    if last_error is not None:
        raise last_error
    raise RuntimeError("Retry loop failed")
